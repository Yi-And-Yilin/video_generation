"""
Comprehensive QA tests for LoRA generation fixes.

Tests:
1. CSV Lookup for LTX templates — load_lora_lookup() finds rows correctly
2. Placeholder matching protects hardcoded paths — apply_wan_placeholders() doesn't touch Distill Lora node
3. End-to-end workflow generation with acts — generate_api_workflow() produces correct nodes
4. Empty acts fallback — generate_api_workflow() with acts=[] uses defaults
"""

import os
import sys
import json

BASE_DIR = r"C:\SimpleAIHelper\video_generation"
sys.path.insert(0, os.path.join(BASE_DIR, "projects", "ltx"))
sys.path.insert(0, BASE_DIR)

from workflow_generator import generate_api_workflow, load_lora_lookup, apply_wan_placeholders
import projects.ltx.workflow_generator as wg

# CSV path for testing
CSV_PATH = os.path.join(BASE_DIR, "lookup", "lora_lookup.csv")
TEMPLATE_PATH = os.path.join(BASE_DIR, "workflows", "video", "ltx_1st_sampling.json")


class TestResult:
    def __init__(self):
        self.results = []
        self.pass_count = 0
        self.fail_count = 0

    def add(self, test_name, passed, detail=""):
        status = "PASS" if passed else "FAIL"
        self.results.append((test_name, status, detail))
        if passed:
            self.pass_count += 1
        else:
            self.fail_count += 1
        print(f"  [{status}] {test_name}")
        if detail:
            print(f"         {detail}")


results = TestResult()


def test_1_csv_lookup():
    """Test 1: CSV Lookup for LTX templates"""
    print("\n" + "=" * 70)
    print("TEST 1: CSV Lookup for LTX Templates")
    print("=" * 70)

    lookup = load_lora_lookup(csv_path=CSV_PATH, filter_type="video", workflow_name=None)
    print(f"\n  Lookup keys (video, no filter): {list(lookup.keys())[:10]}...")

    ltx_1st = load_lora_lookup(csv_path=CSV_PATH, filter_type="video", workflow_name="ltx_1st_sampling")
    print(f"\n  Lookup keys (ltx_1st_sampling): {list(ltx_1st.keys())[:10]}...")

    # Test: lying_on_tummy_doggy should be in lookup
    test_1a = "lying_on_tummy_doggy found in ltx_1st_sampling lookup"
    found_lod = "lying_on_tummy_doggy" in ltx_1st
    results.add(test_1a, found_lod)
    if not found_lod:
        results.add(f"  Available keys: {list(ltx_1st.keys())}", False)

    if found_lod:
        # Verify lora1 and lora2 values
        loras = ltx_1st["lying_on_tummy_doggy"]
        lora_names = [l["name"] for l in loras]
        lora_strengths = [l["strength"] for l in loras]

        test_1b = "lora1_name is ltx\\nsfw\\NSFW_furryv2.safetensors"
        results.add(test_1b, len(lora_names) > 0 and lora_names[0] == r"ltx\nsfw\NSFW_furryv2.safetensors")
        if len(lora_names) > 0 and lora_names[0] != r"ltx\nsfw\NSFW_furryv2.safetensors":
            results.add(f"  Got lora1_name: {lora_names[0]}", False)

        test_1c = "lora1_strength is 0.9"
        results.add(test_1c, len(lora_strengths) > 0 and lora_strengths[0] == 0.9)
        if len(lora_strengths) > 0 and lora_strengths[0] != 0.9:
            results.add(f"  Got lora1_strength: {lora_strengths[0]}", False)

        test_1d = "lora2_name is ltx\\nsfw\\Female Nudity.safetensors"
        results.add(test_1d, len(lora_names) > 1 and lora_names[1] == r"ltx\nsfw\Female Nudity.safetensors")
        if len(lora_names) > 1 and lora_names[1] != r"ltx\nsfw\Female Nudity.safetensors":
            results.add(f"  Got lora2_name: {lora_names[1]}", False)

        test_1e = "lora2_strength is 0.3"
        results.add(test_1e, len(lora_strengths) > 1 and lora_strengths[1] == 0.3)
        if len(lora_strengths) > 1 and lora_strengths[1] != 0.3:
            results.add(f"  Got lora2_strength: {lora_strengths[1]}", False)

    # Test: ltx_2nd_sampling should also find the same row
    ltx_2nd = load_lora_lookup(csv_path=CSV_PATH, filter_type="video", workflow_name="ltx_2nd_sampling")
    test_1f = "lying_on_tummy_doggy found in ltx_2nd_sampling lookup"
    results.add(test_1f, "lying_on_tummy_doggy" in ltx_2nd)
    if not test_1f:
        results.add(f"  ltx_2nd_sampling keys: {list(ltx_2nd.keys())[:10]}", False)

    # Test: ltx_preparation should also find the same row
    ltx_prep = load_lora_lookup(csv_path=CSV_PATH, filter_type="video", workflow_name="ltx_preparation")
    test_1g = "lying_on_tummy_doggy found in ltx_preparation lookup"
    results.add(test_1g, "lying_on_tummy_doggy" in ltx_prep)

    # Test: ltx_decode should also find the same row
    ltx_dec = load_lora_lookup(csv_path=CSV_PATH, filter_type="video", workflow_name="ltx_decode")
    test_1h = "lying_on_tummy_doggy found in ltx_decode lookup"
    results.add(test_1h, "lying_on_tummy_doggy" in ltx_dec)

    # Test: non-LTX templates should NOT match (e.g., z-image)
    zimg = load_lora_lookup(csv_path=CSV_PATH, filter_type="image", workflow_name="z-image")
    test_1i = "z-image lookup works for image type"
    results.add(test_1i, len(zimg) > 0)
    if not test_1i:
        results.add(f"  z-image lookup has {len(zimg)} entries", False)


