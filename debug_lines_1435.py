
with open('nsfw_ui.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

for i in range(1435, 1445):
    if i < len(lines):
        print(f"L{i+1}: {repr(lines[i])}")
