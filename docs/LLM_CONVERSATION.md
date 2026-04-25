# LLM Conversation Module User Guide

## Overview

`llm_conversation.py` provides utilities for interacting with local LLM servers (llama.cpp) that expose an OpenAI-compatible API. It supports streaming responses, tool/function calling, and JSON schema validation.

## Requirements

- Local llama.cpp server running (default: `http://localhost:8081`)
- Model name (default: `qwen`)
- Python 3.8+

## Quick Start

```python
from llm_conversation import LLMUtils, Conversation

llm = LLMUtils(base_url="http://localhost:8081", model="qwen")
conv = Conversation(system_prompt="You are a helpful assistant.")

for chunk in llm.chat(conv, "Hello, how are you?"):
    print(chunk, end="")
```

## API Reference

### render_md_template()

Reads a markdown file and replaces `{{variable}}` placeholders with provided values.

```python
from llm_conversation import render_md_template

prompt = render_md_template(
    "prompts/my_prompt.md",
    user_requirements="A romantic scene",
    male_character="Adult, Tall",
    female_character="Young, Short"
)
```

**Parameters:**
- `md_file_path` (str): Path to markdown template file
- `**kwargs`: Variable substitutions for `{{variable}}` placeholders

**Returns:** String with placeholders replaced

---

### LLMUtils Class

#### Constructor

```python
LLMUtils(
    base_url: str = "http://localhost:8081",
    model: str = "qwen",
    context_window: int = 40000,
    reasoning_budget: Optional[int] = None,
    reasoning_budget_message: Optional[str] = None,
    enable_thinking: Optional[bool] = None,
    thinking_stop_token_bias: Optional[float] = None
)
```

**Parameters:**
- `base_url`: llama.cpp server URL
- `model`: Model name (e.g., "qwen")
- `context_window`: Context window size in tokens (default: 40000)
- `reasoning_budget`: Maximum thinking tokens as integer (e.g., 500). **Note:** llama.cpp may not fully enforce this (known regression in builds before 8744).
- `reasoning_budget_message`: Optional message injected when budget is reached
- `enable_thinking`: Set to `True` to enable thinking/reasoning (default: `False` — reasoning disabled)
- `thinking_stop_token_bias`: Pseudo-budget via logit bias (e.g., 0.5–1.0). Makes the model more likely to close its thinking early without a hard limit. Recommended range: `0.5` to `1.0`.

---

#### chat() Method

```python
chat(
    conversation: Conversation,
    message: str,
    chat_mode: str = "test",
    max_retries: int = 1
) -> Generator[str, None, None]
```

Sends a message to the LLM and streams the response.

**Parameters:**
- `conversation`: Conversation object containing system prompt, tool schema, and message history
- `message`: User message string
- `chat_mode`: `"test"` for plain text, `"json"` for validated JSON with tool schema
- `max_retries`: Number of validation retry attempts (default: 1)

**Yields:**
- Response chunks as strings
- On validation failure: `[VALIDATION_ERROR]: <error message>`
- On success (json mode): `[TOOL_CALLS]: <json>` and returns parsed data

---

### Conversation Class

#### Constructor

```python
Conversation(
    system_prompt: str,
    tool_schema: Optional[List[Dict] | Dict] = None
)
```

**Parameters:**
- `system_prompt`: System prompt string
- `tool_schema`: JSON schema for tool/function calling (OpenAI format). Accepts either a `dict` or a `list` of schemas. Both formats are automatically normalized to a list internally.

#### Methods

```python
add_user_message(content: str)       # Add user message to history
add_assistant_message(message: Dict)  # Add assistant message to history
to_llm_messages() -> List[Dict]      # Convert to LLM message format
clear()                              # Clear message history
get_messages() -> List[Dict]         # Get copy of messages
```

---

## Usage Examples

### Example 1: Simple Chat (Plain Text)

```python
from llm_conversation import LLMUtils, Conversation

llm = LLMUtils(base_url="http://localhost:8081", model="qwen")
conv = Conversation(system_prompt="You are a helpful assistant.")

response = ""
for chunk in llm.chat(conv, "What is 2+2?"):
    response += chunk
    print(chunk, end="")

print(f"\nFull response: {response}")
```

### Example 2: JSON Mode with Tool Schema

```python
import json
from llm_conversation import LLMUtils, Conversation, render_md_template

# Load tool schema
with open("prompts/character_design.json", "r") as f:
    tool_schema = json.load(f)

# Render system prompt from template
system_prompt = render_md_template(
    "prompts/character_design.md",
    user_requirements="A romantic scene in a cozy library"
)

# Create conversation with schema
conv = Conversation(system_prompt=system_prompt, tool_schema=tool_schema)
llm = LLMUtils(base_url="http://localhost:8081", model="qwen")

# Send request - returns parsed JSON data
for chunk in llm.chat(conv, "Design characters for a couple scene", chat_mode="json"):
    print(chunk, end="")
```

