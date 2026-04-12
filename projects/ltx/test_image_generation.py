"""
Unit tests for image generation module (nsfw_ui.py)
Tests for:
- LoRA lookup CSV parsing
- Workflow JSON generation
- ComfyUI API request handling
- Error scenarios
"""

import json
import os
import sys
import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path

import requests

# Add parent and grandparent directories to path
sys.path.insert(0, str(Path(__file__).parent.parent))  # sfdw directory
sys.path.insert(0, str(Path(__file__).parent.parent.parent))  # sfw directory

from workflow_generator import load_lora_lookup, generate_api_workflow


class TestLoRALookup(unittest.TestCase):
    """Test LoRA lookup CSV parsing."""

    def setUp(self):
        self.csv_path = "image_lora_lookup.csv"

    def test_load_lora_lookup(self):
        """Test loading LoRA lookup from CSV."""
        result = load_lora_lookup(
            csv_path=self.csv_path,
            filter_type="pornmaster_proSDXLV8",
            workflow_name="pornmaster_proSDXLV8"
        )
        self.assertIsNotNone(result)
        self.assertIsInstance(result, dict)
        self.assertIn("fingering", result)
        self.assertIn("mating_press", result)
        # Note: doggy_style is not in the CSV file

    def test_load_lora_lookup_empty_result(self):
        """Test loading LoRA lookup with non-existent workflow."""
        result = load_lora_lookup(
            csv_path=self.csv_path,
            filter_type="non_existent_workflow",
            workflow_name="non_existent_workflow"
        )
        self.assertEqual(result, {})


class TestWorkflowGeneration(unittest.TestCase):
    """Test workflow JSON generation."""

    @patch("requests.post")
    def test_send_workflow_success(self, mock_post):
        """Test successful workflow submission to ComfyUI."""
        from nsfw_ui import COMFYUI_URL, NSFWApp

        # Setup mock response
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.text = '{"prompt_id": "test-123"}'
        mock_post.return_value = mock_response

        # Create mock app
        mock_app = MagicMock()
        mock_app._image_log = MagicMock()

        # Test workflow dict (as returned by generate_api_workflow)
        test_workflow = {
            "3": [{"class_type": "LoadImage"}, {"class_type": "VAEDecode"}],
            "prompt_0": [{"class_type": "CLIPTextEncode"}],
            "4": [{"class_type": "CheckpointLoaderSimple"}],
        }

        # Convert to JSON string
        workflow_str = json.dumps(test_workflow)

        # Call send_workflow_to_comfyui
        prompt_id = NSFWApp.send_workflow_to_comfyui(workflow_str, "test-work-id")

        # Verify response
        self.assertIsNotNone(prompt_id)
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        self.assertEqual(call_args.kwargs["timeout"], 60)

    @patch("requests.post")
    def test_send_workflow_timeout(self, mock_post):
        """Test workflow timeout error handling."""
        mock_post.side_effect = requests.exceptions.Timeout()

        from nsfw_ui import NSFWApp

        test_workflow = {"3": [], "prompt_0": []}
        workflow_str = json.dumps(test_workflow)

        prompt_id = NSFWApp.send_workflow_to_comfyui(workflow_str, "test-work-id")

        self.assertIsNone(prompt_id)

    @patch("requests.post")
    def test_send_workflow_connection_error(self, mock_post):
        """Test connection error handling."""
        mock_post.side_effect = requests.exceptions.ConnectionError()

        from nsfw_ui import NSFWApp

        test_workflow = {"3": [], "prompt_0": []}
        workflow_str = json.dumps(test_workflow)

        prompt_id = NSFWApp.send_workflow_to_comfyui(workflow_str, "test-work-id")

        self.assertIsNone(prompt_id)

    @patch("requests.post")
    def test_send_workflow_failed_response(self, mock_post):
        """Test failed workflow submission (non-2xx response)."""
        mock_response = MagicMock()
        mock_response.ok = False
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_post.return_value = mock_response

        from nsfw_ui import NSFWApp

        test_workflow = {"3": [], "prompt_0": []}
        workflow_str = json.dumps(test_workflow)

        prompt_id = NSFWApp.send_workflow_to_comfyui(workflow_str, "test-work-id")

        self.assertIsNone(prompt_id)


class TestImageLoraLookup(unittest.TestCase):
    """Test image_lora_lookup.csv parsing (specific CSV format)."""

    def setUp(self):
        self.csv_path = os.path.join(os.path.dirname(__file__), "..", "..", "projects", "ltx", "image_lora_lookup.csv")

    def test_load_image_lora_lookup(self):
        """Test loading the image_lora_lookup.csv file."""
        from workflow_generator import load_lora_lookup

        result = load_lora_lookup(
            csv_path=self.csv_path,
            filter_type="pornmaster_proSDXLV8",
            workflow_name="pornmaster_proSDXLV8"
        )

        self.assertIsNotNone(result)
        self.assertIsInstance(result, dict)

        # Check for expected entries
        self.assertIn("mating_press", result)
        self.assertIn("fingering", result)
        # Note: doggy_style is not in the CSV file

    def test_lora_entry_structure(self):
        """Test that LoRA entries have correct structure."""
        from workflow_generator import load_lora_lookup

        result = load_lora_lookup(
            csv_path=self.csv_path,
            filter_type="pornmaster_proSDXLV8",
            workflow_name="pornmaster_proSDXLV8"
        )

        for tag, loras in result.items():
            for lora in loras:
                self.assertIn("name", lora)
                self.assertIn("strength", lora)


class TestWorkflowJsonSerialization(unittest.TestCase):
    """Test JSON serialization of workflow dicts."""

    @patch("requests.post")
    def test_dict_to_json_conversion(self, mock_post):
        """Test that workflow dict is properly converted to JSON string."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.text = '{"prompt_id": "test"}'
        mock_post.return_value = mock_response

        from nsfw_ui import NSFWApp

        # workflow is a dict returned from generate_api_workflow
        workflow_dict = {
            "3": [{"class_type": "LoadImage"}],
            "64": [{"class_type": "VAEDecode"}]
        }

        # This is what the fixed code does
        workflow_str = json.dumps(workflow_dict)
        prompt_id = NSFWApp.send_workflow_to_comfyui(workflow_str, "test-id")

        self.assertIsNotNone(prompt_id)


if __name__ == "__main__":
    unittest.main()
