from llm_utils import LLMUtils
import json
import os

def test_function_calling_validation():
    # Load schema
    schema_path = "mock_schema.json"
    with open(schema_path, "r") as f:
        schema = json.load(f)
    
    # Mock prompt that should trigger the tool call
    prompt = "Please generate an image prompt for a 'cyberpunk city at night' in a 'digital art' style with tags like 'neon', 'rain', 'flying cars'."
    
    print(f"Testing validation with prompt: {prompt}")
    print("Function Definition:", json.dumps(schema, indent=2))
    print("--- Stream Start ---")
    
    full_output = ""
    try:
        for chunk in LLMUtils.stream(
            prompt=prompt,
            model="huihui_ai/qwen3.5-abliterated:9b",
            thinking=True,
            context_window=65536,
            json_response=False,
            function_definition=schema
        ):
            print(chunk, end='', flush=True)
            full_output += chunk
    except Exception as e:
        print(f"\nError occurred: {e}")
        
    print("\n--- Stream End ---")
    
    # Verification of the result
    if "[TOOL_CALLS]" in full_output:
        print("\nSuccess: Tool call was generated and validated.")
    else:
        # Check if it returned JSON instead (some models might just return JSON if tools are requested)
        try:
            json.loads(full_output)
            print("\nSuccess: Valid JSON was returned and validated against schema.")
        except:
            print("\nFailure: Output did not contain a valid tool call or JSON.")

if __name__ == "__main__":
    test_function_calling_validation()
