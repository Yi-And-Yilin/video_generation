# Gemini Prompting System - Integration Guide

## Overview

The **gemini** system uses a **template-based placeholder replacement** mechanism for prompt generation, which offers significant advantages over simple keyword lookup systems. This document explains what makes the gemini prompting system useful and how to integrate it into the UI system.

---

## 1. What Makes Gemini's Prompting System Useful

### 1.1 Character Consistency

**Problem with current WAN system:** Each video gets a generic prompt like "A Chinese woman..." with no way to ensure consistent character appearance across multiple videos.

**Gemini solution:** Character definitions stored in JSON files (`character_forms/`) provide:
- Body shape, hair, eyes, skin tone
- Clothing (top, bottom, shoes, accessories)
- Location and lighting preferences

**Benefit:** Generate 100 different scenes with the **same character** maintaining visual consistency.

### 1.2 Template Flexibility

**Current WAN system:** Pre-written prompts in `video_prompt.tsv` - you select a category and get a random prompt.

**Gemini system:** Templates with placeholders that get filled dynamically:

```
Template: "{female} is {action} in {location}"
Character JSON: female="mature curvy woman", action="dancing", location="bedroom"
Result: "mature curvy woman is dancing in bedroom"
```

**Benefit:** Same template + different characters = unique, consistent prompts.

### 1.3 Weighted Random Selection

**Gemini templates support weighted choices:**

```
["action1:0.3", "action2:0.5", "action3:0.2"]
```

**Benefit:** Control probability distribution - some actions appear more often than others.

### 1.4 Complex Conditional Logic

**Gemini handles nested logic:**

```
["holding hands:1.3", "leaning back:1.25, arching back:1.3, holding hands:1.3"]:0.3
```

**Benefit:** Create sophisticated prompt variations without manual writing.

### 1.5 Auto-LoRA Mapping

**Gemini automatically assigns LoRAs based on template tags:**

```
Template: "...cowgirl position..." ; xl/cowgirl_lora.safetensors:0.8
```

**Benefit:** No manual LoRA selection - system picks based on action tags.

### 1.6 Special Rules

**Gemini applies character-specific rules automatically:**

- Curvy characters → auto-add `skindentation` tag
- Specific body shapes → modify related tags (e.g., `wide hips` for curvy)

**Benefit:** Domain knowledge baked into the system.

---

## 2. Core Components to Copy

| File | Purpose | Key Features |
|------|---------|--------------|
| `prompt_generator.py` | Main logic engine | Placeholder replacement, weighted selection, complex logic parsing |
| `prompt_warehouse.csv` | Template library | Pre-written templates with `{placeholders}` and LoRA tags |
| `mapping.json` | Placeholder definitions | Maps `{breasts}` → `{female.body_shape} breasts` |
| `character_forms/*.json` | Character definitions | Structured character data (body, clothing, accessories) |
| `*_lora_lookup.csv` | LoRA mappings | Maps action tags to LoRA files and strengths |

---

## 3. How It Works - Data Flow

```
┌─────────────────┐
│ Character JSON  │───┐
└─────────────────┘   │
                      ▼
┌──────────────────────────────────────┐
│ prompt_generator.py                  │
│  1. Load template from warehouse     │
│  2. Replace {placeholders} from JSON │
│  3. Apply mapping.json rules         │
│  4. Process weighted logic []        │
│  5. Apply special rules (curvy, etc) │
│  6. Extract LoRA tags (; separator)  │
└──────────────────────────────────────┘
                      │
                      ▼
┌──────────────────────────────────────┐
│ Final Output                         │
│ - Complete prompt text               │
│ - List of LoRA tags for lookup       │
└──────────────────────────────────────┘
```

---

## 4. Template Syntax Reference

### 4.1 Basic Placeholders

```
{female}        → "{female.age} woman" (from mapping.json)
{breasts}       → "{female.body_shape} breasts"
{eyes}          → "{female.eye_color} eyes"
{top}           → "{female.top}" (direct value)
{location}      → "{location}" (from JSON root)
```

### 4.2 Weighted Random Selection

```
["option1:0.3", "option2:0.7"]  → 30% option1, 70% option2
["option1", "option2:0.5"]      → 50% option2, 50% option1 (remaining weight)
```

### 4.3 Conditional Probability

```
{placeholder:0.8}  → Include placeholder 80% of time, skip 20%
```

### 4.4 Nested Complex Logic

```
["main:0.3|fallback:0.7"]:0.5  → 50% chance to evaluate this block
                                → If evaluated: 30% main, 70% fallback
```

### 4.5 LoRA Tag Specification

```
Template part ; lora1_name:lora1_strength, lora2_name:lora2_strength

Example: "$cowgirl$...cowgirl position... ; xl/cowgirl_lora:0.8, xl/thrust_lora:0.6"
```

---

## 5. Example: Character JSON Structure