### Example 3.5: Controlling Reasoning/Thinking

To prevent excessive reasoning tokens with Qwen models, you have three approaches (from strongest to weakest):

**Note:** By default, `enable_thinking=False` — reasoning is already disabled. To enable it, pass `enable_thinking=True`.

**Option A: `enable_thinking=False`** — Completely disables thinking (strongest, and the default):
```python
from llm_conversation import LLMUtils, Conversation

llm = LLMUtils(
    base_url="http://localhost:8081",
    model="qwen",
    enable_thinking=False  # Disables all thinking/reasoning entirely (default behavior)
)

conv = Conversation(system_prompt="You are a helpful assistant.")

for chunk in llm.chat(conv, "What is 2+2?"):
    print(chunk, end="")
```

**Option B: `thinking_stop_token_bias`** — Pseudo-budget via logit bias (recommended balance):
```python
llm = LLMUtils(
    base_url="http://localhost:8081",
    model="qwen",
    thinking_stop_token_bias=0.5  # Makes model close thoughts ~40% sooner
)
```
- **Recommended range:** `0.5` to `1.0`
- Reduces reasoning by ~35-40% without fully disabling it
- Works even when `reasoning_budget` is ignored by llama.cpp

**Option C: `reasoning_budget`** — Hard token limit (requires llama.cpp 8744+):
```python
llm = LLMUtils(
    base_url="http://localhost:8081",
    model="qwen",
    reasoning_budget=500,
    reasoning_budget_message="... thinking budget exceeded, let's answer now."
)
```
- **Note:** llama.cpp builds before 8744 ignore this for Qwen 3.6 (known bug)
- Once upgraded, this becomes the most reliable hard limit

**Parameters:**
- `reasoning_budget`: Maximum thinking tokens as **integer** (e.g., 500, 1000)
- `reasoning_budget_message`: Optional message injected when budget is reached
- `enable_thinking`: Set to `True` to enable thinking (default: `False` — reasoning disabled)
- `thinking_stop_token_bias`: Float bias applied to the end-of-thought token (pseudo-budget)

---

### Example 3: Tool Schema Format

The tool schema follows OpenAI's function calling format. **All schema JSON files should be wrapped in an outer array** `[...]` containing one or more function definitions:

```python
tool_schema = [
    {
        "type": "function",
        "function": {
            "name": "answer",
            "description": "Design character profiles based on requirements.",
            "parameters": {
                "type": "object",
                "properties": {
                    "male": {
                        "type": "object",
                        "properties": {
                            "age": {"type": "string"},
                            "nationality": {"type": "string"}
                        },
                        "required": ["age", "nationality"]
                    }
                },
                "required": ["male"]
            }
        }
    }
]
```

**Note:** The `Conversation` class automatically normalizes both dict and list schema formats, so passing a bare `{ "type": "function", ... }` dict will work. However, for consistency, all schema JSON files should use the outer array format `[ {...} ]`.

---

## Qwen3 Model Specific Behavior

When using Qwen3 model with llama.cpp:

1. **Reasoning content**: Uses `reasoning_content` field (not `thinking`/`thought`)
2. **Tool calls**: Uses `tool_calls` array (not `function_call`)
3. **Arguments**: May be sent in multiple stream chunks and need concatenation

The module handles these automatically.

---

## Logging

The module uses Python's standard logging with `INFO` level by default.

To see detailed debug output (raw LLM responses):
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

To suppress most output:
```python
logging.basicConfig(level=logging.WARNING)
```

---

## JSON Parsing Robustness

The parser handles several common LLM output formats:

1. **Markdown code fences**: LLMs often wrap JSON in ````json ... `````. The parser strips trailing fences before parsing.
2. **Refusal text + retry**: If the LLM outputs refusal text followed by valid JSON, the parser extracts the first `{` or `[` delimiter.
3. **Tool calls vs plain JSON**: Detects `tool_calls` from the API response; if absent, validates the response as plain JSON.

## Error Handling

The `chat()` method handles several error cases:

1. **Invalid JSON**: Returns `[VALIDATION_ERROR]` and retries (if `max_retries > 1`)
2. **Missing required fields**: Returns specific error message
3. **Type mismatches**: Attempts to fix common issues (e.g., stringified arrays)
4. **Connection errors**: Yields error message and returns `None`

---

## Files

- `llm_conversation.py` - Main module
- `prompts/character_design.md` + `.json` - Example prompt and schema for character design
- `prompts/scene_design.md` + `.json` - Example prompt and schema for scene design
- `test_llm_conversation.py` - Test script for character design
- `test_scene_design.py` - Test script for scene design