def test_2_placeholder_matching():
    """Test 2: Placeholder matching protects hardcoded paths"""
    print("\n" + "=" * 70)
    print("TEST 2: Placeholder Matching Protects Hardcoded Paths")
    print("=" * 70)

    with open(TEMPLATE_PATH, 'r', encoding='utf-8') as f:
        workflow = json.load(f)

    print(f"\n  Node 9 (Distill Lora) lora_name: {workflow['9']['inputs']['lora_name']}")
    print(f"  Node 9 (Distill Lora) strength_model: {workflow['9']['inputs']['strength_model']}")
    print(f"  Node 10 (Load LoRA 1) lora_name: {workflow['10']['inputs']['lora_name']}")

    # Simulate params dict
    params = {
        "lora1_name": r"ltx\nsfw\NSFW_furryv2.safetensors",
        "lora1_strength": 0.3,
        "lora2_name": r"ltx\nsfw\Female Nudity.safetensors",
        "lora2_strength": 0.9,
    }
    print(f"  Params dict: {params}")
    print(f"  Params keys: {list(params.keys())}")

    modified = apply_wan_placeholders(workflow, params)

    # Verify node 9 is untouched
    test_2a = "Node 9 lora_name is NOT replaced (still hardcoded)"
    node9_lora = modified["9"]["inputs"]["lora_name"]
    expected_hardcoded = r"ltx\ltx-2.3-22b-distilled-lora-384-1.1.safetensors"
    results.add(test_2a, node9_lora == expected_hardcoded)
    if node9_lora != expected_hardcoded:
        results.add(f"  Expected: {expected_hardcoded}", False)
        results.add(f"  Got: {node9_lora}", False)

    test_2b = "Node 9 strength_model is NOT replaced (still 0.5)"
    results.add(test_2b, modified["9"]["inputs"]["strength_model"] == 0.5)
    if modified["9"]["inputs"]["strength_model"] != 0.5:
        results.add(f"  Expected: 0.5, Got: {modified['9']['inputs']['strength_model']}", False)

    # Verify node 10 placeholder IS replaced (lora2_name -> Female Nudity from CSV)
    test_2c = "Node 10 lora_name placeholder IS replaced (lora2_name -> Female Nudity)"
    node10_lora = modified["10"]["inputs"]["lora_name"]
    results.add(test_2c, node10_lora == r"ltx\nsfw\Female Nudity.safetensors")
    if node10_lora != r"ltx\nsfw\Female Nudity.safetensors":
        results.add(f"  Expected: ltx\\nsfw\\Female Nudity.safetensors, Got: {node10_lora}", False)

    # Verify node 10 strength_model becomes float (from test params lora2_strength=0.9)
    test_2d = "Node 10 strength_model becomes float (not null or string)"
    node10_strength = modified["10"]["inputs"]["strength_model"]
    results.add(test_2d, isinstance(node10_strength, (int, float)))
    if isinstance(node10_strength, (int, float)):
        print(f"    Node 10 strength_model = {node10_strength} (from lora2_strength=0.9 test param)")
    else:
        results.add(f"  Expected float/int, Got: {type(node10_strength).__name__} = {node10_strength}", False)


