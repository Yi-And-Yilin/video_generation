import os
import random
import csv
import json
from pathlib import Path

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(SCRIPT_DIR, "image_prompt_main_lookup.csv")


def build_character_string(character: dict, gender: str) -> str:
    parts = []

    age = character.get("age", "").lower()
    nationality = character.get("nationality", "")
    height = character.get("height", "")
    body_shape = character.get("body_shape", "")
    hair_style = character.get("hair_style", "")

    if gender == "male":
        if age == "toddler":
            age_str = "boy toddler"
        elif age == "child":
            age_str = "boy child"
        elif age == "teenager":
            age_str = "boy teenager"
        elif age == "adult":
            age_str = "adult man"
        elif age == "middle-age":
            age_str = "middle-age man"
        elif age == "old":
            age_str = "old man"
        else:
            age_str = f"{age} man"
    else:
        if age == "toddler":
            age_str = "girl toddler"
        elif age == "child":
            age_str = "girl child"
        elif age == "teenager":
            age_str = "girl teenager"
        elif age == "adult":
            age_str = "adult woman"
        elif age == "middle-age":
            age_str = "middle-age woman"
        elif age == "old":
            age_str = "old woman"
        else:
            age_str = f"{age} woman"

    if height.lower() != "medium":
        parts.append(height)

    if nationality:
        parts.append(nationality)

    parts.append(age_str)

    return " ".join(parts)


def resolve_field_value(val: str) -> str:
    """If value is '3', 50% chance becomes '0', 50% stays '1'."""
    if val == "3":
        return "1" if random.random() < 0.5 else "0"
    return val


def resolve_nipples_value(nipples_val: str, female_char: dict) -> str:
    """
    Handle nipples field value='3' with weighted random outcomes:
      30% -> '' (ignore)
      30% -> nipples_value + 'nipples slip'
      20% -> 'clothed nipples, nipple outline, nipples visible through fabric'
      20% -> nipples_value + 'nipples visible through fabric, see-through nipples'

    For nipples_val '1' or '2', returns the actual nipples text from female_char.
    For nipples_val '0' or resolved '0', returns ''.
    """
    nipples_value = female_char.get("nipples", "").strip()

    if nipples_val == "3":
        roll = random.random()
        if roll < 0.3:
            # 30%: ignore
            return ""
        elif roll < 0.6:
            # 30%: nipples + "nipples slip"
            if nipples_value:
                return nipples_value + ", nipples slip"
            return "nipples slip"
        elif roll < 0.8:
            # 20%: clothed nipples preset
            return "clothed nipples, nipple outline, nipples visible through fabric"
        else:
            # 20%: nipples + "nipples visible through fabric, see-through nipples"
            if nipples_value:
                return nipples_value + ", nipples visible through fabric, see-through nipples"
            return "nipples visible through fabric, see-through nipples"
    elif nipples_val in ("1", "2"):
        # Return the actual nipples text from character design
        return nipples_value
    else:
        # nipples_val is "0" or resolved to "0"
        return ""


