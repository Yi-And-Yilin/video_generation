import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from image_prompt_generator import generate_prompts_for_task


if __name__ == "__main__":
    task_path = sys.argv[1] if len(sys.argv) >= 2 else "tasks/92bk9/task.json"
    prompts, male_str, female_str = generate_prompts_for_task(task_path)

    print("=" * 60)
    print("Male character string:", male_str)
    print("Female character string:", female_str)
    print("=" * 60)

    for p in prompts:
        print(f"\nLocation: {p['location']}")
        print(f"Prompt: {p['prompt']}")
        print("-" * 60)