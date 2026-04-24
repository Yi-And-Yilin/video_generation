
with open('main_ui.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if '# Corrected:' in line:
        print(f"L{i+1}: {repr(line)}")
        if i > 0:
            print(f"L{i}: {repr(lines[i-1])}")
        if i < len(lines) - 1:
            print(f"L{i+2}: {repr(lines[i+1])}")
        print("-" * 20)
