"""
Integration Test Script for New Tab -> ComfyUI Workflow Generation
===================================================================

This script:
1. Reads a real task.json from tasks/ folder
2. For each location, for each prompt in the prompts list:
   - Extracts params using parameter_extraction module
   - Generates the ComfyUI workflow using workflow_generator module
3. Saves each generated workflow as a separate JSON file
4. Produces a summary report
5. Demonstrates the prompt extraction bug and provides a workaround

Usage:
    python integration_test_new_tab_to_comfyui.py

Author: QA Integration Test
Date: 2026-04-23
"""

import json
import sys
import os
from pathlib import Path
from datetime import datetime

# Add the project root to path so imports work
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))


def load_task_json(task_path: str) -> dict:
    """Load and return the parsed task.json."""
    with open(task_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def generate_workflows_for_task(task_path: str, output_dir: str,
                                 resolutions: list = None) -> list:
    """
    For each location and each prompt in task.json, generate a ComfyUI workflow.

    Parameters
    ----------
    task_path : str
        Path to the task.json file.
    output_dir : str
        Directory to save generated workflow JSON files.
    resolutions : list of str, optional
        List of resolution strings like ["1024*1024", "1024*768"].
        If None, uses ["1024*1024"].

    Returns
    -------
    list of dict
        Summary of all generated workflows.
    """
    if resolutions is None:
        resolutions = ["1024*1024"]

    # Load task data
    task_data = load_task_json(task_path)
    job_id = task_data.get("job_id", "unknown")
    user_requirements = task_data.get("user_requirements", "")
    locations = task_data.get("location_design", {}).get("locations", [])

    # Create output directory
    os.makedirs(output_dir, exist_ok=True)

    # Create a subdirectory for this job_id
    job_output_dir = os.path.join(output_dir, job_id)
    os.makedirs(job_output_dir, exist_ok=True)

    generated_workflows = []
    summary = {
        "task_path": task_path,
        "job_id": job_id,
        "user_requirements": user_requirements,
        "num_locations": len(locations),
        "resolutions_tested": resolutions,
        "total_workflows_generated": 0,
        "locations": [],
        "bugs_found": []
    }

    for loc_idx, location in enumerate(locations):
        location_name = location.get("location", f"Location_{loc_idx}")
        prompts = location.get("prompts", [])
        num_prompts = len(prompts)

        loc_summary = {
            "location_index": loc_idx,
            "location_name": location_name,
            "num_prompts": num_prompts,
            "prompts": []
        }
        summary["locations"].append(loc_summary)

        print(f"\n{'='*70}")
        print(f"Processing Location {loc_idx + 1}/{len(locations)}: {location_name}")
        print(f"{'='*70}")

        for prompt_idx, prompt in enumerate(prompts):
            for res_idx, resolution in enumerate(resolutions):
                print(f"\n  [{loc_idx+1}/{len(locations)}] Prompt {prompt_idx+1}/{num_prompts} | Resolution {resolution}")
                print(f"  Original prompt preview: {prompt[:80]}...")

                try:
                    # Import inside the loop so we only import when needed
                    from projects.ltx.parameter_extraction import (
                        extract_params_from_new_tab_task,
                        create_default_image_params
                    )
                    from projects.ltx.workflow_generator import (
                        generate_workflow_for_wan_image,
                        generate_workflow_from_standard_params
                    )

                    # Extract params for this location
                    params = extract_params_from_new_tab_task(
                        task_path,
                        scene_index=loc_idx,
                        resolution=resolution
                    )

                    # Check if the prompt matches what we expect
                    extracted_prompt = params.image_pos_prompt
                    prompt_matches = (extracted_prompt == prompt)

                    if not prompt_matches and prompt_idx > 0:
                        bug_note = (
                            f"BUG CONFIRMED: Location {loc_idx}, Prompt {prompt_idx} - "
                            f"extract_params_from_new_tab_task(scene_index={loc_idx}) "
                            f"returns prompts[{loc_idx} % {num_prompts}] instead of prompts[{prompt_idx}]"
                        )
                        print(f"  WARNING: {bug_note}")
                        summary["bugs_found"].append(bug_note)
                        print(f"  Extracted prompt: {extracted_prompt[:80]}...")
                    else:
                        print(f"  Extracted prompt: {extracted_prompt[:80]}...")

                    # --- WORKAROUND: Manually inject the correct prompt ---
                    # Since the workflow generator ultimately uses the params object
                    # which gets converted to a workflow, we need to patch it.
                    # The easiest way is to generate the workflow first, then
                    # find and replace the positive prompt string in the workflow dict.

                    # Generate the workflow using the standard pipeline
                    workflow = generate_workflow_for_wan_image(
                        task_path=task_path,
                        scene_index=loc_idx,
                        resolution=resolution
                    )

                    # Patch the workflow to use the correct prompt for this index
                    # Find the StringConstant node that holds the positive prompt
                    for node_id, node_data in workflow.items():
                        if isinstance(node_data, dict) and node_data.get("class_type") == "StringConstant":
                            inputs = node_data.get("inputs", {})
                            if "string" in inputs:
                                # Check if this is the positive prompt string node
                                # (it should contain location-specific text)
                                current_str = inputs["string"]
                                if current_str != prompt:
                                    # Replace with the correct prompt
                                    workflow[node_id]["inputs"]["string"] = prompt
                                    print(f"  PATCHED: Node {node_id} prompt injected correctly")
                                    break

                    # Build output filename
                    res_parts = resolution.split('*')
                    res_short = res_parts[0].replace('*', 'x')
                    filename = (
                        f"{job_id}_loc{loc_idx:02d}_"
                        f"prompt{prompt_idx:02d}_"
                        f"res{res_short}.json"
                    )
                    output_path = os.path.join(job_output_dir, filename)

                    # Save workflow
                    with open(output_path, 'w', encoding='utf-8') as f:
                        json.dump(workflow, f, indent=2, ensure_ascii=False)

                    # Collect metadata
                    workflow_size = os.path.getsize(output_path)
                    node_count = len(workflow)

                    print(f"  -> Saved: {filename} ({node_count} nodes, {workflow_size} bytes)")

                    generated_workflows.append({
                        "location": location_name,
                        "location_index": loc_idx,
                        "prompt_index": prompt_idx,
                        "resolution": resolution,
                        "output_file": filename,
                        "output_path": output_path,
                        "node_count": node_count,
                        "workflow_size_bytes": workflow_size,
                        "prompt_matched_original": prompt_matches
                    })

                    loc_summary["prompts"].append({
                        "prompt_index": prompt_idx,
                        "prompt_preview": prompt[:100],
                        "resolution": resolution,
                        "output_file": filename,
                        "bug_note": not prompt_matches
                    })

                    summary["total_workflows_generated"] += 1

                except Exception as e:
                    print(f"  -> ERROR: {type(e).__name__}: {e}")
                    import traceback
                    traceback.print_exc()
                    loc_summary["prompts"].append({
                        "prompt_index": prompt_idx,
                        "resolution": resolution,
                        "error": str(e)
                    })

    # Save summary report
    summary_path = os.path.join(job_output_dir, "integration_test_summary.json")
    with open(summary_path, 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    # Print summary
    print(f"\n{'#'*70}")
    print(f"# INTEGRATION TEST SUMMARY")
    print(f"#{'#'*70}")
    print(f"  Task Path:        {task_path}")
    print(f"  Job ID:           {job_id}")
    print(f"  Resolutions:      {', '.join(resolutions)}")
    print(f"  Locations:        {summary['num_locations']}")
    print(f"  Workflows Gen:    {summary['total_workflows_generated']}")
    print(f"  Output Dir:       {job_output_dir}")
    print(f"  Summary File:     {summary_path}")

    if summary["bugs_found"]:
        print(f"\n  BUGS FOUND ({len(summary['bugs_found'])}):")
        for bug in summary["bugs_found"]:
            print(f"    - {bug}")

    for loc_summary in summary["locations"]:
        print(f"\n  Location {loc_summary['location_index']}: {loc_summary['location_name']}")
        for p in loc_summary["prompts"]:
            if p.get("bug_note"):
                print(f"    Prompt {p['prompt_index']}: BUG (wrong prompt extracted)")
            else:
                print(f"    Prompt {p['prompt_index']}: {p.get('prompt_preview', 'N/A')[:70]}...")
            print(f"      -> {p.get('output_file', 'ERROR: ' + p.get('error', 'unknown'))}")

    return generated_workflows


def analyze_workflow_structure(workflow: dict) -> dict:
    """Analyze the structure of a generated workflow."""
    node_types = {}
    for node_id, node_data in workflow.items():
        if isinstance(node_data, dict):
            class_name = node_data.get("_class", node_data.get("class_type", "Unknown"))
            node_types[class_name] = node_types.get(class_name, 0) + 1

    return {
        "total_nodes": len(workflow),
        "node_type_distribution": node_types
    }


def print_workflow_comparison(workflows: list):
    """Print a comparison of generated workflows."""
    print(f"\n{'~'*70}")
    print(f"  WORKFLOW COMPARISON")
    print(f"~{'~'*70}")

    for w in workflows:
        output_path = w["output_path"]
        with open(output_path, 'r', encoding='utf-8') as f:
            wf = json.load(f)
        analysis = analyze_workflow_structure(wf)

        # Extract the positive prompt from the workflow
        pos_prompt = ""
        for node_id, node_data in wf.items():
            if isinstance(node_data, dict) and node_data.get("class_type") == "StringConstant":
                s = node_data.get("inputs", {}).get("string", "")
                if len(s) > 30 and "man" in s.lower():
                    pos_prompt = s
                    break

        print(f"\n  {w['output_file']}")
        print(f"    Location:       {w['location']}")
        print(f"    Resolution:     {w['resolution']}")
        print(f"    Total Nodes:    {analysis['total_nodes']}")
        print(f"    Unique Types:   {len(analysis['node_type_distribution'])}")
        print(f"    Positive Prompt: {pos_prompt[:100]}...")


def main():
    """Main entry point for the integration test."""
    print(f"Integration Test: New Tab -> ComfyUI Workflow Generation")
    print(f"Project Root:     {PROJECT_ROOT}")
    print(f"Timestamp:        {datetime.now().isoformat()}")
    print()

    # Define the task file to test
    task_path = str(PROJECT_ROOT / "tasks" / "wzk4h" / "task.json")

    if not os.path.exists(task_path):
        print(f"ERROR: Task file not found: {task_path}")
        sys.exit(1)

    # Define output directory
    output_dir = str(PROJECT_ROOT / "integration_test_output")

    print(f"Loading task: {task_path}")
    task_data = load_task_json(task_path)
    print(f"  Job ID:       {task_data.get('job_id')}")
    print(f"  Requirements: {task_data.get('user_requirements', '')[:80]}...")
    locations = task_data.get("location_design", {}).get("locations", [])
    print(f"  Locations:    {len(locations)}")
    for i, loc in enumerate(locations):
        prompts = loc.get("prompts", [])
        print(f"    [{i}] {loc.get('location', 'Unknown')} ({len(prompts)} prompts)")

    # Generate workflows
    workflows = generate_workflows_for_task(
        task_path=task_path,
        output_dir=output_dir,
        resolutions=["1024*1024"]
    )

    # Analyze and compare workflows
    if workflows:
        print_workflow_comparison(workflows)

    print(f"\n{'='*70}")
    print(f"  Integration test complete!")
    print(f"  Generated files saved to: {output_dir}")
    print(f"{'='*70}")


if __name__ == "__main__":
    main()
