import requests
import json
import re
import logging
from typing import List, Dict, Any, Optional, Generator
from pathlib import Path


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


LLM_BASE_URL = "http://localhost:8081"
LLAMA_CPP_BASE_URL = LLM_BASE_URL


def render_md_template(md_file_path: str, **kwargs) -> str:
    """
    Reads a markdown file and replaces {{variable}} placeholders with provided values.
    """
    path = Path(md_file_path)
    if not path.exists():
        raise FileNotFoundError(f"Template file not found: {md_file_path}")

    content = path.read_text(encoding="utf-8")

    pattern = re.compile(r'\{\{(\w+)\}\}')

    def replacer(match):
        key = match.group(1)
        if key in kwargs:
            return str(kwargs[key])
        return match.group(0)

    return pattern.sub(replacer, content)


class LLMUtils:
    def __init__(
        self,
        base_url: str = LLM_BASE_URL,
        model: str = "qwen",
        context_window: int = 40000,
        reasoning_budget: Optional[int] = None,
        reasoning_budget_message: Optional[str] = None,
        enable_thinking: bool = False,
        thinking_stop_token_bias: Optional[float] = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.context_window = context_window
        self.reasoning_budget = reasoning_budget
        self.reasoning_budget_message = reasoning_budget_message
        self.enable_thinking = enable_thinking
        self.thinking_stop_token_bias = thinking_stop_token_bias

    def chat(
        self,
        conversation: "Conversation",
        message: str,
        chat_mode: str = "test",
        max_retries: int = 1
    ) -> Generator[str, None, None]:
        """
        Sends a message to the LLM and streams the response.
        conversation: Conversation object with messages, system prompt, and tool schema
        message: user message string
        chat_mode: "test" (plain text) or "json" (validated JSON with tool schema)
        max_retries: max validation retries (default 3)
        """
        logger.info(f"[CHAT] Starting chat in '{chat_mode}' mode with max_retries={max_retries}")
        logger.info(f"[CHAT] Message: {message[:200]}...")

        conversation.add_user_message(message)

        for attempt in range(max_retries):
            logger.info(f"[CHAT] Attempt {attempt + 1}/{max_retries}")

            full_response = ""
            full_json_content = ""

            try:
                payload = {
                    "model": self.model,
                    "messages": conversation.to_llm_messages(),
                    "stream": True,
                    "options": {
                        "num_ctx": self.context_window
                    }
                }

                # Add reasoning budget parameters (top-level, llama.cpp specific)
                if self.reasoning_budget is not None:
                    payload["reasoning_budget"] = self.reasoning_budget
                if self.reasoning_budget_message:
                    payload["reasoning_budget_message"] = self.reasoning_budget_message

                # Add enable_thinking via chat_template_kwargs
                if self.enable_thinking is not None:
                    payload["chat_template_kwargs"] = {"enable_thinking": self.enable_thinking}

                # Add thinking_stop_token_bias (pseudo-budget via logit bias)
                if self.thinking_stop_token_bias is not None:
                    # Qwen uses token 151649 as </s> / end-of-thought marker
                    # Positive bias makes the model more likely to end thinking
                    payload["logits_bias"] = {151649: self.thinking_stop_token_bias}

                if chat_mode == "json" and conversation.tool_schema:
                    payload["format"] = "json"
                    if isinstance(conversation.tool_schema, list) and len(conversation.tool_schema) > 0:
                        tools = []
                        for fd in conversation.tool_schema:
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
                        payload["tool_choice"] = "auto"

                logger.info(f"[CHAT] Sending request to {self.base_url}/v1/chat/completions")
                logger.info(f"[CHAT] Payload messages: {json.dumps(payload.get('messages', [])[:2], ensure_ascii=False, indent=2)}")
                logger.info(f"[CHAT] Payload tools: {json.dumps(payload.get('tools', [])[:1], ensure_ascii=False, indent=2) if payload.get('tools') else 'none'}")

                response = requests.post(
                    f"{self.base_url}/v1/chat/completions",
                    json=payload,
                    stream=True,
                    timeout=120
                )
                response.raise_for_status()

                tool_calls_found = []
                reasoning_content = ""
                current_function_name = ""
                current_arguments = ""

                logger.info("[CHAT] Starting to parse response stream...")
                for line in response.iter_lines():
                    if not line:
                        continue
                    line = line.decode('utf-8')
                    if line.startswith("data: "):
                        line = line[6:]
                    if line == "[DONE]":
                        logger.info("[CHAT] Received [DONE] signal")
                        break

                    logger.debug(f"[CHAT] Raw line: {line}")
                    try:
                        chunk = json.loads(line)
                        logger.debug(f"[CHAT] Parsed chunk keys: {list(chunk.keys())}")

                        delta = chunk.get("choices", [{}])[0].get("delta", {})
                        logger.debug(f"[CHAT] Delta keys: {list(delta.keys())}")

                        reasoning = delta.get("reasoning_content") or delta.get("thinking") or delta.get("thought") or ""
                        if reasoning:
                            reasoning_content += reasoning
                            logger.debug(f"[CHAT] Found reasoning_content: {reasoning[:100]}...")

                        content = delta.get("content", "")
                        if content:
                            logger.debug(f"[CHAT] Found content: {content[:100]}...")
                            full_response += content
                            full_json_content += content
                            yield content

                        func_call = delta.get("function_call")
                        if func_call:
                            logger.debug(f"[CHAT] Found function_call: {json.dumps(func_call, ensure_ascii=False)[:200]}")
                            fn_name = func_call.get("name", "")
                            fn_args = func_call.get("arguments", "")
                            if fn_name:
                                current_function_name = fn_name
                            if fn_args:
                                current_arguments += fn_args

                        tool_calls_delta = delta.get("tool_calls", [])
                        for tc in tool_calls_delta:
                            func_data = tc.get("function", {})
                            fn_name = func_data.get("name", "")
                            fn_args = func_data.get("arguments", "")
                            if fn_name:
                                current_function_name = fn_name
                            if fn_args:
                                current_arguments += fn_args

                    except json.JSONDecodeError as e:
                        logger.warning(f"[CHAT] Failed to parse JSON: {e}")

                logger.info(f"[CHAT] LLM Response: {full_response}")

                if reasoning_content:
                    logger.info(f"[CHAT] Full reasoning content:\n{reasoning_content}")

                if current_function_name and current_arguments:
                    tool_calls_found = [{
                        "index": 0,
                        "id": "call_0",
                        "type": "function",
                        "function": {
                            "name": current_function_name,
                            "arguments": current_arguments
                        }
                    }]
                    logger.info(f"[CHAT] Built tool_call from chunks: {json.dumps(tool_calls_found, ensure_ascii=False)}")

                parsed_data = None
                validation_error = None

                if chat_mode == "json" and conversation.tool_schema:
                    logger.info("[CHAT] Validating JSON response against schema")

                    if tool_calls_found:
                        logger.info(f"[CHAT] Tool calls found: {len(tool_calls_found)}")
                        logger.info(f"[CHAT] Tool call content: {json.dumps(tool_calls_found, ensure_ascii=False)}")
                        tc = tool_calls_found[0]
                        func_data = tc.get('function', {})
                        fn_name = func_data.get("name", "")
                        fn_args_str = func_data.get("arguments", "")
                        
                        logger.info(f"[CHAT] Function name: {fn_name}, arguments type: {type(fn_args_str)}")
                        logger.info(f"[CHAT] Raw arguments length: {len(fn_args_str)}, first 200: {repr(fn_args_str[:200])}")
                        
                        args = fn_args_str
                        if isinstance(args, str):
                            try:
                                args = json.loads(args)
                                logger.info(f"[CHAT] Parsed tool arguments from string: {args}")
                            except:
                                validation_error = "Invalid JSON in tool call arguments."
                                logger.warning(f"[CHAT] Failed to parse tool arguments: {fn_args_str}")

                        if not validation_error:
                            val_err = LLMUtils._validate_schema(args, conversation.tool_schema)
                            if val_err:
                                validation_error = val_err
                                logger.warning(f"[CHAT] Schema validation failed: {val_err}")
                            else:
                                parsed_data = args
                                tc['function']['arguments'] = args
                                logger.info("[CHAT] Schema validation passed")
                    else:
                        logger.info("[CHAT] No tool calls, validating as plain JSON")
                        try:
                            json_to_parse = full_json_content if full_json_content.strip() else full_response
                            logger.info(f"[CHAT] full_json_content length: {len(full_json_content)}, first 200 chars: {repr(full_json_content[:200])}")
                            logger.info(f"[CHAT] full_response length: {len(full_response)}, first 200 chars: {repr(full_response[:200])}")
                            logger.info(f"[CHAT] current_arguments: {repr(current_arguments[:200])}")
                            # First try: parse the full content directly
                            try:
                                parsed_json = json.loads(json_to_parse)
                                logger.info("[CHAT] First parse attempt succeeded")
                            except json.JSONDecodeError as e:
                                logger.warning(f"[CHAT] First parse attempt FAILED: {e}")
                                # Second try: LLM may have output refusal text + retry JSON
                                # Find the FIRST { or [ to extract the JSON block
                                brace_idx = json_to_parse.find("{")
                                bracket_idx = json_to_parse.find("[")
                                if brace_idx >= 0 and bracket_idx >= 0:
                                    start = min(brace_idx, bracket_idx)
                                elif brace_idx >= 0:
                                    start = brace_idx
                                elif bracket_idx >= 0:
                                    start = bracket_idx
                                else:
                                    raise json.JSONDecodeError("No JSON delimiter found", json_to_parse, 0)
                                extracted = json_to_parse[start:]
                                # Strip trailing markdown code fences (```) that LLM may append
                                extracted = re.sub(r'\s*```\s*$', '', extracted)
                                logger.info(f"[CHAT] Extracted JSON from index {start}, length: {len(extracted)}, first 200: {repr(extracted[:200])}")
                                try:
                                    parsed_json = json.loads(extracted)
                                    logger.info("[CHAT] Second parse attempt succeeded")
                                except json.JSONDecodeError as e2:
                                    logger.warning(f"[CHAT] Second parse attempt FAILED: {e2}")
                                    raise e2
                            val_err = LLMUtils._validate_schema(parsed_json, conversation.tool_schema)
                            if val_err:
                                validation_error = val_err
                                logger.warning(f"[CHAT] JSON schema validation failed: {val_err}")
                            else:
                                parsed_data = parsed_json
                                logger.info("[CHAT] JSON schema validation passed")
                        except json.JSONDecodeError as e:
                            validation_error = "Output is not valid JSON."
                            logger.warning(f"[CHAT] JSON decode error: {e}")

                if chat_mode == "json" and not validation_error:
                    logger.info("[CHAT] Validation passed, adding assistant message to conversation")
                    assistant_msg = {"role": "assistant", "content": full_response}

                    # If raw JSON was parsed (no tool_calls from API), wrap it as a tool call
                    # so downstream parsers can find [TOOL_CALLS]:
                    if parsed_data and not tool_calls_found:
                        wrapped_tc = {
                            "index": 0,
                            "id": "call_raw",
                            "type": "function",
                            "function": {
                                "name": "answer",
                                "arguments": parsed_data
                            }
                        }
                        tool_calls_found = [wrapped_tc]
                        logger.info("[CHAT] Wrapped raw JSON as tool_calls")

                    if tool_calls_found:
                        assistant_msg["tool_calls"] = tool_calls_found
                        logger.info(f"[CHAT] Returning tool calls: {json.dumps(tool_calls_found, ensure_ascii=False)}")
                        yield f"\n[TOOL_CALLS]: {json.dumps(tool_calls_found, ensure_ascii=False)}"
                    return parsed_data

                if validation_error:
                    logger.warning(f"[CHAT] Validation failed: {validation_error}")
                    yield f"\n[VALIDATION_ERROR]: {validation_error}\n"

                    if tool_calls_found:
                        tc = tool_calls_found[0]
                        args = tc.get('function', {}).get('arguments', {})
                        if isinstance(args, str):
                            try:
                                args = json.loads(args)
                            except:
                                pass
                        yield f"\n[RECEIVED_JSON]:\n{json.dumps(args, indent=2, ensure_ascii=False, default=str)}\n"
                    elif parsed_data is not None:
                        yield f"\n[RECEIVED_JSON]:\n{json.dumps(parsed_data, indent=2, ensure_ascii=False, default=str)}\n"
                    elif full_json_content.strip():
                        yield f"\n[RECEIVED_JSON]:\n{full_json_content}\n"

                    logger.info(f"[CHAT] Adding retry message to conversation")
                    conversation.add_user_message(f"Your previous response had the following error: {validation_error}. Please correct it and ensure it follows the schema/format perfectly.")

                    if attempt == max_retries - 1:
                        logger.error(f"[CHAT] Failed after {max_retries} attempts, returning None")
                        yield f"\n[Error]: Failed to get valid response after {max_retries} attempts."
                        conversation.add_assistant_message({"role": "assistant", "content": full_response})
                        return None

            except Exception as e:
                logger.error(f"[CHAT] Exception during LLM call: {str(e)}")
                yield f"\n[Error]: {str(e)}\n"
                conversation.add_assistant_message({"role": "assistant", "content": full_response if full_response else f"[Error: {str(e)}]"})
                return None

    @staticmethod
    def _validate_schema(data: Any, schema_input: Any) -> Optional[str]:
        """Validates data against function definition schema."""
        if not isinstance(data, dict):
            return "Output must be a JSON object."

        if not schema_input:
            return None

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

        for key, value in data.items():
            if key in properties:
                expected_type = properties[key].get("type")

                if (expected_type == "array" and not isinstance(value, list)) or \
                   (expected_type == "object" and not isinstance(value, dict)):
                    if isinstance(value, str):
                        candidate = value.strip().strip("'").strip("\"").strip()
                        candidate = candidate.replace("\\n", "").replace("\n", "")

                        if (expected_type == "array" and candidate.startswith("[") and candidate.endswith("]")) or \
                           (expected_type == "object" and candidate.startswith("{") and candidate.endswith("}")):
                            try:
                                fixed_value = json.loads(candidate)
                                if (expected_type == "array" and isinstance(fixed_value, list)) or \
                                   (expected_type == "object" and isinstance(fixed_value, dict)):
                                    data[key] = fixed_value
                                    value = fixed_value
                                    continue
                            except:
                                pass

                if expected_type == "array" and not isinstance(value, list):
                    return f"Property '{key}' should be a list/array."
                elif expected_type == "string" and not isinstance(value, str):
                    return f"Property '{key}' should be a string."
                elif expected_type == "object" and not isinstance(value, dict):
                    return f"Property '{key}' should be an object."

        return None


class Conversation:
    def __init__(self, system_prompt: str, tool_schema: Optional[List[Dict] | Dict] = None):
        self.system_prompt = system_prompt
        self.tool_schema = tool_schema
        self.messages: List[Dict[str, Any]] = []

    def add_user_message(self, content: str):
        self.messages.append({"role": "user", "content": content})

    def add_assistant_message(self, message: Dict[str, Any]):
        self.messages.append(message)

    def to_llm_messages(self) -> List[Dict[str, Any]]:
        result = []
        if self.system_prompt:
            result.append({"role": "system", "content": self.system_prompt})
        result.extend(self.messages)
        return result

    def clear(self):
        self.messages = []

    def get_messages(self) -> List[Dict[str, Any]]:
        return self.messages.copy()