"""
Unified workflow and template selection system for Video Generation UI.

Provides:
- TemplateCatalog: static methods for scanning/loading workflow templates, prompt templates, and image tasks
- apply_placeholders_unified(): placeholder substitution for workflow JSON files
- create_comfyui_selector_ui(): helper to create a ComfyUI workflow selector dropdown
"""

import os
import json
import csv
import glob as glob_module
from typing import List, Dict, Any, Tuple, Optional

# Point to the project root (same as main_ui.py SCRIPT_DIR)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

WAN_WORKFLOW_DIR = os.path.join(SCRIPT_DIR, "workflows")
WAN_WORKFLOW_IMAGE_DIR = os.path.join(WAN_WORKFLOW_DIR, "image")
WAN_WORKFLOW_VIDEO_DIR = os.path.join(WAN_WORKFLOW_DIR, "video")
LTX_PROMPTS_DIR = os.path.join(SCRIPT_DIR, "projects", "ltx", "prompts")
LTX_TASKS_DIR = os.path.join(SCRIPT_DIR, "projects", "ltx", "tasks")
TASK_STEPS_CSV = os.path.join(SCRIPT_DIR, "task_steps.csv")
CHECKPOINTS_TXT = os.path.join(WAN_WORKFLOW_IMAGE_DIR, "checkpoints.txt")