def resolve_crotch_value(crotch_val: str, female_char: dict, location: dict, leg_raw: str, bottom_active: bool) -> str:
    """
    Handle crotch field with weighted random outcomes for value='3':
      40% -> '' (ignore)
      40% -> panties + ", pulled aside" + pussy + (optionally bottom if bottom field not active)
      20% -> panties + (if leg is 1/2/3 then ", on legs" else ", on thighs") + pussy + (optionally bottom)

    For crotch=1/2, returns the standard behavior (panties + pussy + optionally bottom).
    For crotch=0, returns ''.

    Parameters
    ----------
    crotch_val : str
        Raw value from CSV row (before resolve_field_value).
    female_char : dict
        The character_design.female dict (for pussy).
    location : dict
        The location dict (for female_character.panties, bottom).
    leg_raw : str
        Raw leg field value from CSV (before resolve_field_value).
    bottom_active : bool
        Whether the CSV `bottom` field resolved to non-zero.
    """
    female_panties = location.get("female_character", {}).get("panties", "").strip()
    female_bottom = location.get("female_character", {}).get("bottom", "").strip()
    female_pussy = female_char.get("pussy", "").strip()

    def build_with_bottom():
        """Build the standard crotch fragment: panties (+ optionally bottom) + pussy."""
        result = ""
        if female_panties:
            if female_bottom and not bottom_active:
                result = female_panties + "," + female_bottom
            else:
                result = female_panties
        if female_pussy:
            if result:
                result = result + "," + female_pussy
            else:
                result = female_pussy
        return result

    if crotch_val == "3":
        roll = random.random()
        if roll < 0.4:
            # 40%: ignore
            return ""
        elif roll < 0.8:
            # 40%: panties + pulled aside + pussy (+ optionally bottom)
            base = build_with_bottom()
            if base:
                return base + ", pulled aside"
            return "pulled aside"
        else:
            # 20%: panties + (on legs or on thighs) + pussy (+ optionally bottom)
            base = build_with_bottom()
            leg_is_active = leg_raw in ("1", "2", "3")
            if base:
                if leg_is_active:
                    return base + ", on legs"
                else:
                    return base + ", on thighs"
            return "on legs" if leg_is_active else "on thighs"
    elif crotch_val in ("1", "2"):
        return build_with_bottom()
    else:
        return ""


