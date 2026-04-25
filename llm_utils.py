import requests
import json
from typing import List, Dict, Any, Optional, Generator

LLAMA_CPP_BASE_URL = "http://localhost:8081"

class LLMUtils:
    @staticmethod
    def validate_schema(data: Any, schema_input: Any) -> Optional[str]:
        """
        Validates the data against the function definition schema.
        schema_input can be a list of tools or a single tool dictionary.
        """
        if not isinstance(data, dict):
            return "Output must be a JSON object."
        
        if not schema_input:
            return None
        
        # Get the function definition part
        if isinstance(schema_input, list):
            if len(schema_input) > 0:
                func_def = schema_input[0].get("function", {})
            else:
                return None
        else:
            func_def = schema_input.get("function", {})

        parameters = func_def.get("parameters", {})
        required = parameters.get("required", [])
        properties = parameters.get("properties", {})
        
        for req in required:
            if req not in data:
                return f"Missing required property: '{req}'"
        
        # Type checking (basic) with auto-fix for stringified JSON
        for key, value in data.items():
            if key in properties:
                expected_type = properties[key].get("type")
                
                # Auto-fix: if we expect an array/object but got a string, try to parse it
                if (expected_type == "array" and not isinstance(value, list)) or \
                   (expected_type == "object" and not isinstance(value, dict)):
                    if isinstance(value, str):
                        # Strip common outer junk and also internal newlines that might break stringified JSON
                        candidate = value.strip().strip("'").strip("\"").strip()
                        candidate = candidate.replace("\\n", "").replace("\n", "")
                        
                        if (expected_type == "array" and candidate.startswith("[") and candidate.endswith("]")) or \
                           (expected_type == "object" and candidate.startswith("{") and candidate.endswith("}")):
                            try:
                                fixed_value = json.loads(candidate)
                                if (expected_type == "array" and isinstance(fixed_value, list)) or \
                                   (expected_type == "object" and isinstance(fixed_value, dict)):
                                    data[key] = fixed_value
                                    value = fixed_value # Update local value for further checks
                                    continue # Fixed!
                            except:
                                pass

                if expected_type == "array" and not isinstance(value, list):
                    return f"Property '{key}' should be a list/array."
                elif expected_type == "string" and not isinstance(value, str):
                    return f"Property '{key}' should be a string."
                elif expected_type == "object" and not isinstance(value, dict):
                    return f"Property '{key}' should be an object."
        
        return None

    @staticmethod
    def stream(
        prompt: str,
        model: str = "hauhau",
        thinking: bool = True,
        context_window: int = 65536,
        json_response: bool = False,
        function_definition: Optional[List[Dict[str, Any]]] = None,
        keep_alive: Any = None
    ) -> Generator[str, None, None]:
        """
        Streams response from a local llama.cpp server with internal retry and validation logic.
        """
        messages = [
            {'role': 'user', 'content': prompt}
        ]

        max_retries = 5

        for attempt in range(max_retries):
            full_content = ""
            full_json_content = ""
            last_yield_type = None

            try:
                payload = {
                    "model": model,
                    "messages": messages,
                    "stream": True,
                    "options": {
                        "num_ctx": context_window
                    }
                }

                if json_response or function_definition:
                    payload["format"] = "json"

                if function_definition:
                    tools = []
                    for fd in function_definition:
                        func = fd.get("function", {})
                        tools.append({
                            "type": "function",
                            "function": {
                                "name": func.get("name", ""),
                                "description": func.get("description", ""),
                                "parameters": func.get("parameters", {})
                            }
                        })
                    payload["tools"] = tools

                response = requests.post(
                    f"{LLAMA_CPP_BASE_URL}/v1/chat/completions",
                    json=payload,
                    stream=True,
                    timeout=120
                )
                response.raise_for_status()

                tool_calls_found = []

                for line in response.iter_lines():
                    if not line:
                        continue
                    line = line.decode('utf-8')
                    if line.startswith("data: "):
                        line = line[6:]
                    if line == "[DONE]":
                        break

                    try:
                        chunk = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    delta = chunk.get("choices", [{}])[0].get("delta", {})

                    thought_content = delta.get("thinking") or delta.get("thought") or ""
                    if thinking and thought_content:
                        if last_yield_type != 'thinking':
                            yield "\nThinking:\n"
                            last_yield_type = 'thinking'
                        full_content += thought_content
                        yield thought_content

                    content = delta.get("content", "")
                    if content:
                        if last_yield_type != 'content':
                            yield "\nFormal Answer:\n"
                            last_yield_type = 'content'
                        full_content += content
                        full_json_content += content
                        yield content

                    tool_calls = delta.get("tool_calls", [])
                    if tool_calls:
                        for tc in tool_calls:
                            tool_calls_found.append({
                                "function": {
                                    "name": tc.get("function", {}).get("name", ""),
                                    "arguments": tc.get("function", {}).get("arguments", {})
                                }
                            })

                error_msg = None
                parsed_data = None

                if function_definition:
                    if tool_calls_found:
                        tc = tool_calls_found[0]
                        args = tc.get('function', {}).get('arguments', {})
                        if isinstance(args, str):
                            try:
                                args = json.loads(args)
                            except:
                                error_msg = "Invalid JSON in tool call arguments."

                        if not error_msg:
                            val_err = LLMUtils.validate_schema(args, function_definition)
                            if val_err:
                                error_msg = val_err
                            else:
                                parsed_data = args
                                tc['function']['arguments'] = args
                    else:
                        try:
                            json_to_parse = full_json_content if full_json_content.strip() else full_content
                            # If full_content contains refusal text + retry JSON, extract the LAST JSON block
                            # This happens when LLM refuses (safety filter) then retries with valid JSON
                            if "{" in json_to_parse:
                                last_brace = json_to_parse.rfind("{")
                                json_to_parse = json_to_parse[last_brace:]
                            elif "[" in json_to_parse:
                                last_bracket = json_to_parse.rfind("[")
                                json_to_parse = json_to_parse[last_bracket:]
                            # Strip trailing markdown code fences (```) that LLM may append after the JSON
                            json_to_parse = json_to_parse.rstrip()
                            while json_to_parse.endswith('```'):
                                json_to_parse = json_to_parse[:-3].rstrip()
                            parsed_json = json.loads(json_to_parse)
                            val_err = LLMUtils.validate_schema(parsed_json, function_definition)
                            if val_err:
                                error_msg = val_err
                            else:
                                parsed_data = parsed_json
                                if function_definition:
                                    tc = {
                                        "index": 0,
                                        "id": "call_raw",
                                        "type": "function",
                                        "function": {
                                            "name": "answer",
                                            "arguments": parsed_json
                                        }
                                    }
                                    tool_calls_found.append(tc)
                        except json.JSONDecodeError:
                            error_msg = "Output is not valid JSON."

                elif json_response:
                    try:
                        json.loads(full_json_content if full_json_content.strip() else full_content)
                    except json.JSONDecodeError:
                        error_msg = "Output is not valid JSON."

                if not error_msg:
                    if tool_calls_found:
                        yield f"\n[TOOL_CALLS]: {json.dumps(tool_calls_found, ensure_ascii=False)}"
                    elif function_definition and 'parsed_json' in locals():
                        tc = {
                            "index": 0,
                            "id": "call_raw",
                            "type": "function",
                            "function": {
                                "name": "answer",
                                "arguments": parsed_json
                            }
                        }
                        yield f"\n[TOOL_CALLS]: {json.dumps(tc, ensure_ascii=False)}"
                    return

                else:
                    yield f"\n[VALIDATION_ERROR]: {error_msg}\n"

                    if tool_calls_found:
                        tc = tool_calls_found[0]
                        args = tc.get('function', {}).get('arguments', {})
                        if isinstance(args, str):
                            try:
                                args = json.loads(args)
                            except:
                                pass
                        yield f"\n[RECEIVED_JSON]:\n{json.dumps(args, indent=2, ensure_ascii=False, default=str)}\n"
                    elif 'parsed_json' in dir() and parsed_json:
                        yield f"\n[RECEIVED_JSON]:\n{json.dumps(parsed_json, indent=2, ensure_ascii=False, default=str)}\n"
                    elif 'json_to_parse' in dir():
                        yield f"\n[RECEIVED_JSON]:\n{json_to_parse}\n"

                    messages.append({'role': 'assistant', 'content': full_content})
                    if tool_calls_found:
                        messages[-1]['tool_calls'] = tool_calls_found

                    retry_prompt = f"Your previous response had the following error: {error_msg}. Please correct it and ensure it follows the schema/format perfectly."
                    yield f"\n[RETRY_PROMPT]: {retry_prompt}\n"
                    messages.append({'role': 'user', 'content': retry_prompt})

                    if attempt == max_retries - 1:
                        yield f"Error: Failed to get valid response after {max_retries} attempts. Last error: {error_msg}"

            except Exception as e:
                yield f"Error during llama.cpp call: {str(e)}\n"
                if 'response' in dir():
                    try:
                        yield f"[DEBUG] Response: {response}\n"
                    except:
                        yield "[DEBUG] Could not serialize response object\n"
                if tool_calls_found:
                    yield f"\n[DEBUG] Tool calls found: {len(tool_calls_found)}\n"
                    for i, tc in enumerate(tool_calls_found):
                        try:
                            yield f"[DEBUG] Tool call {i}: {json.dumps(tc, indent=2, ensure_ascii=False, default=str)}\n"
                        except:
                            yield f"[DEBUG] Tool call {i}: (could not serialize)\n"
                return

if __name__ == "__main__":
    print("LLMUtils loaded.")
