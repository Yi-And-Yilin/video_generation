import sys
sys.path.insert(0, r"C:\SimpleAIHelper\video_generation")

from llm_conversation import render_md_template, LLMUtils, Conversation
import json

md_path = "prompts/scene_design.md"
json_path = "prompts/scene_design.json"

system_prompt = render_md_template(
    md_path,
    user_requirements="A romantic scene in a cozy library at night",
    male_character="Adult, French, Tall, Slim, Charming",
    female_character="Young, British, Short, Slender, Intelligent"
)

with open(json_path, "r", encoding="utf-8") as f:
    tool_schema = json.load(f)

print("=== System Prompt ===")
print(system_prompt)

print("\n=== Tool Schema Loaded ===")
print(f"Tool name: {tool_schema[0]['function']['name']}")

conv = Conversation(system_prompt=system_prompt, tool_schema=tool_schema)
llm = LLMUtils(base_url="http://localhost:8081", model="qwen")

print("\n=== Sending chat request ===")
result_collected = ""
for chunk in llm.chat(conv, "Design a romantic library scene", chat_mode="json"):
    result_collected += chunk
    print(chunk, end="")

print("\n\n=== Conversation Messages ===")
for i, msg in enumerate(conv.get_messages()):
    role = msg['role']
    content = msg.get('content', '')[:200] if msg.get('content') else ''
    tool_calls = msg.get('tool_calls', [])
    print(f"Msg {i}: role={role}, content={content}..., tool_calls={len(tool_calls) if tool_calls else 0}")