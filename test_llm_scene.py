#!/usr/bin/env python3
"""Test JSON parsing with actual LLM API call."""

import json
import requests

BASE_URL = "http://localhost:8081"

def test_scene_design():
    """Test scene design LLM call."""
    
    # Simple tool schema
    tool_schema = {
        "type": "function",
        "function": {
            "name": "answer",
            "description": "Design locations",
            "parameters": {
                "type": "object",
                "properties": {
                    "locations": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "location": {"type": "string"},
                                "time": {"type": "string"},
                                "lighting": {"type": "string"},
                                "prompts": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "sex_act": {"type": "string"},
                                            "prompt": {"type": "string"}
                                        }
                                    }
                                }
                            }
                        }
                    }
                },
                "required": ["locations"]
            }
        }
    }
    
    system_prompt = """You are an expert scene designer. Design locations with time, lighting, and prompts.

CRITICAL FORMAT:
{
  "locations": [
    {
      "location": "Bedroom",
      "time": "night",
      "lighting": "dim candlelight",
      "prompts": [
        {"sex_act": "kissing", "prompt": "Detailed description..."}
      ]
    }
  ]
}

Call the `answer` tool with the exact JSON format above."""
    
    payload = {
        "model": "hauhau",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "Design a bedroom scene for a romantic couple."}
        ],
        "stream": True,
        "options": {"num_ctx": 40000},
        "format": "json",
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": tool_schema["function"]["name"],
                    "description": tool_schema["function"]["description"],
                    "parameters": tool_schema["function"]["parameters"]
                }
            }
        ],
        "tool_choice": "auto"
    }
    
    print("=" * 60)
    print("TESTING LLM SCENE DESIGN")
    print("=" * 60)
    
    response = requests.post(
        f"{BASE_URL}/v1/chat/completions",
        json=payload,
        stream=True,
        timeout=300
    )
    response.raise_for_status()
    
    full_response = ""
    full_json_content = ""
    tool_calls_found = []
    current_function_name = ""
    current_arguments = ""
    
    for line in response.iter_lines():
        if not line:
            continue
        line = line.decode('utf-8')
        if line.startswith("data: "):
            line = line[6:]
        if line == "[DONE]":
            print("\n=== [DONE] ===")
            break
        
        try:
            chunk = json.loads(line)
            delta = chunk.get("choices", [{}])[0].get("delta", {})
            
            content = delta.get("content", "")
            if content:
                full_response += content
                full_json_content += content
                print(content, end="", flush=True)
            
            tool_calls_delta = delta.get("tool_calls", [])
            for tc in tool_calls_delta:
                func_data = tc.get("function", {})
                fn_name = func_data.get("name", "")
                fn_args = func_data.get("arguments", "")
                if fn_name:
                    current_function_name = fn_name
                if fn_args:
                    current_arguments += fn_args
                    
        except json.JSONDecodeError:
            pass
    
    print("\n\n=== POST-STREAM ANALYSIS ===")
    print(f"full_response length: {len(full_response)}")
    print(f"full_json_content length: {len(full_json_content)}")
    print(f"current_arguments length: {len(current_arguments)}")
    print(f"current_function_name: {current_function_name}")
    print()
    print(f"full_response first 200: {repr(full_response[:200])}")
    print(f"full_json_content first 200: {repr(full_json_content[:200])}")
    print(f"current_arguments first 200: {repr(current_arguments[:200])}")
    print()
    
    # Test JSON parsing like llm_conversation.py does
    print("=== JSON PARSING TEST ===")
    
    if current_arguments:
        print(f"Trying to parse current_arguments ({len(current_arguments)} chars)...")
        try:
            args_parsed = json.loads(current_arguments)
            print(f"SUCCESS: {json.dumps(args_parsed, indent=2)[:500]}")
        except json.JSONDecodeError as e:
            print(f"FAILED: {e}")
    else:
        print("current_arguments empty, trying full_json_content...")
        try:
            parsed = json.loads(full_json_content)
            print(f"SUCCESS: {json.dumps(parsed, indent=2)[:500]}")
        except json.JSONDecodeError as e:
            print(f"FAILED: {e}")
            print(f"Raw full_json_content: {repr(full_json_content[:500])}")

if __name__ == "__main__":
    test_scene_design()
