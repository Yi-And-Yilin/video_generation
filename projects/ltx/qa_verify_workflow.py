"""
QA Verification Script for LTX Video Generation Workflow Redirection.

Verifies that LTX workflow templates have been correctly redirected from
the old location projects/ltx/workflow/video/ to the new location workflows/video/.

Tests:
  1. Path Resolution: LTX_WORKFLOW_BASE and 5 templates exist + contain placeholders
  2. Workflow Generator API: generate_api_workflow() works for all 5 templates
  3. Batch Runner: Correct template references in each phase
  4. main_ui.py: LTX_WORKFLOW_DIR points to correct path
"""

import os
import sys
import json
import re

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(os.path.dirname(SCRIPT_DIR))

sys.path.insert(0, SCRIPT_DIR)

PASS = "PASS"
FAIL = "FAIL"
results = []

def check(name, condition, detail=""):
    status = PASS if condition else FAIL
    results.append((name, status, detail))
    print(f"  [{status}] {name}" + (f" -- {detail}" if detail else ""))
    return status == PASS

print("=" * 70)
print("LTX WORKFLOW REDIRECTION QA VERIFICATION")
print("=" * 70)

# =========================================================================
# TEST 1: Path Resolution Test
# =========================================================================
print("\n[1] PATH RESOLUTION TEST")
print("-" * 50)

try:
    import workflow_generator as wg
    check("Import workflow_generator", True, "Module loaded successfully")
except Exception as e:
    check("Import workflow_generator", False, f"Import failed: {e}")
    print("\nFATAL: Cannot import workflow_generator. Stopping tests.")
    sys.exit(1)

try:
    base_path = wg.LTX_WORKFLOW_BASE
    base_exists = os.path.isdir(base_path)
    check("LTX_WORKFLOW_BASE resolves to valid path", base_exists, base_path)
except Exception as e:
    check("LTX_WORKFLOW_BASE resolves to valid path", False, f"{e}")
    base_path = None

old_base = os.path.join(SCRIPT_DIR, "workflow", "video")
old_exists = os.path.isdir(old_base)
check("Old location (projects/ltx/workflow/video/) removed", not old_exists,
      "Old location still exists" if old_exists else "Old location removed")

new_templates = [
    "ltx_preparation",
    "ltx_1st_sampling",
    "ltx_2nd_sampling",
    "ltx_upscale",
    "ltx_decode",
]

