# Image Prompt Generation Process

## Related Files

| File | Description |
|------|-------------|
| `image_prompt_generator.py` | Main module implementing the prompt generation logic |
| `image_prompt_main_lookup.csv` | Lookup table with pose/angle combinations |
| `test_prompt.py` | CLI test tool for generating prompts from a task.json |
| `prompts/` | Directory for prompt templates (future) |

## Overview

The image prompt generator reads `task.json` (character and location design) and `image_prompt_main_lookup.csv` (pose/angle lookup) to create Stable Diffusion prompts for each location.

## Input Files

### task.json
Contains character design and location design with outfits, accessories, and scene details.

### image_prompt_main_lookup.csv
Lookup table with pose/angle combinations. Each row has a `possiblity` field determining selection probability.

## Process

### Step 1: Build Character Strings

#### Male Character
Format: `[height] [nationality] [age_phrase]`

- Age mapping:
  - toddler → boy toddler
  - child → boy child
  - teenager → boy teenager
  - adult → adult man
  - middle-age → middle-age man
  - old → old man
- Skip "medium" for height
- Example: `Tall Japanese young man`

#### Female Character
Format: `[height] [nationality] [age_phrase]`

- Same age/nationality/height rules as male
- Hair style is NOT included in base character string
- Example: `Short Japanese young woman`

### Step 2: CSV Row Selection

1. Sum all `possiblity` values in CSV
2. Randomly select 1 row per location based on probability distribution
3. Each location gets its own selected row (different actions/poses per location)

**Note:** CSV field values may have surrounding quotes that are automatically stripped.

### Step 3: Parse CSV Fields to Prompt Elements

For each selected row, parse these fields based on their value:

| Value | Behavior |
|-------|----------|
| `0` | Ignore the field |
| `1` | Include and parse |
| `2` | Include and parse |
| `3` | 50% chance treated as `0` (ignore), 50% chance treated as `1` (include) |

| Field | Action |
|-------|--------|
| main_action | Include value directly (e.g., kiss, hug) |
| vertical_position | Include value directly (e.g., eye_level) |
| horizontal_angle | Include value directly (e.g., side_view). If value starts with "side_view", only include "side_view". If value is "frontal", ignore this field. |
| pov | Include "pov" if value is "1" |
| extra_condition | Include value directly (may contain placeholders) |
| extra_condition_2 | Include value directly (may contain placeholders) |
| male | Add male character string if 1/2/3 (only once if male_head also non-zero). Value 3 has 50% chance of being ignored. |
| male_head | Adds male character string if 1/2/3 AND adds "1man" if 1/2/3 (after resolve). Value 3 has 50% chance of being ignored. |
| male_upper | Adds `male_character.top` if 1/2/3 AND adds "1man" if 1/2/3 (after resolve). Value 3 has 50% chance of being ignored. |
| male_lower | Add `male_character.bottom` if 1/2/3. Value 3 has 50% chance of being ignored. |
| male_feet | Add `male_character.shoes` if 1/2/3. Value 3 has 50% chance of being ignored. |
| man_hand | Ignore |
| male_croth | Add `character_design.male.penis` if 1/2. Value 3 has 50% chance of being ignored. Value 0 is ignored. |
| crotch | Add `female_character.panties` + `,` + `female_character.bottom` + `,` + `female_character.pussy` if 1/2. Value 3 has 50% chance of being ignored. Value 0 keeps existing behavior (no addition). |
| bottom | First determine `bottom_adv` based on female body_shape: "small " for Thin/Slender, "" for Medium, "big " for Curvy/Voluptuous/Chubby. Then add `bottom_adv + "ass" + ", " + female_character.bottom` if 1/2. Value 3 has 50% chance of being ignored. Value 0 keeps existing behavior (no addition). |
| nipples | Add `character_design.female.nipples` if 1/2. Value 3 has 50% chance of being ignored. Value 0 is ignored. |
| male_body_part | If 1/2/3 (after 50% resolve), adds "1man" to prompt. Value 3 has 50% chance of being ignored. |
| head | Add female hair style (from character) + `female_character.accessories.hair` + `ear` if 1/2/3. Value 3 has 50% chance of being ignored. |
| face | Add `face` + `makeup` + `accessories.face` if 1/2/3. Value 3 has 50% chance of being ignored. |
| chest | Add `top` + `neck` + `waist` + `belly` + `bra` if 1/2/3. Value 3 has 50% chance of being ignored. |
| back | Add "woman's back" + `top` if 1/2/3. Value 3 has 50% chance of being ignored. |
| thigh | Add `accessories.thigh` if 1/2/3. Value 3 has 50% chance of being ignored. |
| leg | Add `legs` + `accessories.ankle` if 1/2/3. Value 3 has 50% chance of being ignored. |
| feet | Add `shoes` if 1/2/3. Value 3 has 50% chance of being ignored. |
| arm | Ignore |
| hand | Add `finger` + `wrist` + `finger_nail` if 1/2/3. Value 3 has 50% chance of being ignored. |

