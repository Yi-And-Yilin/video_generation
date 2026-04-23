"""
Tests for new image_prompt_generator fields:
- male_croth (male genitals)
- crotch (adds female pussy)
- bottom (adds ass with body_shape-based modifier)
- nipples (female nipples)
"""
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from image_prompt_generator import (
    build_location_prompt,
    resolve_field_value,
    build_character_string,
)


def make_location(
    female_body_shape="Athletic",
    female_bottom="Grey leggings",
    female_pussy="hairless pussy",
    female_nipples="pink nipples",
    female_panties="white panties",
    male_penis="veiny penis",
):
    """Build a minimal location dict for testing."""
    return {
        "location": "Test Room",
        "location_major_elements": ["Wall"],
        "time": "Day",
        "lighting": "Bright",
        "lying_surfaces": [],
        "sitting_surface": [],
        "virtical_surface": [],
        "female_character": {
            "body_shape": female_body_shape,
            "bottom": female_bottom,
            "pussy": female_pussy,
            "nipples": female_nipples,
            "panties": female_panties,
            "accessories": {
                "hair": "None",
                "ear": "None",
                "face": "None",
                "finger": "None",
                "wrist": "None",
                "neck": "None",
                "waist": "None",
                "ankle": "None",
                "belly": "None",
                "thigh": "None",
            },
        },
        "male_character": {
            "penis": male_penis,
            "accessories": {
                "hair": "None",
                "ear": "None",
                "face": "None",
            },
        },
    }


def make_character(body_shape):
    """Build a character_design dict with a body_shape."""
    return {
        "male": {
            "age": "Adult",
            "nationality": "Asian",
            "height": "Tall",
            "body_shape": body_shape,
            "penis": "veiny penis",
        },
        "female": {
            "age": "Adult",
            "nationality": "Asian",
            "height": "Medium",
            "body_shape": body_shape,
            "nipples": "pink nipples",
            "pussy": "hairless pussy",
        },
    }


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

def _build_prompt(loc, male_str, female_str, row, male_char, female_char):
    """Helper to call build_location_prompt with character dicts."""
    return build_location_prompt(
        loc, male_str, female_str, "", [row], male_char, female_char
    )


def assert_includes(prompt, expected_substrs):
    """Assert all substrings appear in the prompt."""
    for s in expected_substrs:
        assert s in prompt, f"Expected '{s}' not found in prompt:\n{prompt}"


def assert_not_includes(prompt, unexpected_substrs):
    """Assert none of the substrings appear in the prompt."""
    for s in unexpected_substrs:
        assert s not in prompt, f"Unexpected '{s}' found in prompt:\n{prompt}"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_male_croth_1_includes_penis():
    """male_croth=1 or 2 -> add male penis to prompt."""
    row = {
        "main_action": "kiss",
        "male_croth": "1",
        "male": "1",
        "male_head": "1",
    }
    for _ in range(20):
        loc = make_location()
        char = make_character("Athletic")
        prompt = _build_prompt(
            loc, "Tall Asian adult man", "Asian adult woman", row, char["male"], char["female"]
        )
        assert_includes(prompt, ["kiss", "veiny penis"])
        break


def test_male_croth_0_ignores_penis():
    """male_croth=0 -> do NOT add male penis."""
    row = {
        "main_action": "kiss",
        "male_croth": "0",
        "male": "1",
        "male_head": "1",
    }
    for _ in range(20):
        loc = make_location()
        char = make_character("Athletic")
        prompt = _build_prompt(
            loc, "Tall Asian adult man", "Asian adult woman", row, char["male"], char["female"]
        )
        assert_includes(prompt, ["kiss"])
        assert_not_includes(prompt, ["veiny penis"])
        break


