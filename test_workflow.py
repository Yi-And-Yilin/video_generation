#!/usr/bin/env python3
"""Test the actual workflow with a simple prompt."""

import sys
sys.path.insert(0, r"C:\SimpleAIHelper\video_generation")

from new_tab_workflow import run_new_tab_workflow

def status_callback(msg, end="\n"):
    print(msg, end=end, flush=True)

print("=" * 60)
print("TESTING NEW TAB WORKFLOW")
print("=" * 60)

result = run_new_tab_workflow(
    "A romantic couple in a bedroom",
    status_callback,
    stop_event=None,
    mode="Z"
)

print("\n" + "=" * 60)
print("WORKFLOW RESULT")
print("=" * 60)
print(f"Job ID: {result.get('job_id')}")
print(f"Character design: {result.get('character_design')}")
print(f"Location design: {result.get('location_design')}")