class TemplateCatalog:
    """Static registry and utilities for workflow/prompt/task templates."""

    REGISTRY = [
        ("FlashSVR", "FlashSVR", "wan_workflow", os.path.join(WAN_WORKFLOW_DIR, "FlashSVR.json"), "shared"),
        ("clean_up", "clean_up", "wan_workflow", os.path.join(WAN_WORKFLOW_DIR, "clean_up.json"), "shared"),
        ("final_upscale", "final_upscale", "wan_workflow", os.path.join(WAN_WORKFLOW_DIR, "final_upscale.json"), "shared"),
    ]

    # Priority ordering for discovered templates
    TEMPLATE_PRIORITY = ["FlashSVR", "clean_up", "final_upscale", "wan_image"]

    @classmethod
    def _scan_templates_recursive(cls, directory: str) -> List[str]:
        """Scan a directory for .json template files and return base names."""
        if not os.path.isdir(directory):
            return []
        return [f[:-5] for f in os.listdir(directory) if f.endswith('.json')]

    @classmethod
    def get_checkpoint_options(cls) -> List[str]:
        """
        Read checkpoint names from checkpoints.txt in workflows/image/.

        Format: one checkpoint filename per line. Lines starting with # are comments.
        Blank lines are ignored.

        Returns
        -------
        List[str]
            Sorted list of checkpoint filenames (e.g., ['checkpoint_a.safetensors', ...])
        """
        if not os.path.isfile(CHECKPOINTS_TXT):
            return []
        checkpoints = []
        with open(CHECKPOINTS_TXT, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    checkpoints.append(line)
        return checkpoints

    @classmethod
    def get_wan_workflow_options(cls) -> List[str]:
        """
        Scan workflows/ (root, image/, video/ subfolders)
        and return sorted template names.
        Includes FlashSVR, clean_up, final_upscale, wan_image at top,
        then alphabetical others.
        """
        all_names = set()
        # Root-level templates (shared)
        all_names.update(cls._scan_templates_recursive(WAN_WORKFLOW_DIR))
        # Image templates
        all_names.update(cls._scan_templates_recursive(WAN_WORKFLOW_IMAGE_DIR))
        # Video templates
        all_names.update(cls._scan_templates_recursive(WAN_WORKFLOW_VIDEO_DIR))

        priority = [name for name in cls.TEMPLATE_PRIORITY if name in all_names]
        remaining = sorted([name for name in all_names if name not in cls.TEMPLATE_PRIORITY])
        return priority + remaining

    @classmethod
    def _resolve_template_path(cls, template_key: str) -> Optional[str]:
        """
        Resolve which subfolder a template belongs to and return its full path.

        Resolution order:
        1. Root WAN_WORKFLOW_DIR (shared templates: FlashSVR, clean_up, final_upscale)
        2. Image subfolder (wan_image)
        3. Video subfolder (wan_2.1_*, wan_2.2_*, etc.)
        4. Raise FileNotFoundError if not found anywhere
        """
        # Check root (shared templates)
        root_path = os.path.join(WAN_WORKFLOW_DIR, f"{template_key}.json")
        if os.path.exists(root_path):
            return root_path

        # Check image subfolder
        image_path = os.path.join(WAN_WORKFLOW_IMAGE_DIR, f"{template_key}.json")
        if os.path.exists(image_path):
            return image_path

        # Check video subfolder
        video_path = os.path.join(WAN_WORKFLOW_VIDEO_DIR, f"{template_key}.json")
        if os.path.exists(video_path):
            return video_path

        return None

    @classmethod
    def load_template(cls, template_key: str) -> Dict[str, Any]:
        """
        Load a workflow template JSON from workflows/{template_key}.json.
        Automatically resolves subfolders (image/ for wan_image, video/ for wan_2.*_step*).
        Returns the parsed JSON as a dictionary.
        """
        template_path = cls._resolve_template_path(template_key)
        if template_path is None:
            raise FileNotFoundError(
                f"Workflow template not found: {template_key}.json "
                f"(searched root, image/, and video/ under workflows/)"
            )
        with open(template_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    @classmethod
    def get_prompt_template_options(cls) -> List[str]:
        """
        Scan projects/ltx/prompts/*.md (excluding user-prompt.md) and return sorted names.
        """
        if not os.path.isdir(LTX_PROMPTS_DIR):
            return []

        files = []
        for f in os.listdir(LTX_PROMPTS_DIR):
            if f.endswith('.md') and f != 'user-prompt.md':
                files.append(f[:-3])  # Remove .md extension

        files.sort()
        return files

    @classmethod
    def get_image_task_options(cls) -> List[str]:
        """
        Scan projects/ltx/tasks/*.json and return sorted filenames (reverse chronological).
        """
        if not os.path.isdir(LTX_TASKS_DIR):
            return []

        files = [f for f in os.listdir(LTX_TASKS_DIR) if f.endswith('.json')]
        files.sort(reverse=True)
        return files

    @classmethod
    def get_task_steps_from_csv(cls, task_name: str) -> Optional[List[Tuple[str, bool, str]]]:
        """
        Read task_steps.csv and return steps for a given task_name.

        Returns:
            List of (workflow_name, save_video_bool, category) tuples, or None if not found.
        """
        try:
            with open(TASK_STEPS_CSV, mode='r', encoding='utf-8') as f:
                reader = csv.reader(f)
                header = next(reader, None)
                if not header:
                    return None

                idx_name = header.index('task_name')
                idx_wf = header.index('workflow_name')
                idx_sv = header.index('save_video')
                idx_cat = header.index('category')

                steps = []
                for row in reader:
                    if len(row) > max(idx_name, idx_wf, idx_sv, idx_cat) and row[idx_name].strip() == task_name:
                        save_video = row[idx_sv].strip().lower() == 'yes'
                        category = row[idx_cat].strip()
                        steps.append((row[idx_wf].strip(), save_video, category))
                return steps if steps else None
        except Exception:
            return None

    @classmethod
    def get_csv_task_names(cls) -> List[str]:
        """
        Read task_steps.csv and return sorted unique task names.
        """
        try:
            with open(TASK_STEPS_CSV, mode='r', encoding='utf-8') as f:
                reader = csv.reader(f)
                next(reader, None)  # skip header
                names = sorted(set(row[0].strip() for row in reader if len(row) > 0))
                return names
        except Exception:
            return []


def apply_placeholders_unified(workflow_json: Dict[str, Any], params_dict: Dict[str, Any]) -> Dict[str, Any]:
    """
    Apply placeholder -> value substitution to a workflow JSON.

    Iterates through all nodes and replaces **placeholder** tokens in string
    input values with values from params_dict.

    Type conversion:
    - If class_type is "JWInteger" or placeholder name contains "strength",
      convert to float or int as appropriate.

    Parameters
    ----------
    workflow_json : dict
        The workflow JSON to modify (modified in-place, also returned).
    params_dict : dict
        Mapping of placeholder names (without ** prefix) to their replacement values.

    Returns
    -------
    dict
        The modified workflow JSON.
    """
    for node_id, node in workflow_json.items():
        if not isinstance(node, dict):
            continue
        cls = node.get("class_type", "")
        inputs = node.get("inputs", {})

        for k, v in inputs.items():
            if not isinstance(v, str):
                continue

            new_val = v
            for placeholder, repl_val in params_dict.items():
                p_key = f"**{placeholder}**"
                if isinstance(new_val, str) and p_key in new_val:
                    should_convert = (cls == "JWInteger" or
                                      "strength" in placeholder or
                                      "seed" in placeholder or
                                      "random" in placeholder or
                                      "width" in placeholder or
                                      "height" in placeholder or
                                      "fps" in placeholder or
                                      "steps" in placeholder or
                                      "shift" in placeholder or
                                      "denoise" in placeholder or
                                      "cfg" in placeholder)

                    if should_convert:
                        try:
                            if "strength" in placeholder or cls == "Float":
                                new_val = float(repl_val)
                            else:
                                new_val = int(repl_val)
                        except (ValueError, TypeError):
                            new_val = str(repl_val)
                    else:
                        new_val = new_val.replace(p_key, str(repl_val))

            inputs[k] = new_val

    return workflow_json


def create_comfyui_selector_ui(parent, var=None, label_text="ComfyUI:"):
    """
    Create a ComfyUI workflow selector dropdown for use in a tab.

    Parameters
    ----------
    parent : tk.Widget
        Parent widget to pack into.
    var : tk.StringVar, optional
        Existing StringVar to bind. If None, a new one is created.
    label_text : str
        Text for the label widget (default "ComfyUI:").

    Returns
    -------
    tuple
        (frame, stringvar, combobox)
    """
    import tkinter as tk
    from tkinter import ttk

    if var is None:
        var = tk.StringVar(value="meichiILIghtMIXV1_meichiILUstMIXV1.safetensors")

    frame = tk.Frame(parent)
    frame.pack(fill=tk.X, pady=(5, 0))

    tk.Label(frame, text=label_text).pack(side=tk.LEFT, padx=(0, 5))

    dropdown = ttk.Combobox(frame, textvariable=var, state="readonly", width=30)
    dropdown.pack(side=tk.LEFT, padx=(0, 5))

    # Populate with checkpoint options from checkpoints.txt
    options = TemplateCatalog.get_checkpoint_options()
    dropdown['values'] = options
    if options:
        var.set(options[0])
    else:
        var.set("meichiILIghtMIXV1_meichiILUstMIXV1.safetensors")

    return (frame, var, dropdown)