def test_male_croth_3_50_percent():
    """male_croth=3 -> 50% include penis, 50% ignore."""
    row = {
        "main_action": "kiss",
        "male_croth": "3",
        "male": "1",
        "male_head": "1",
    }
    with_includes = 0
    with_out = 0
    for _ in range(20):
        loc = make_location()
        char = make_character("Athletic")
        prompt = _build_prompt(
            loc, "Tall Asian adult man", "Asian adult woman", row, char["male"], char["female"]
        )
        if "veiny penis" in prompt:
            with_includes += 1
        else:
            with_out += 1
    assert with_includes >= 4 and with_out >= 4, f"Expected ~50/50 split for male_croth=3, got {with_includes}/{with_out}"


def test_crotch_1_2_adds_pussy():
    """crotch=1 or 2 -> add female pussy in addition to existing values."""
    row = {
        "main_action": "kiss",
        "crotch": "2",
        "bottom": "1",
    }
    loc = make_location()
    char = make_character("Athletic")
    prompt = _build_prompt(
        loc, "Tall Asian adult man", "Asian adult woman", row, char["male"], char["female"]
    )
    assert_includes(prompt, ["hairless pussy", "Grey leggings"])


def test_crotch_3_50_percent():
    """crotch=3 -> 50% include pussy, 50% ignore."""
    row = {
        "main_action": "kiss",
        "crotch": "3",
        "bottom": "1",
    }
    with_pussy = 0
    without_pussy = 0
    for _ in range(20):
        loc = make_location()
        char = make_character("Athletic")
        prompt = _build_prompt(
            loc, "Tall Asian adult man", "Asian adult woman", row, char["male"], char["female"]
        )
        if "hairless pussy" in prompt:
            with_pussy += 1
        else:
            without_pussy += 1
    assert with_pussy >= 4 and without_pussy >= 4, f"Expected ~50/50 split for crotch=3, got {with_pussy}/{without_pussy}"


def test_crotch_0_keeps_existing():
    """crotch=0 -> do NOT add pussy, keep existing values."""
    row = {
        "main_action": "kiss",
        "crotch": "0",
        "bottom": "1",
    }
    loc = make_location()
    char = make_character("Athletic")
    prompt = _build_prompt(
        loc, "Tall Asian adult man", "Asian adult woman", row, char["male"], char["female"]
    )
    assert_includes(prompt, ["Grey leggings"])
    assert_not_includes(prompt, ["hairless pussy"])


def test_bottom_adv_thin_slender():
    """body_shape Thin/Slender -> bottom_adv='small ', add 'small ass'."""
    row = {
        "main_action": "kiss",
        "bottom": "2",
    }
    for shape in ["Thin", "Slender"]:
        loc = make_location(female_body_shape=shape)
        char = make_character(shape)
        prompt = _build_prompt(
            loc, "Tall Asian adult man", f"{shape} Asian adult woman", row, char["male"], char["female"]
        )
        assert_includes(prompt, ["small ass"])


def test_bottom_adv_medium():
    """body_shape Medium -> bottom_adv='', add 'ass'."""
    row = {
        "main_action": "kiss",
        "bottom": "2",
    }
    loc = make_location(female_body_shape="Medium")
    char = make_character("Medium")
    prompt = _build_prompt(
        loc, "Tall Asian adult man", "Medium Asian adult woman", row, char["male"], char["female"]
    )
    assert_includes(prompt, [" ass"])


def test_bottom_adv_curvy():
    """body_shape Curvy/Voluptuous/Chubby -> bottom_adv='big ', add 'big ass'."""
    row = {
        "main_action": "kiss",
        "bottom": "2",
    }
    for shape in ["Curvy", "Voluptuous", "Chubby"]:
        loc = make_location(female_body_shape=shape)
        char = make_character(shape)
        prompt = _build_prompt(
            loc, "Tall Asian adult man", f"{shape} Asian adult woman", row, char["male"], char["female"]
        )
        assert_includes(prompt, ["big ass"])


def test_bottom_3_50_percent():
    """bottom=3 -> 50% add ass, 50% ignore."""
    row = {
        "main_action": "kiss",
        "bottom": "3",
    }
    with_ass = 0
    without_ass = 0
    for _ in range(20):
        loc = make_location(female_body_shape="Curvy")
        char = make_character("Curvy")
        prompt = _build_prompt(
            loc, "Tall Asian adult man", "Curvy Asian adult woman", row, char["male"], char["female"]
        )
        if "big ass" in prompt:
            with_ass += 1
        else:
            without_ass += 1
    assert with_ass >= 4 and without_ass >= 4, f"Expected ~50/50 split for bottom=3, got {with_ass}/{without_ass}"