def load_lookup_csv():
    rows = []
    with open(CSV_PATH, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows


def select_rows_by_possibility(rows, count=10):
    def safe_int(val):
        try:
            return int(val) if val.strip() else 0
        except:
            return 0

    total_possibility = sum(safe_int(row.get("possiblity", 0)) for row in rows)
    if total_possibility == 0:
        return rows[:count] if len(rows) >= count else rows

    selected_rows = []
    for _ in range(count):
        rand = random.randint(1, total_possibility)
        cumulative = 0
        for row in rows:
            cumulative += safe_int(row.get("possiblity", 0))
            if rand <= cumulative:
                selected_rows.append(row)
                break
    return selected_rows


def parse_row_to_prompt_parts(row, male_char_str, female_char_str, female_hair_str, location, male_char=None, female_char=None):
    prompt_parts = []

    def strip_quotes(val):
        if val.startswith('"') and val.endswith('"'):
            return val[1:-1]
        return val

    main_action = strip_quotes(row.get("main_action", "")).strip()
    if main_action:
        prompt_parts.append(main_action)

    vertical_position = strip_quotes(row.get("vertical_position", "")).strip()
    if vertical_position:
        prompt_parts.append(vertical_position)

    horizontal_angle = strip_quotes(row.get("horizontal_angle", "")).strip()
    if horizontal_angle:
        if horizontal_angle == "frontal":
            pass
        elif horizontal_angle.startswith("side_view"):
            prompt_parts.append("side_view")
        else:
            prompt_parts.append(horizontal_angle)

    pov = strip_quotes(row.get("pov", "")).strip()
    if pov == "1":
        prompt_parts.append("pov")

    extra_condition = strip_quotes(row.get("extra_condition", "")).strip()
    extra_condition_2 = strip_quotes(row.get("extra_condition_2", "")).strip()

    male = resolve_field_value(row.get("male", "").strip())
    male_head = resolve_field_value(row.get("male_head", "").strip())
    male_upper = resolve_field_value(row.get("male_upper", "").strip())
    male_lower = resolve_field_value(row.get("male_lower", "").strip())
    male_feet = resolve_field_value(row.get("male_feet", "").strip())
    male_croth = resolve_field_value(row.get("male_croth", "").strip())
    male_body_part = resolve_field_value(row.get("male_body_part", "").strip())

    has_male = male in ("1", "2") or male_head in ("1", "2")
    has_male_upper = male_upper in ("1", "2")
    has_male_lower = male_lower in ("1", "2")
    has_male_feet = male_feet in ("1", "2")
    has_male_croth = male_croth in ("1", "2")
    has_male_body_part = male_body_part in ("1", "2")

    if has_male:
        prompt_parts.append(male_char_str)

    if has_male_upper:
        male_top = location.get("male_character", {}).get("top", "").strip()
        if male_top:
            prompt_parts.append(male_top)

    if has_male_lower:
        male_bottom = location.get("male_character", {}).get("bottom", "").strip()
        if male_bottom:
            prompt_parts.append(male_bottom)

    if has_male_feet:
        male_shoes = location.get("male_character", {}).get("shoes", "").strip()
        if male_shoes:
            prompt_parts.append(male_shoes)

    if has_male_croth:
        male_penis = male_char.get("penis", "").strip()
        if male_penis:
            prompt_parts.append(male_penis)

    # Add "1man" if any of male_head, male_upper, or male_body_part is non-zero
    if male_head in ("1", "2") or male_upper in ("1", "2") or has_male_body_part:
        prompt_parts.append("1man")

    crotch_raw = row.get("crotch", "").strip()
    bottom = resolve_field_value(row.get("bottom", "").strip())

    has_bottom = bottom in ("1", "2")

    crotch_result = resolve_crotch_value(crotch_raw, female_char or {}, location, row.get("leg", "").strip(), has_bottom)
    if crotch_result:
        prompt_parts.append(crotch_result)

    if has_bottom:
        female_bottom = location.get("female_character", {}).get("bottom", "").strip()
        female_body_shape = location.get("female_character", {}).get("body_shape", "").strip()
        bottom_adv = ""
        shape_lower = female_body_shape.lower()
        if shape_lower in ("thin", "slender"):
            bottom_adv = "small "
        elif shape_lower in ("curvy", "voluptuous", "chubby"):
            bottom_adv = "big "
        # "medium" and others -> bottom_adv stays ""
        ass_value = bottom_adv + "ass" if bottom_adv else "ass"
        if female_bottom:
            prompt_parts.append(ass_value + ", " + female_bottom)

    head = resolve_field_value(row.get("head", "").strip())
    face = resolve_field_value(row.get("face", "").strip())
    chest = resolve_field_value(row.get("chest", "").strip())
    back = resolve_field_value(row.get("back", "").strip())
    thigh = resolve_field_value(row.get("thigh", "").strip())
    leg = resolve_field_value(row.get("leg", "").strip())
    feet = resolve_field_value(row.get("feet", "").strip())
    arm = row.get("arm", "").strip()
    hand = resolve_field_value(row.get("hand", "").strip())
    nipples_raw = row.get("nipples", "").strip()

    nipples_result = resolve_nipples_value(nipples_raw, female_char or {})
    if nipples_result:
        prompt_parts.append(nipples_result)

    if head in ("1", "2"):
        head_parts = []
        if female_hair_str:
            head_parts.append(female_hair_str)
        female_hair_acc = location.get("female_character", {}).get("accessories", {}).get("hair", "").strip()
        female_ear = location.get("female_character", {}).get("accessories", {}).get("ear", "").strip()
        if female_hair_acc:
            head_parts.append(female_hair_acc)
        if female_ear:
            head_parts.append(female_ear)
        if head_parts:
            prompt_parts.append(", ".join(head_parts))

    if face in ("1", "2"):
        face_parts = []
        female_face = location.get("female_character", {}).get("face", "").strip()
        female_makeup = location.get("female_character", {}).get("makeup", "").strip()
        female_face_acc = location.get("female_character", {}).get("accessories", {}).get("face", "").strip()
        if female_face:
            face_parts.append(female_face)
        if female_makeup:
            face_parts.append(female_makeup)
        if female_face_acc:
            face_parts.append(female_face_acc)
        if face_parts:
            prompt_parts.append(", ".join(face_parts))

    if chest in ("1", "2"):
        chest_parts = []
        female_top = location.get("female_character", {}).get("top", "").strip()
        female_neck = location.get("female_character", {}).get("accessories", {}).get("neck", "").strip()
        female_waist = location.get("female_character", {}).get("accessories", {}).get("waist", "").strip()
        female_belly = location.get("female_character", {}).get("accessories", {}).get("belly", "").strip()
        female_bra = location.get("female_character", {}).get("bra", "").strip()
        if female_top:
            chest_parts.append(female_top)
        if female_neck:
            chest_parts.append(female_neck)
        if female_waist:
            chest_parts.append(female_waist)
        if female_belly:
            chest_parts.append(female_belly)
        if female_bra:
            chest_parts.append(female_bra)
        if chest_parts:
            prompt_parts.append(", ".join(chest_parts))

        # Add "cleavage" if female body_shape is Curvy, Voluptuous, or Chubby
        female_body_shape = (female_char or {}).get("body_shape", "").lower()
        if female_body_shape in ("curvy", "voluptuous", "chubby"):
            prompt_parts.append("cleavage")

    if back in ("1", "2"):
        back_parts = ["woman's back"]
        female_back_top = location.get("female_character", {}).get("top", "").strip()
        if female_back_top:
            back_parts.append(female_back_top)
        prompt_parts.append(", ".join(back_parts))

    if thigh in ("1", "2"):
        female_thigh = location.get("female_character", {}).get("accessories", {}).get("thigh", "").strip()
        if female_thigh:
            prompt_parts.append(female_thigh)

    if leg in ("1", "2"):
        leg_parts = []
        female_legs = location.get("female_character", {}).get("legs", "").strip()
        female_ankle = location.get("female_character", {}).get("accessories", {}).get("ankle", "").strip()
        if female_legs:
            leg_parts.append(female_legs)
        if female_ankle:
            leg_parts.append(female_ankle)
        if leg_parts:
            prompt_parts.append(", ".join(leg_parts))

    if feet in ("1", "2"):
        female_shoes = location.get("female_character", {}).get("shoes", "").strip()
        if female_shoes:
            prompt_parts.append(female_shoes)

    if hand in ("1", "2"):
        hand_parts = []
        female_finger = location.get("female_character", {}).get("accessories", {}).get("finger", "").strip()
        female_wrist = location.get("female_character", {}).get("accessories", {}).get("wrist", "").strip()
        female_finger_nail = location.get("female_character", {}).get("accessories", {}).get("finger_nail", "").strip()
        if female_finger:
            hand_parts.append(female_finger)
        if female_wrist:
            hand_parts.append(female_wrist)
        if female_finger_nail:
            hand_parts.append(female_finger_nail)
        if hand_parts:
            prompt_parts.append(", ".join(hand_parts))

    return prompt_parts, extra_condition, extra_condition_2


def replace_placeholders(template, location):
    lying_surfaces = location.get("lying_surfaces", [])
    sitting_surfaces = location.get("sitting_surfaces", location.get("sitting_surface", []))
    virtical_surfaces = location.get("virtical_surfaces", location.get("virtical_surface", []))

    lying_surface = random.choice(lying_surfaces) if lying_surfaces else {}
    lying_surface_name = lying_surface.get("lying_surface", "") if isinstance(lying_surface, dict) else str(lying_surface)
    objects_on_it = lying_surface.get("objects_on_it", []) if isinstance(lying_surface, dict) else []

    sitting_surface = random.choice(sitting_surfaces) if sitting_surfaces else ""

    virtical_surface = random.choice(virtical_surfaces) if virtical_surfaces else ""

    lying_part = lying_surface_name
    if objects_on_it:
        lying_part = lying_surface_name + ", " + ", ".join(objects_on_it)

    result = template.replace("{{lying_surfaces}}", lying_part)
    result = result.replace("{{vertical_surfaces}}", virtical_surface)
    result = result.replace("{{sitting_surfaces}}", sitting_surface)

    return result


def build_location_prompt(location, male_char_str, female_char_str, female_hair_str, selected_rows, male_char=None, female_char=None):
    prompt_parts = []
    extra_condition = ""
    extra_condition_2 = ""

    for row in selected_rows:
        row_parts, ec, ec2 = parse_row_to_prompt_parts(row, male_char_str, female_char_str, female_hair_str, location, male_char, female_char)
        prompt_parts.extend(row_parts)
        if ec:
            extra_condition = ec
        if ec2:
            extra_condition_2 = ec2

    prompt_parts.append(female_char_str)

    female_body_shape = location.get("female_character", {}).get("body_shape", "")
    if female_body_shape:
        prompt_parts.append(female_body_shape)

    loc = location.get("location", "")
    if loc:
        prompt_parts.append(loc)

    major_elements = location.get("location_major_elements", [])
    if major_elements:
        prompt_parts.append(", ".join(major_elements))

    time = location.get("time", "")
    if time:
        prompt_parts.append(time)

    lighting = location.get("lighting", "")
    if lighting:
        prompt_parts.append(lighting)

    if extra_condition:
        prompt_parts.append(replace_placeholders(extra_condition, location))
    if extra_condition_2:
        prompt_parts.append(replace_placeholders(extra_condition_2, location))

    return ", ".join(prompt_parts)


def generate_prompts_for_task(task_path: str):
    with open(task_path, 'r', encoding='utf-8') as f:
        task_data = json.load(f)

    job_id = task_data.get("job_id", "unknown")
    character_design = task_data.get("character_design", {})
    location_design = task_data.get("location_design", {})
    locations = location_design.get("locations", [])

    male_char = character_design.get("male") or {}
    female_char = character_design.get("female") or {}

    male_char_str = build_character_string(male_char, "male")
    female_char_str = build_character_string(female_char, "female")

    female_hair = female_char.get("hair_style", "").lower().replace("hair", "").strip()

    lookup_rows = load_lookup_csv()

    prompts = []
    for location in locations:
        selected_row = select_rows_by_possibility(lookup_rows, count=1)
        prompt = build_location_prompt(location, male_char_str, female_char_str, female_hair, selected_row, male_char, female_char)
        prompts.append({
            "location": location.get("location", ""),
            "prompt": prompt
        })

    output_path = os.path.join(os.path.dirname(task_path), "prompts.json")
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump({
            "job_id": job_id,
            "prompts": prompts,
            "male_character_string": male_char_str,
            "female_character_string": female_char_str
        }, f, indent=4)

    return prompts, male_char_str, female_char_str


def generate_prompts_for_locations(location, character_design, count=3):
    """
    Generate *count* different image prompts for a single location.

    Parameters
    ----------
    location : dict
        A single location dictionary (as found in location_design["locations"]).
    character_design : dict
        The character_design dict with "male" and "female" keys.
    count : int
        Number of prompts to generate (default 3).

    Returns
    -------
    list[str]
        A list of *count* prompt strings.
    """
    male_char = character_design.get("male") or {}
    female_char = character_design.get("female") or {}

    male_char_str = build_character_string(male_char, "male")
    female_char_str = build_character_string(female_char, "female")

    female_hair = female_char.get("hair_style", "").lower().replace("hair", "").strip()

    lookup_rows = load_lookup_csv()

    prompts = []
    for _ in range(count):
        selected_row = select_rows_by_possibility(lookup_rows, count=1)
        prompt = build_location_prompt(
            location, male_char_str, female_char_str, female_hair, selected_row, male_char, female_char
        )
        prompts.append(prompt)

    return prompts


if __name__ == "__main__":
    test_task_path = r"C:\SimpleAIHelper\video_generation\tasks\92bk9\task.json"
    prompts, male_str, female_str = generate_prompts_for_task(test_task_path)

    print("Male character string:", male_str)
    print("Female character string:", female_str)
    print("\nGenerated prompts:")
    for p in prompts:
        print(f"\nLocation: {p['location']}")
        print(f"Prompt: {p['prompt']}")