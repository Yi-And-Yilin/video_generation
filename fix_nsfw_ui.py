import re

file_path = "nsfw_ui.py"
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Fix broken multi-line string literals with " # Corrected: " comments.
# This pattern matches across multiple lines.
# It looks for something like: " \n something " # Corrected: " \n something "
# and tries to restore it to its original state.

# Let's target the specific broken f-strings first.
content = re.sub(r'f"\{system_prompt\}\n\n\{full_user_prompt\}" # Corrected: "\n\n"', r'f"{system_prompt}\\n\\n{full_user_prompt}"', content)
content = re.sub(r'f"\{user_prompt_template\}\n\nUser Instruction from UI: \{user_instruction\}" # Corrected: "\n\n"', r'f"{user_prompt_template}\\n\\nUser Instruction from UI: {user_instruction}"', content)

# General fixes for other patterns
content = re.sub(r' \+ "\n"\) # Corrected: "\n"\n"', r' + "\\n")', content)
content = re.sub(r"'\n'\) # Corrected: '\n'\n'", r"'\\n')", content)
content = re.sub(r"'\n'\) # Corrected: delimiter='\n'\n'", r"'\\t')", content)
content = re.sub(r'f"\[\{timestamp\}\] \{message\}"\n\s+# Also write to file\n\s+try:\n\s+with open\(LTX_LOG_FILE, \'a\', encoding=\'utf-8\'\) as f:\n\s+f\.write\(full_message \+ "\n"\) # Corrected: "\n"\n"', 
                 lambda m: m.group(0).replace('"\n") # Corrected: "\n"\n"', '"\\n")'), content)

# Wait, the f.write one is still broken in L1237.
# Let's just do a very broad replacement.
content = re.sub(r'"\n"\) # Corrected: "\n"\n"', r'"\\n")', content)
content = re.sub(r"'\n'\) # Corrected: '\n'\n'", r"'\\n')", content)
content = re.sub(r"'\n'\) # Corrected: delimiter='\n'\n'", r"'\\t')", content)

# Fix prompt tab generation complete message
content = re.sub(r'self\._prompt_log\("\n--- Generation Complete ---\"\) # Corrected: \"\n"', r'self._prompt_log("\\n--- Generation Complete ---")', content)

# Fix conversation log
content = re.sub(r'f"""\n\{separator\}\n\[\{timestamp\}\] Template: \{template_name\}\n\{separator\}\n\n========== PROMPT SENT TO LLM ==========\n\{prompt\}\n\n========== LLM RESPONSE \(including thinking\) ==========\n\{response\}\n\n""" # Corrected: "\n"', 
                 r'f"""\n{separator}\n[{timestamp}] Template: {template_name}\n{separator}\n\n========== PROMPT SENT TO LLM ==========\n{prompt}\n\n========== LLM RESPONSE (including thinking) ==========\n{response}\n\n"""', content)

# Fix image tab log
content = re.sub(r'str\(item\) \+ "\n"\)\n # Corrected: "\n"\n"', r'str(item) + "\\n")\n', content)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)

print("Fix script completed.")