def test_3_end_to_end_with_acts():
    """Test 3: End-to-end workflow generation with acts=["lying_on_tummy_doggy"]"""
    print("\n" + "=" * 70)
    print("TEST 3: End-to-End Workflow Generation (with acts)")
    print("=" * 70)

    workflow = generate_api_workflow(
        project="ltx",
        type="video",
        template="ltx_1st_sampling",
        acts=["lying_on_tummy_doggy"],
        width=1280,
        height=720,
        length=241,
        prompt="test prompt",
        video_pos_prompt="test prompt",
        negative_prompt="ugly, deformed",
        work_id="test001",
        fps=24,
    )

    # Check node 9 (Distill Lora) — must be UNTOUCHED
    test_3a = "Node 9 (Distill Lora) lora_name is hardcoded and UNCHANGED"
    node9_lora = workflow["9"]["inputs"]["lora_name"]
    expected_hardcoded = r"ltx\ltx-2.3-22b-distilled-lora-384-1.1.safetensors"
    results.add(test_3a, node9_lora == expected_hardcoded)
    if node9_lora != expected_hardcoded:
        results.add(f"  Expected: {expected_hardcoded}", False)
        results.add(f"  Got: {node9_lora}", False)

    test_3b = "Node 9 strength_model is 0.5 (UNTOUCHED)"
    results.add(test_3b, workflow["9"]["inputs"]["strength_model"] == 0.5)
    if workflow["9"]["inputs"]["strength_model"] != 0.5:
        results.add(f"  Expected: 0.5, Got: {workflow['9']['inputs']['strength_model']}", False)

    # Check node 10 (Load LoRA 1) — lora_name should come from CSV lora2_name lookup
    test_3c = "Node 10 lora_name is from CSV lookup (lora2 -> Female Nudity)"
    node10_lora = workflow["10"]["inputs"]["lora_name"]
    results.add(test_3c, node10_lora == r"ltx\nsfw\Female Nudity.safetensors")
    if node10_lora != r"ltx\nsfw\Female Nudity.safetensors":
        results.add(f"  Expected: ltx\\nsfw\\Female Nudity.safetensors, Got: {node10_lora}", False)

    # strength_model should come from lora2_strength=0.3 (not lora1)
    test_3d = "Node 10 strength_model is 0.3 (float from lora2_strength, not 0.9)"
    node10_strength = workflow["10"]["inputs"]["strength_model"]
    results.add(test_3d, isinstance(node10_strength, float) and node10_strength == 0.3)
    if isinstance(node10_strength, float):
        if node10_strength == 0.3:
            print(f"    Node 10 strength_model = {node10_strength} (correct)")
        else:
            print(f"    Node 10 strength_model = {node10_strength} (expected 0.3)")
    else:
        print(f"    Node 10 strength_model type = {type(node10_strength).__name__} (expected float)")

    # Debug: show what all nodes look like
    print(f"\n  Node 9: class={workflow['9'].get('class_type')}, lora_name={workflow['9']['inputs']['lora_name']}")
    print(f"  Node 9 strength_model: {workflow['9']['inputs']['strength_model']} (type={type(workflow['9']['inputs']['strength_model']).__name__})")
    print(f"  Node 10: class={workflow['10'].get('class_type')}, lora_name={workflow['10']['inputs']['lora_name']}")
    print(f"  Node 10 strength_model: {workflow['10']['inputs']['strength_model']} (type={type(workflow['10']['inputs']['strength_model']).__name__})")