**All prompt elements are separated by `, ` (comma space).**

### Step 4: Append Character and Scene Details

After processing all CSV rows:
1. Add female character string + body_shape
2. Add `location`
3. Add `location_major_elements` (comma-separated)
4. Add `time`
5. Add `lighting`

### Step 5: Replace Placeholders

Process `extra_condition` and `extra_condition_2` which may contain:

| Placeholder | Replacement |
|-------------|-------------|
| `{{lying_surfaces}}` | Random `lying_surface` + its `objects_on_it` |
| `{{vertical_surfaces}}` | Random `virtical_surface` (or `virtical_surfaces` plural) |
| `{{sitting_surfaces}}` | Random `sitting_surface` (or `sitting_surfaces` plural) |

**Note:** The JSON supports both singular and plural forms (`sitting_surface`/`sitting_surfaces`, `virtical_surface`/`virtical_surfaces`).

### New Fields: `male_croth`, `crotch`, `bottom`, `nipples`

These fields were added to support additional anatomical details in the generated prompts.

#### `male_croth` Field

Controls inclusion of male genitals from `character_design.male.penis`.

| CSV Value | Behavior |
|-----------|----------|
| `0` | Ignore |
| `1` or `2` | Add `male_character.penis` value |
| `3` | 50% ignore, 50% add penis value |

#### `crotch` Field

Controls inclusion of female genitals in addition to existing panties/bottom values.

| CSV Value | Behavior |
|-----------|----------|
| `0` | Keep existing behavior (no addition) |
| `1` or `2` | Add `female_character.pussy` value |
| `3` | 50% ignore, 50% add pussy value |

#### `bottom` Field

Adds an ass modifier based on the female's body shape, then the bottom clothing value.

**Step 1: Determine `bottom_adv` from body_shape:**

| body_shape | bottom_adv |
|------------|------------|
| Thin, Slender | `"small "` |
| Medium | `""` (empty) |
| Curvy, Voluptuous, Chubby | `"big "` |

**Step 2: Add ass modifier + bottom:**

| CSV Value | Behavior |
|-----------|----------|
| `0` | Keep existing behavior (no addition) |
| `1` or `2` | Add `bottom_adv + "ass" + ", " + female_character.bottom` |
| `3` | 50% ignore, 50% add ass modifier |

**Example:** For a Curvy character with `bottom=2`, the prompt includes: `"big ass, Grey leggings"`

#### `nipples` Field

Controls inclusion of female nipples from `character_design.female.nipples`.

| CSV Value | Behavior |
|-----------|----------|
| `0` | Ignore |
| `1` or `2` | Add `female_character.nipples` value |
| `3` | 50% ignore, 50% add nipples value |

---

## Output

Generates `prompts.json` with:
- `job_id`: Job identifier
- `male_character_string`: Built male character string
- `female_character_string`: Built female character string
- `prompts`: Array of objects with `location` and `prompt` for each location (1 prompt per location)

## Example

**Input (task.json excerpt):**
```json
{
  "male": {"age": "Young", "nationality": "Japanese", "height": "Tall"},
  "female": {"age": "Young", "nationality": "Japanese", "height": "Short", "hair_style": "French braid"}
}
```

**Output (base character strings):**
- Male: `Tall Japanese young man`
- Female: `Short Japanese young woman`

**Note:** Hair style (e.g., "french braid") is only added when CSV `head` field is 1/2, or 3 that resolved to 1.

---

## New: `generate_prompts_for_locations()`

A new function was added to support per-location prompt generation within the automated workflow.

```python
def generate_prompts_for_locations(location, character_design, count=3):
    """
    Generate *count* different image prompts for a single location.
    Returns: list[str] — *count* prompt strings.
    """
```

**Differences from `generate_prompts_for_task()`:**

| Aspect | `generate_prompts_for_task()` | `generate_prompts_for_locations()` |
|--------|-------------------------------|-------------------------------------|
| Input | `task.json` path (full file) | Single location dict + character_design dict |
| Output | `prompts.json` file + `(prompts, male_str, female_str)` | List of *count* prompt strings |
| Prompts per location | 1 | 3 (default) |
| Used by | `test_prompt.py` (CLI) | `run_new_tab_workflow()` (automated pipeline) |

**Integration with `new_tab_workflow.py`:**

Phase 3 of the new tab workflow calls `_generate_prompts_for_locations()`, which in turn calls `generate_prompts_for_locations()` for each location. The resulting prompts are embedded into each location dict under `"prompts"` key in `task.json`.

```json
{
  "location": "Traditional Japanese Garden",
  "prompts": [
    "prompt string 1",
    "prompt string 2",
    "prompt string 3"
  ]
}
```