```json
{
  "location": "elegant modern bedroom",
  "time": "night",
  "lighting": "soft warm lamp light",
  "female": {
    "age": "mature",
    "body_shape": "curvy",
    "hair_style": "long wavy",
    "hair_color": "black",
    "eye_color": "blue",
    "top": "silk blouse",
    "bottom": "pencil skirt",
    "shoes": "high heels",
    "bra": "black lace bra",
    "panties": "black lace panties",
    "accessories": {
      "hair": "hair band",
      "neck": "necklace",
      "ear": "earrings"
    }
  },
  "male": {
    "age": "young man",
    "top": "button-up shirt",
    "bottom": "dress pants"
  }
}
```

---

## 6. Example: Template in prompt_warehouse.csv

```
$cowgirl_pov$cowgirl position, {female}, {male}, {hair}, {breasts}, {eyes}, 
{top}, {open_lower}, {thighs}, vaginal penetration, pussy juice, male pov,
["holding hands:1.3", "leaning back:1.25, arching back:1.3"]:0.3,
["breast grab:0.7", "":0.3] ; ltx/cowgirl_lora:0.5, ltx/thrust_lora:0.85
```

**After processing with mature_curvy_lady.json:**

```
cowgirl position, mature curvy woman, boy, black long wavy hair, 
huge saggy breasts, blue eyes, silk blouse, black lace panties, 
thick thighs, vaginal penetration, pussy juice, male pov, 
leaning back, arching back, breast grab
```

**LoRA tags extracted:** `ltx/cowgirl_lora`, `ltx/thrust_lora`

---

## 7. Integration Requirements for main_ui

### 7.1 For WAN Tab (Replace TSV Lookup)

**Current:** Category dropdown → Random selection from `video_prompt.tsv`

**Proposed:** 
1. Add character selection dropdown (loads JSON from `projects/character_forms/`)
2. Add action template dropdown (loads from `prompt_warehouse.csv`)
3. Click "Generate Prompt" → Uses `prompt_generator.py` to create personalized prompt
4. Auto-fill LoRA tags into workflow based on template

### 7.2 For LTX Tab (Enhancement)

**Current:** Natural language instruction → LLM generates prompt

**Proposed:** 
1. Add option: "Use template-based generation" vs "Use LLM generation"
2. Template option: Select character + template → Instant prompt (no LLM wait)
3. LLM option: Keep existing for creative exploration

### 7.3 New Features to Add

- **Character library management** - UI to view/edit character JSON files
- **Template browser** - Browse and preview templates before use
- **Prompt preview** - See generated prompt before committing to video generation
- **Batch character generation** - Generate multiple scenes with same character

---

## 8. Advantages Over Current Systems

| Feature | WAN (TSV) | LTX (LLM) | Gemini (Template) |
|---------|-----------|-----------|-------------------|
| **Character consistency** | ❌ None | ⚠️ Manual description | ✅ Automatic via JSON |
| **Generation speed** | ✅ Instant | ❌ 10-60 sec wait | ✅ Instant |
| **Determinism** | ❌ Random prompt | ❌ LLM varies | ⚠️ Controlled randomness |
| **Flexibility** | ❌ Fixed categories | ✅ Unlimited | ✅ Template + variables |
| **LoRA automation** | ❌ Manual | ❌ Manual | ✅ Auto-mapped |
| **Special rules** | ❌ None | ⚠️ LLM may miss | ✅ Built-in |

---

## 9. Migration Checklist

- [ ] Copy `prompt_generator.py` to root folder
- [ ] Copy `prompt_warehouse.csv` to root folder
- [ ] Copy `mapping.json` to root folder
- [ ] Create `projects/character_forms/` folder
- [ ] Copy character JSON files to new location
- [ ] Copy `*_lora_lookup.csv` files to root
- [ ] Update paths in `prompt_generator.py` for new locations
- [ ] Add character selection UI to WAN/LTX tabs
- [ ] Add template selection UI
- [ ] Add "Generate from Template" button
- [ ] Integrate with existing workflow execution
- [ ] Test with sample character + template
- [ ] Verify LoRA mapping works correctly

---

## 10. Code Reference

### Key Methods in `prompt_generator.py`

```python
# Load templates from CSV
gen = PromptGenerator('mapping.json')
gen.load_warehouse('prompt_warehouse.csv')

# Load character JSON
with open('character_forms/mature_curvy_lady.json') as f:
    character_data = json.load(f)

# Generate prompt
prompt = gen.generate(character_data)

# Generate with LoRA tags
prompt, lora_tags = gen.generate_with_lora(character_data)
```

---

## 11. Next Steps

1. **Copy files** - Execute file copy commands
2. **Review code** - Study `prompt_generator.py` logic
3. **Design UI** - Plan character/template selection interface
4. **Implement integration** - Add to main_ui.py
5. **Test thoroughly** - Verify prompt generation and LoRA mapping
6. **Document changes** - Update user guides

---

*Document Version: 1.0*
*Created: 2026-04-21*
*Purpose: Guide for integrating gemini prompting system into main_ui*
