from llm_utils import LLMUtils

def test_thinking_toggle():
    prompt = "Why is the sky blue?"
    model = "huihui_ai/qwen3.5-abliterated:9b"
    
    print("=== PASS 1: thinking=True ===")
    for chunk in LLMUtils.stream(prompt=prompt, model=model, thinking=True):
        print(chunk, end='', flush=True)
    print("\n")

    print("=== PASS 2: thinking=False ===")
    for chunk in LLMUtils.stream(prompt=prompt, model=model, thinking=False):
        print(chunk, end='', flush=True)
    print("\n")

if __name__ == "__main__":
    test_thinking_toggle()