def test_4_empty_acts_fallback():
    """Test 4: Empty acts fallback"""
    print("\n" + "=" * 70)
    print("TEST 4: Empty Acts Fallback")
    print("=" * 70)

    workflow = generate_api_workflow(
        project="ltx",
        type="video",
        template="ltx_1st_sampling",
        acts=[],
        width=1280,
        height=720,
        length=241,
        prompt="test prompt",
        video_pos_prompt="test prompt",
        negative_prompt="ugly, deformed",
        work_id="test002",
        fps=24,
    )

    # Node 9 must still be untouched
    test_4a = "Node 9 (Distill Lora) lora_name is UNCHANGED with empty acts"
    node9_lora = workflow["9"]["inputs"]["lora_name"]
    expected_hardcoded = r"ltx\ltx-2.3-22b-distilled-lora-384-1.1.safetensors"
    results.add(test_4a, node9_lora == expected_hardcoded)
    if node9_lora != expected_hardcoded:
        results.add(f"  Expected: {expected_hardcoded}", False)
        results.add(f"  Got: {node9_lora}", False)

    # Node 10 should use default LoRA (add-detail at strength 0.0)
    test_4b = "Node 10 lora_name is default (add-detail.safetensors) with empty acts"
    node10_lora = workflow["10"]["inputs"]["lora_name"]
    results.add(test_4b, node10_lora == r"xl\add-detail.safetensors")
    if node10_lora != r"xl\add-detail.safetensors":
        results.add(f"  Expected: xl\\add-detail.safetensors, Got: {node10_lora}", False)

    test_4c = "Node 10 strength_model is 0.0 (default) with empty acts"
    node10_strength = workflow["10"]["inputs"]["strength_model"]
    results.add(test_4c, isinstance(node10_strength, (int, float)) and node10_strength == 0.0)
    if node10_strength != 0.0:
        results.add(f"  Expected: 0.0, Got: {node10_strength} (type={type(node10_strength).__name__})", False)


def test_5_other_ltx_templates():
    """Test 5: Other LTX templates also match ltx_standard in CSV"""
    print("\n" + "=" * 70)
    print("TEST 5: Other LTX Templates Match ltx_standard")
    print("=" * 70)

    templates = ["ltx_1st_sampling", "ltx_2nd_sampling", "ltx_preparation", "ltx_decode", "ltx_upscale"]

    for tmpl in templates:
        lookup = load_lora_lookup(csv_path=CSV_PATH, filter_type="video", workflow_name=tmpl)
        test_name = f"'{tmpl}' finds lying_on_tummy_doggy"
        results.add(test_name, "lying_on_tummy_doggy" in lookup)
        if "lying_on_tummy_doggy" not in lookup:
            results.add(f"  Available keys for '{tmpl}': {list(lookup.keys())[:10]}", False)


def test_6_placeholder_replacement_mechanism():
    """Test 6: Verify ** placeholder requirement"""
    print("\n" + "=" * 70)
    print("TEST 6: Placeholder ** Requirement (No False Replacements)")
    print("=" * 70)

    workflow = {"1": {"inputs": {"hardcoded_path": r"some\path\file.safetensors"}, "class_type": "SomeNode"}}
    params = {"hardcoded_path": r"ltx\nsfw\NSFW_furryv2.safetensors"}

    modified = apply_wan_placeholders(deepcopy(workflow), params)

    test_6a = "Plain strings without ** are NOT replaced"
    results.add(test_6a, modified["1"]["inputs"]["hardcoded_path"] == r"some\path\file.safetensors")
    if modified["1"]["inputs"]["hardcoded_path"] != r"some\path\file.safetensors":
        results.add(f"  Expected: some\\path\\file.safetensors, Got: {modified['1']['inputs']['hardcoded_path']}", False)

    # Now test with ** wrapper
    workflow2 = {"1": {"inputs": {"lora_name": "**lora2_name**", "strength_model": None}, "class_type": "LoraLoaderModelOnly"}}
    params2 = {"lora2_name": r"ltx\nsfw\NSFW_furryv2.safetensors", "lora2_strength": 0.9}

    try:
        modified2 = apply_wan_placeholders(deepcopy(workflow2), params2)
        test_6b = "With ** wrapper, placeholder IS replaced"
        results.add(test_6b, modified2["1"]["inputs"]["lora_name"] == r"ltx\nsfw\NSFW_furryv2.safetensors")
    except Exception as e:
        results.add(f"With ** wrapper, placeholder IS replaced (error: {e})", False)


import copy
def deepcopy(obj):
    return copy.deepcopy(obj)


if __name__ == "__main__":
    test_1_csv_lookup()
    test_2_placeholder_matching()
    test_3_end_to_end_with_acts()
    test_4_empty_acts_fallback()
    test_5_other_ltx_templates()
    test_6_placeholder_replacement_mechanism()

    print("\n" + "=" * 70)
    print(f"SUMMARY: {results.pass_count} passed, {results.fail_count} failed, {len(results.results)} total")
    print("=" * 70)

    if results.fail_count > 0:
        print("\nFAILED TESTS:")
        for name, status, detail in results.results:
            if status == "FAIL":
                print(f"  {name}")
                if detail:
                    print(f"    {detail}")
    else:
        print("\nALL TESTS PASSED!")
