import ollama
import json
from typing import List, Dict, Any, Optional, Generator

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
        model: str = "huihui_ai/qwen3.5-abliterated:9b",
        thinking: bool = True,
        context_window: int = 65536,
        json_response: bool = False,
        function_definition: Optional[List[Dict[str, Any]]] = None,
        keep_alive: Any = None
    ) -> Generator[str, None, None]:
        """
        Streams response from a local Ollama instance with internal retry and validation logic.
        """
        messages = [
            {'role': 'user', 'content': prompt}
        ]
        
        options = {"num_ctx": context_window}
        format_param = 'json' if (json_response or function_definition) else ''
        
        # Default keep_alive if not provided
        if keep_alive is None:
            keep_alive = "5m" # Default Ollama timeout
            
        max_retries = 5
        
        for attempt in range(max_retries):
            full_content = ""      # Combined content for logging/history
            full_json_content = "" # Specifically content field for JSON parsing
            current_response_chunks = []
            last_yield_type = None # Track 'thinking' vs 'content'
            
            try:
                response = ollama.chat(
                    model=model,
                    messages=messages,
                    stream=True,
                    options=options,
                    format=format_param,
                    tools=function_definition,
                    keep_alive=keep_alive
                )
                
                tool_calls_found = []
                
                for chunk in response:
                    msg = chunk.get('message', {})
                    current_response_chunks.append(chunk)
                    
                    # Handle thinking/thought field
                    thought_content = msg.get('thought') or msg.get('thinking') or ""
                    if thinking and thought_content:
                        if last_yield_type != 'thinking':
                            yield "\nThinking:\n"
                            last_yield_type = 'thinking'
                        full_content += thought_content
                        yield thought_content
                    
                    # Handle content field
                    content = msg.get('content', '')
                    if content:
                        if last_yield_type != 'content':
                            yield "\nFormal Answer:\n"
                            last_yield_type = 'content'
                        full_content += content
                        full_json_content += content
                        yield content
                    
                    if msg.get('tool_calls'):
                        tool_calls_found.extend(msg['tool_calls'])
                        # We don't yield TOOL_CALLS label here yet to keep stream clean
                        # but we might want to if it's the only thing returned.

                # Validation Logic
                error_msg = None
                parsed_data = None
                
                if function_definition:
                    if tool_calls_found:
                        # Validate the FIRST tool call for simplicity in this workflow
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
                                # Update the tool call with potentially auto-fixed args
                                tc['function']['arguments'] = args
                    else:
                        try:
                            # Use full_json_content if available, fallback to full_content
                            json_to_parse = full_json_content if full_json_content.strip() else full_content
                            parsed_json = json.loads(json_to_parse)
                            val_err = LLMUtils.validate_schema(parsed_json, function_definition)
                            if val_err:
                                error_msg = val_err
                            else:
                                parsed_data = parsed_json
                        except json.JSONDecodeError:
                            error_msg = "Output is not valid JSON."
                
                elif json_response:
                    try:
                        json.loads(full_json_content if full_json_content.strip() else full_content)
                    except json.JSONDecodeError:
                        error_msg = "Output is not valid JSON."

                if not error_msg:
                    # Success!
                    if tool_calls_found:
                        # Re-yield the tool calls if they were the primary output
                        # (though in this project we usually parse the saved task.json)
                        yield f"\n[TOOL_CALLS]: {json.dumps(tool_calls_found, ensure_ascii=False)}"
                    return
                
                else:
                    # Failure - Log to stream
                    yield f"\n[VALIDATION_ERROR]: {error_msg}\n"
                    
                    # Show the actual JSON that failed validation
                    if tool_calls_found:
                        tc = tool_calls_found[0]
                        # Handle both dict and ToolCall object
                        if hasattr(tc, 'function'):
                            args = tc.function.arguments if hasattr(tc.function, 'arguments') else {}
                        else:
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
                yield f"Error during Ollama call: {str(e)}\n"
                # Print the response object for debugging
                yield f"\n[DEBUG] Response object type: {type(response)}\n"
                try:
                    # Try to print response details
                    if 'response' in dir():
                        yield f"[DEBUG] Response: {response}\n"
                except:
                    yield "[DEBUG] Could not serialize response object\n"
                # Print tool_calls_found if available
                if tool_calls_found:
                    yield f"\n[DEBUG] Tool calls found: {len(tool_calls_found)}\n"
                    for i, tc in enumerate(tool_calls_found):
                        try:
                            yield f"[DEBUG] Tool call {i}: {json.dumps(tc, indent=2, ensure_ascii=False, default=str)}\n"
                        except:
                            yield f"[DEBUG] Tool call {i}: (could not serialize)\n"
                # Print current_response_chunks
                if current_response_chunks:
                    yield f"\n[DEBUG] Chunks collected: {len(current_response_chunks)}\n"
                    try:
                        yield f"[DEBUG] Last few chunks: {current_response_chunks[-5:]}\n"
                    except:
                        pass
                return

if __name__ == "__main__":
    print("LLMUtils loaded.")
