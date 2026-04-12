import ollama
import json

def test_raw_response():
    model = "huihui_ai/qwen3.5-abliterated:9b"
    prompt = "Why is the sky blue? (Please include your thinking process)"
    
    print(f"Testing raw response from {model}...")
    
    response = ollama.chat(
        model=model,
        messages=[{'role': 'user', 'content': prompt}],
        stream=True
    )
    
    for chunk in response:
        # Print the entire chunk dictionary to see all fields
        print(json.dumps(chunk, default=str))
        if 'message' in chunk:
            content = chunk['message'].get('content', '')
            if content:
                # We don't want to flood the screen with content, just the first bit
                # print(f"CONTENT: {content}")
                pass

if __name__ == "__main__":
    test_raw_response()
