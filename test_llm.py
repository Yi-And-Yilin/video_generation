from llm_utils import LLMUtils
import sys

def test_stream():
    prompt = "Hi, can you introduce yourself?"
    model = "huihui_ai/qwen3.5-abliterated:9b"
    context_window = 65536
    
    print(f"Testing stream with model: {model}")
    print("--- Response Start ---")
    
    try:
        for chunk in LLMUtils.stream(
            prompt=prompt,
            model=model,
            thinking=True,
            context_window=context_window,
            json_response=False
        ):
            print(chunk, end='', flush=True)
    except Exception as e:
        print(f"\nError occurred: {e}")
        
    print("\n--- Response End ---")

def test_json_response():
    prompt = "List 3 colors in JSON format with a 'colors' key."
    model = "huihui_ai/qwen3.5-abliterated:9b"
    
    print(f"\nTesting JSON response with model: {model}")
    print("--- JSON Response Start ---")
    
    full_response = ""
    try:
        for chunk in LLMUtils.stream(
            prompt=prompt,
            model=model,
            thinking=True,
            context_window=4096,
            json_response=True
        ):
            print(chunk, end='', flush=True)
            full_response += chunk
    except Exception as e:
        print(f"\nError occurred: {e}")
        
    print("\n--- JSON Response End ---")

if __name__ == "__main__":
    test_stream()
    # Uncomment the line below to test JSON response
    # test_json_response()