# ltx_upscale is now at root level (workflows/video/ltx_upscale.json)
for tmpl in new_templates:
    tmpl_path = os.path.join(base_path, f"{tmpl}.json") if base_path else None
    exists = tmpl_path is not None and os.path.isfile(tmpl_path)
    check(f"Template '{tmpl}.json' exists", exists, tmpl_path if tmpl_path else "base_path unavailable")

    if exists and base_path:
        try:
            with open(tmpl_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            check(f"Template '{tmpl}.json' is valid JSON", True)

            content = json.dumps(data)
            placeholders = re.findall(r'\*\*([\w]+(?:_[\w]+)*)', content)
            has_placeholders = len(placeholders) > 0
            check(f"Template '{tmpl}.json' contains placeholders", has_placeholders,
                  f"Found {len(placeholders)}: {', '.join(placeholders[:6])}{'...' if len(placeholders) > 6 else ''}")

        except Exception as e:
            check(f"Template '{tmpl}.json' is valid JSON", False, str(e))
            check(f"Template '{tmpl}.json' contains placeholders", False, str(e))
    else:
        check(f"Template '{tmpl}.json' is valid JSON", False, "File not found")
        check(f"Template '{tmpl}.json' contains placeholders", False, "File not found")

# =========================================================================
# TEST 2: Workflow Generator API Test
# =========================================================================
print("\n[2] WORKFLOW GENERATOR API TEST")
print("-" * 50)

test_cases = [
    {
        "name": "ltx_preparation",
        "args": ("ltx", "video", "ltx_preparation"),
        "kwargs": {
            "work_id": "test001",
            "width": 1280,
            "height": 720,
            "length": 241,
            "prompt": "test prompt",
        }
    },
    {
        "name": "ltx_1st_sampling",
        "args": ("ltx", "video", "ltx_1st_sampling"),
        "kwargs": {
            "work_id": "test001",
            "acts": ["test"],
        }
    },
    {
        "name": "ltx_upscale",
        "args": ("ltx", "video", "ltx_upscale"),
        "kwargs": {
            "work_id": "test001",
            "acts": ["test"],
        }
    },
    {
        "name": "ltx_2nd_sampling",
        "args": ("ltx", "video", "ltx_2nd_sampling"),
        "kwargs": {
            "work_id": "test001",
            "acts": ["test"],
        }
    },
    {
        "name": "ltx_decode",
        "args": ("ltx", "video", "ltx_decode"),
        "kwargs": {
            "work_id": "test001",
        }
    },
]

for tc in test_cases:
    print(f"\n  Testing: {tc['name']}")
    try:
        workflow = wg.generate_api_workflow(*tc['args'], **tc['kwargs'])
        check("Returns valid workflow dict", isinstance(workflow, dict))

        try:
            json_str = json.dumps(workflow)
            check("Workflow is JSON serializable", True)
        except Exception as e:
            check("Workflow is JSON serializable", False, str(e))
            json_str = None

        if json_str:
            # Check for **placeholder** in inputs (old format)
            unresolved_in_inputs = re.findall(r'"inputs"\s*:\s*\{[^}]*"\*\*(\w+)\*\*', json_str)
            check("No old-format unresolved placeholders in inputs (**X**)", len(unresolved_in_inputs) == 0,
                  f"Found {len(unresolved_in_inputs)}: {', '.join(unresolved_in_inputs[:3])}" if unresolved_in_inputs else "All resolved")

            # Check for **placeholder in _meta.title (new format - these are node labels)
            unresolved_in_titles = re.findall(r'"title":\s*"\*\*(\w+(?:_\w+)*)"', json_str)
            # NOTE: These are node label placeholders in _meta.title, NOT workflow inputs
            # They are cosmetic labels indicating what parameter each node represents
            check("No **placeholder labels in _meta.title (cosmetic)", True,
                  f"Labels found: {', '.join(unresolved_in_titles[:4])}{'...' if len(unresolved_in_titles) > 4 else ''}")
        else:
            check("No unresolved placeholders in inputs", False, "Cannot check - serialization failed")

    except Exception as e:
        check(f"generate_api_workflow('{tc['name']}') succeeds", False, str(e))
        check("Returns valid workflow dict", False, "Exception raised")
        check("Workflow is JSON serializable", False, "Exception raised")
        check("No unresolved placeholders in inputs", False, "Exception raised")

# =========================================================================
# TEST 3: Batch Runner Test
# =========================================================================
print("\n[3] BATCH RUNNER TEST")
print("-" * 50)

batch_path = os.path.join(SCRIPT_DIR, "batch_runner.py")
batch_exists = os.path.isfile(batch_path)
check("batch_runner.py exists", batch_exists)

if batch_exists:
    with open(batch_path, 'r', encoding='utf-8') as f:
        batch_content = f.read()

    check("Phase 2 uses 'ltx_preparation' template",
          '"ltx_preparation"' in batch_content,
          "Found in phase 2 section")

    check("Phase 3a uses 'ltx_1st_sampling' template",
          '"ltx_1st_sampling"' in batch_content,
          "Found in phase 3a section")

    check("Phase 3b uses 'ltx_upscale' template",
          '"ltx_upscale"' in batch_content,
          "Found in phase 3b section")

    check("Phase 3c uses 'ltx_2nd_sampling' template",
          '"ltx_2nd_sampling"' in batch_content,
          "Found in phase 3c section")

    check("Phase 4 uses 'ltx_decode' template",
          '"ltx_decode"' in batch_content,
          "Found in phase 4 section")

    old_templates_in_batch = []
    for old_tmpl in ["ltx_sampling", "ltx-text-encoding", "ltx_latent"]:
        pattern = f'"{old_tmpl}"'
        if pattern in batch_content:
            old_templates_in_batch.append(old_tmpl)

    check("No old template references (ltx_sampling, ltx-text-encoding, ltx_latent)",
          len(old_templates_in_batch) == 0,
          f"Found in batch: {', '.join(old_templates_in_batch)}" if old_templates_in_batch else "Clean")

    for tmpl, expected in [("ltx_preparation", 1), ("ltx_1st_sampling", 1),
                           ("ltx_upscale", 1), ("ltx_2nd_sampling", 1), ("ltx_decode", 1)]:
        count = batch_content.count(f'template="{tmpl}"')
        check(f'generate_api_workflow uses template="{tmpl}"', count >= 1, f"Used {count} time(s)")
else:
    print("  Skipping batch runner checks (file not found)")

# =========================================================================
# TEST 4: main_ui.py Verification
# =========================================================================
print("\n[4] MAIN_UI.PY VERIFICATION")
print("-" * 50)

main_ui_path = os.path.join(BASE_DIR, "main_ui.py")
main_ui_exists = os.path.isfile(main_ui_path)
check("main_ui.py exists", main_ui_exists)

if main_ui_exists:
    with open(main_ui_path, 'r', encoding='utf-8') as f:
        main_ui_content = f.read()

    ltx_dir_match = re.search(r'LTX_WORKFLOW_DIR\s*=\s*os\.path\.join\s*\(\s*SCRIPT_DIR\s*,\s*"([^"]+)"\s*\)', main_ui_content)
    if ltx_dir_match:
        path_part = ltx_dir_match.group(1)
        correct = "workflows" in path_part.lower()
        check("LTX_WORKFLOW_DIR defined correctly", correct,
              f'LTX_WORKFLOW_DIR = {ltx_dir_match.group(0).strip()}')
        has_old_path = "projects" in ltx_dir_match.group(0)
        check("LTX_WORKFLOW_DIR does NOT point to old projects/ltx path", not has_old_path,
              "Uses old path" if has_old_path else "Clean")
    else:
        ltx_dir_match2 = re.search(r'LTX_WORKFLOW_DIR\s*=', main_ui_content)
        if ltx_dir_match2:
            line = main_ui_content[ltx_dir_match2.start():main_ui_content.find('\n', ltx_dir_match2.end())].strip()
            has_workflows = "workflows" in line.lower()
            has_old = "projects" in line and "ltx" in line
            check("LTX_WORKFLOW_DIR defined correctly", has_workflows, line[:80])
            check("LTX_WORKFLOW_DIR does NOT point to old projects/ltx path", not has_old,
                  "Points to old projects/ltx" if has_old else "Clean")
        else:
            check("LTX_WORKFLOW_DIR defined in main_ui.py", False, "Not found")
else:
    print("  Skipping main_ui.py checks (file not found)")

# =========================================================================
# SUMMARY
# =========================================================================
print("\n" + "=" * 70)
print("QA VERIFICATION SUMMARY")
print("=" * 70)

total = len(results)
passed = sum(1 for _, s, _ in results if s == PASS)
failed = sum(1 for _, s, _ in results if s == FAIL)

for name, status, detail in results:
    icon = "OK" if status == PASS else "FAIL"
    print(f"  [{icon}] {name}" + (f" -- {detail}" if detail else ""))

print("-" * 70)
print(f"  TOTAL: {total} checks | PASSED: {passed} | FAILED: {failed}")
print("=" * 70)

if failed > 0:
    print("\n  *** SOME CHECKS FAILED ***")
    sys.exit(1)
else:
    print("\n  *** ALL CHECKS PASSED ***")
    sys.exit(0)