def test_bottom_0_keeps_existing():
    """bottom=0 -> do NOT add ass modifier, do NOT add bottom value (existing behavior)."""
    row = {
        "main_action": "kiss",
        "bottom": "0",
    }
    loc = make_location(female_body_shape="Curvy")
    char = make_character("Curvy")
    prompt = _build_prompt(
        loc, "Tall Asian adult man", "Curvy Asian adult woman", row, char["male"], char["female"]
    )
    assert_not_includes(prompt, ["ass"])
    assert_not_includes(prompt, ["Grey leggings"])


def test_nipples_1_includes_nipples():
    """nipples=1 or 2 -> add female nipples to prompt."""
    row = {
        "main_action": "kiss",
        "nipples": "2",
    }
    loc = make_location()
    char = make_character("Athletic")
    prompt = _build_prompt(
        loc, "Tall Asian adult man", "Asian adult woman", row, char["male"], char["female"]
    )
    assert_includes(prompt, ["pink nipples"])


def test_nipples_0_ignores_nipples():
    """nipples=0 -> do NOT add nipples."""
    row = {
        "main_action": "kiss",
        "nipples": "0",
    }
    loc = make_location()
    char = make_character("Athletic")
    prompt = _build_prompt(
        loc, "Tall Asian adult man", "Asian adult woman", row, char["male"], char["female"]
    )
    assert_not_includes(prompt, ["pink nipples"])


def test_nipples_3_50_percent():
    """nipples=3 -> 50% include nipples, 50% ignore."""
    row = {
        "main_action": "kiss",
        "nipples": "3",
    }
    with_nipples = 0
    without_nipples = 0
    for _ in range(20):
        loc = make_location()
        char = make_character("Athletic")
        prompt = _build_prompt(
            loc, "Tall Asian adult man", "Asian adult woman", row, char["male"], char["female"]
        )
        if "pink nipples" in prompt:
            with_nipples += 1
        else:
            without_nipples += 1
    assert with_nipples >= 4 and without_nipples >= 4, f"Expected ~50/50 split for nipples=3, got {with_nipples}/{without_nipples}"


def test_all_new_fields_together():
    """Test all four new fields in one row."""
    row = {
        "main_action": "kiss",
        "male_croth": "1",
        "crotch": "2",
        "bottom": "2",
        "nipples": "2",
    }
    loc = make_location(female_body_shape="Curvy")
    char = make_character("Curvy")
    prompt = _build_prompt(
        loc, "Tall Asian adult man", "Curvy Asian adult woman", row, char["male"], char["female"]
    )
    assert_includes(prompt, [
        "veiny penis",
        "hairless pussy",
        "big ass",
        "pink nipples",
        "Grey leggings",
    ])


if __name__ == "__main__":
    tests = [
        test_male_croth_1_includes_penis,
        test_male_croth_0_ignores_penis,
        test_male_croth_3_50_percent,
        test_crotch_1_2_adds_pussy,
        test_crotch_3_50_percent,
        test_crotch_0_keeps_existing,
        test_bottom_adv_thin_slender,
        test_bottom_adv_medium,
        test_bottom_adv_curvy,
        test_bottom_3_50_percent,
        test_bottom_0_keeps_existing,
        test_nipples_1_includes_nipples,
        test_nipples_0_ignores_nipples,
        test_nipples_3_50_percent,
        test_all_new_fields_together,
    ]

    passed = 0
    failed = 0
    for test in tests:
        try:
            random.seed(42)
            test()
            print(f"  PASS: {test.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"  FAIL: {test.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"  ERROR: {test.__name__}: {e}")
            failed += 1

    print(f"\n{'=' * 40}")
    print(f"Results: {passed} passed, {failed} failed out of {len(tests)} tests")
    if failed:
        sys.exit(1)
