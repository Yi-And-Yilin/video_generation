"""
WAN project module — unified LoRA management for video generation.

Exports the core LoRA manager for use by workflow generators and UI code.
"""

from wan_lora_manager import (
    load_lora_lookup,
    resolve_lora_params,
    apply_lora_placeholders,
    apply_dynamic_lora_chaining,
    generate_workflow_unified,
    DEFAULT_LORA_NAME,
    DEFAULT_LORA_STRENGTH,
)

__all__ = [
    "load_lora_lookup",
    "resolve_lora_params",
    "apply_lora_placeholders",
    "apply_dynamic_lora_chaining",
    "generate_workflow_unified",
    "DEFAULT_LORA_NAME",
    "DEFAULT_LORA_STRENGTH",
]
