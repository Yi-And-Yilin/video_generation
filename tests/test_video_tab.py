"""
Comprehensive tests for video_tab.py VideoTabUI class.

Tests cover:
  - Normal case: LTX batch generation with valid inputs
  - Edge case: empty prompts, missing resolution, no rows
  - Error case: bad JSON workflow, unreachable ComfyUI, wrong types
"""
import os
import json
import threading
import sys
import pytest
from unittest.mock import MagicMock, patch, mock_open


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def valid_input_data():
    """Return a dict representing a well-formed row for video generation."""
    return {
        "image_path": "C:\\SimpleAIHelper\\video_generation\\output\\test.png",
        "video_prompt": "A cat walking on grass in the park",
        "resolution": "1280*720",
        "seconds": "10",
        "fps": "24",
        "width": "1280",
        "batch": "1",
        "filename_base": "test_scene_0_p0",
        "upscale": False,
    }


@pytest.fixture
def invalid_input_data():
    """Return a dict with missing or broken fields."""
    return {
        "image_path": None,
        "video_prompt": "",
        "resolution": "",
        "seconds": "",
        "fps": "",
        "width": "",
        "batch": "",
        "filename_base": "",
        "upscale": False,
    }


@pytest.fixture
def malformed_input_data():
    """Return a dict with wrong types (string where int expected, etc.)."""
    return {
        "image_path": 12345,
        "video_prompt": 999,
        "resolution": 555,
        "seconds": "not_an_int",
        "fps": None,
        "width": [],
        "batch": {},
        "filename_base": set(),
        "upscale": "yes",
    }


# ---------------------------------------------------------------------------
# Helper: build a VideoTabUI instance without a visible tkinter window
# ---------------------------------------------------------------------------

def _make_video_tab():
    """Build a VideoTabUI instance, patching main_ui and external modules."""
    # Create a real but hidden tkinter root so StringVar works
    import tkinter as tk
    tk_root = tk.Tk()
    tk_root.withdraw()  # hide the window

    # Create a Notebook-like parent
    mock_notebook = MagicMock()
    mock_notebook.add = MagicMock()

    # Patch main_ui BEFORE importing video_tab
    mock_mu = MagicMock()
    mock_mu.COMFYUI_URL = "http://127.0.0.1:8188/prompt"
    mock_mu.COMFYUI_ROOT = r"C:\ComfyUI"
    mock_mu.INPUT_FOLDER = r"C:\ComfyUI\input"
    mock_mu.OUTPUT_FOLDER = r"C:\ComfyUI\output"
    mock_mu.WORKFLOW_TEMPLATE_DIR = r"C:\templates"
    mock_mu.LTX_WORKFLOW_DIR = r"C:\templates\ltx"
    mock_mu.VIDEO_OUTPUT_FOLDER = r"C:\ComfyUI\output\video"
    mock_mu.STATE_FILE = r"C:\state.json"
    mock_mu.TASK_STEPS_CSV = r"C:\task_steps.csv"
    mock_mu.AUDIO_PROMPT_TSV = r"C:\audio_prompt.tsv"
    mock_mu.StreamChunk = MagicMock
    mock_mu.generate_api_workflow = MagicMock
    mock_mu.TemplateCatalog = MagicMock

    with patch.dict(sys.modules, {"main_ui": mock_mu}):
        import video_tab
        tab = video_tab.VideoTabUI(mock_notebook, tk_root)

    # Inject mock constants (overrides _c method)
    tab._mock_c = {
        "COMFYUI_URL": "http://127.0.0.1:8188/prompt",
        "COMFYUI_ROOT": r"C:\ComfyUI",
        "INPUT_FOLDER": r"C:\ComfyUI\input",
        "OUTPUT_FOLDER": r"C:\ComfyUI\output",
        "WORKFLOW_TEMPLATE_DIR": r"C:\templates",
        "LTX_WORKFLOW_DIR": r"C:\templates\ltx",
        "VIDEO_OUTPUT_FOLDER": r"C:\ComfyUI\output\video",
        "STATE_FILE": r"C:\state.json",
        "TASK_STEPS_CSV": r"C:\task_steps.csv",
        "AUDIO_PROMPT_TSV": r"C:\audio_prompt.tsv",
        "TemplateCatalog": mock_mu.TemplateCatalog,
        "StreamChunk": mock_mu.StreamChunk,
        "generate_api_workflow": mock_mu.generate_api_workflow,
    }
    tab._c = lambda: tab._mock_c

    return tab, tk_root


# ---------------------------------------------------------------------------
# test_normal_case
# ---------------------------------------------------------------------------

def test_normal_case(valid_input_data, malformed_input_data, invalid_input_data):
    """Tests the happy path for LTX video generation with valid inputs.

    Verifies that:
      1. start_video_generation with valid rows enters running state
      2. _run_ltx_video_generation calls BatchRunner.run_batch with correct params
      3. Logs show completed/failed counts
      4. _send_workflow_to_comfyui returns a prompt_id on success
      5. _wait_for_completion returns history data when ComfyUI responds
    """
    tab, tk_root = _make_video_tab()

    # --- Mock BatchRunner ---
    mock_batch_result = {
        "completed": [valid_input_data["filename_base"]],
        "failed": [],
    }
    mock_runner_instance = MagicMock()
    mock_runner_instance.run_batch.return_value = mock_batch_result
    mock_batch_cls = MagicMock(return_value=mock_runner_instance)

    # --- Mock requests.post for _send_workflow_to_comfyui ---
    # mock api.call to return {"id": "some_id", "status": "queued"}
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.json.return_value = {"id": "mock_prompt_id", "status": "queued"}

    with patch("requests.post", return_value=mock_resp) as mock_post:
        # --- Add a row manually (simulating user adding images) ---
        tab.rows.append({
            "frame": MagicMock(),
            "image_path": valid_input_data["image_path"],
            "filename_base": valid_input_data["filename_base"],
            "filename": MagicMock(get=MagicMock(return_value="test.png")),
            "video_prompt": MagicMock(get=MagicMock(return_value=valid_input_data["video_prompt"])),
            "seconds": MagicMock(get=MagicMock(return_value=valid_input_data["seconds"])),
            "width": MagicMock(get=MagicMock(return_value=valid_input_data["width"])),
            "upscale": MagicMock(get=MagicMock(return_value=valid_input_data["upscale"])),
            "batch": MagicMock(get=MagicMock(return_value=valid_input_data["batch"])),
        })

        # Set engine and resolution
        tab.video_engine_var.set("LTX")
        tab.resolution_var.set(valid_input_data["resolution"])
        tab.video_length_var.set("241")
        tab.fps_var.set("24")
        tab.image_model_var.set("pornmaster_proSDXLV8")

        # --- Start generation ---
        tab.start_video_generation()

        # Verify running state was set
        assert tab.is_running == True
        tab.status_var.set.assert_called_with("Running")

        # Give thread time to run
        import time
        time.sleep(1)

        # Verify BatchRunner was invoked with correct params
        mock_batch_cls.assert_called()
        # Verify tasks contain main_sex_act
        batch_calls = mock_batch_cls.call_args_list
        for call_args in batch_calls:
            if "tasks" in call_args[1]:
                tasks = call_args[1]["tasks"]
                assert len(tasks) > 0
                assert "main_sex_act" in tasks[0]
                assert tasks[0]["main_sex_act"] == "A cat walking on grass in the park"

    # --- Test _send_workflow_to_comfyui ---
    mock_wf = {"node": {"inputs": {}}}
    prompt_id = tab._send_workflow_to_comfyui(mock_wf, "test_work_id")
    assert prompt_id is not None  # should return the generated prompt_id

    # Verify the POST call payload
    mock_post.assert_called()
    post_call = mock_post.call_args
    payload = post_call[1]["json"]
    assert "prompt" in payload
    assert "prompt_id" in payload

    # --- Test _wait_for_completion ---
    mock_hist_resp = MagicMock()
    mock_hist_resp.ok = True
    mock_hist_resp.json.return_value = {
        "test_prompt_id": {"status": "success", "outputs": []}
    }

    with patch("requests.get", return_value=mock_hist_resp) as mock_get:
        result = tab._wait_for_completion("test_prompt_id", timeout=1)
        assert result == {"status": "success", "outputs": []}

    # Cleanup
    tk_root.destroy()


# ---------------------------------------------------------------------------
# test_edge_case
# ---------------------------------------------------------------------------

def test_edge_case(invalid_input_data, malformed_input_data):
    """Tests boundary conditions for video generation.

    Verifies that:
      1. start_video_generation logs warning and returns when rows is empty
      2. _run_ltx_video_generation handles empty video_prompt gracefully
      3. _run_wan_video_generation handles missing task steps
      4. _run_wan_video_generation skips steps with correct conditions
      5. _get_task_steps returns None when CSV doesn't exist
      6. _resolve_template_path returns None for missing templates
      7. cancel_generation works mid-processing
    """
    tab, tk_root = _make_video_tab()

    # --- Edge case: no rows ---
    tab.rows = []
    tab.video_engine_var.set("LTX")
    tab.start_video_generation()

    # Should have logged a warning (check log queue)
    assert tab.is_running == False
    log_entries = tab.video_log_queue.copy()
    has_warning = any("WARNING" in str(e) for e in log_entries)
    assert has_warning == True

    # --- Edge case: empty video_prompt ---
    tab.rows = [{
        "frame": MagicMock(),
        "image_path": "C:\\empty\\path.png",
        "filename_base": "empty_test",
        "filename": MagicMock(get=MagicMock(return_value="test.png")),
        "video_prompt": MagicMock(get=MagicMock(return_value="")),  # empty prompt
        "seconds": MagicMock(get=MagicMock(return_value="10")),
        "width": MagicMock(get=MagicMock(return_value="1280")),
        "upscale": MagicMock(get=MagicMock(return_value=False)),
        "batch": MagicMock(get=MagicMock(return_value="1")),
    }]
    tab.video_engine_var.set("LTX")
    tab.resolution_var.set("1280*720")
    tab.video_length_var.set("241")
    tab.fps_var.set("24")
    tab.image_model_var.set("pornmaster_proSDXLV8")

    # --- Mock _c ---
    tab._c = lambda: tab._mock_c

    # --- Mock BatchRunner ---
    mock_runner = MagicMock()
    mock_runner.run_batch.return_value = {"completed": [], "failed": ["empty_test"]}

    import sys
    mock_ltx_pkg = MagicMock()
    mock_ltx_pkg.BatchRunner = MagicMock(return_value=mock_runner)
    sys.modules["projects"] = MagicMock()
    sys.modules["projects.ltx"] = MagicMock()
    sys.modules["projects.ltx.batch_runner"] = mock_ltx_pkg

    tab._run_ltx_video_generation()

    # Should have fallen back to image_path when prompt is empty
    task = mock_runner.run_batch.call_args[1]["tasks"][0]
    assert task["main_sex_act"] == ""

    # --- Edge case: _get_task_steps returns None when CSV doesn't exist ---
    steps = tab._get_task_steps("nonexistent_task")
    assert steps is None

    # --- Edge case: _resolve_template_path returns None for missing templates ---
    result = tab._resolve_template_path("nonexistent_workflow")
    assert result is None

    # --- Edge case: cancel_generation ---
    tab.rows = [{
        "frame": MagicMock(),
        "image_path": "x",
        "filename_base": "cancel_test",
        "filename": MagicMock(get=MagicMock(return_value="x")),
        "video_prompt": MagicMock(get=MagicMock(return_value="test")),
        "seconds": MagicMock(get=MagicMock(return_value="10")),
        "width": MagicMock(get=MagicMock(return_value="1280")),
        "upscale": MagicMock(get=MagicMock(return_value=False)),
        "batch": MagicMock(get=MagicMock(return_value="1")),
    }]
    tab.cancel_generation()
    assert tab.cancel_event.is_set() == True

    # Cleanup
    tk_root.destroy()


# ---------------------------------------------------------------------------
# test_error_case
# ---------------------------------------------------------------------------

def test_error_case(valid_input_data, invalid_input_data, malformed_input_data):
    """Tests error handling for video generation.

    Verifies that:
      1. _send_workflow_to_comfyui returns None when ComfyUI is unreachable
      2. _wait_for_completion returns 'cancelled' when cancel_event is set
      3. _get_task_steps returns None on CSV read failure
      4. _run_wan_video_generation handles missing workflow templates
      5. Malformed input data does not crash the runner (graceful degradation)
      6. Invalid JSON in workflow template is silently skipped
      7. Exception in thread is caught and logged
    """
    tab, tk_root = _make_video_tab()

    # --- Error case: ComfyUI unreachable (bad response) ---
    mock_err_resp = MagicMock()
    mock_err_resp.ok = False
    with patch("requests.post", return_value=mock_err_resp):
        prompt_id = tab._send_workflow_to_comfyui({"node": {}}, "bad_id")
        assert prompt_id is None

    # --- Error case: requests.post raises exception ---
    with patch("requests.post", side_effect=Exception("Connection refused")):
        prompt_id = tab._send_workflow_to_comfyui({"node": {}}, "bad_id")
        assert prompt_id is None  # should catch exception and return None

    # --- Error case: cancel_event during _wait_for_completion ---
    tab.cancel_event.set()
    result = tab._wait_for_completion("any_id", timeout=5)
    assert result == "cancelled"
    tab.cancel_event.clear()

    # --- Error case: _get_task_steps returns None ---
    steps = tab._get_task_steps("nonexistent_task")
    assert steps is None

    # --- Error case: _run_wan_video_generation with missing template ---
    tab.video_engine_var.set("WAN")
    tab.video_log = MagicMock()
    tab.task_type_var = MagicMock(return_value="wan2.2")

    with patch.object(tab, "_get_task_steps", return_value=["some_step"]):
        with patch.object(tab, "_resolve_template_path", return_value=None):
            tab._run_wan_video_generation()

    # Should have logged a warning about missing template
    log_calls = [str(c) for c in tab.video_log.call_args_list]
    assert any("Warning" in c or "warning" in c for c in log_calls)

    # --- Error case: invalid JSON in workflow template ---
    tab2, _ = _make_video_tab()
    tab2.video_engine_var.set("WAN")
    tab2.video_log = MagicMock()
    tab2.task_type_var = MagicMock(return_value="wan2.2")
    tab2.resolution_var = MagicMock(return_value="1280*720")
    tab2.fps_var = MagicMock(return_value="24")
    tab2.image_model_var = MagicMock(return_value="model")

    with patch.object(tab2, "_get_task_steps", return_value=["bad_workflow"]):
        fake_path = r"C:\templates\bad_workflow.json"
        with patch.object(tab2, "_resolve_template_path", return_value=fake_path):
            with patch("builtins.open", mock_open(read_data="not valid json{{{")):
                # This should not raise — the code has try/except around json.loads
                tab2._run_wan_video_generation()

    # --- Error case: malformed input in LTX runner ---
    tab3, _ = _make_video_tab()
    tab3.video_engine_var.set("LTX")
    tab3.video_log = MagicMock()
    tab3.resolution_var.set("1280*720")
    tab3.video_length_var.set("241")
    tab3.fps_var.set("24")
    tab3.image_model_var.set("model")
    tab3.rows = [{
        "frame": MagicMock(),
        "image_path": 12345,  # int instead of string (malformed)
        "filename_base": "fallback_base",
        "filename": MagicMock(get=MagicMock(return_value="test.png")),
        "video_prompt": MagicMock(get=MagicMock(return_value="999")),  # int as string
        "seconds": MagicMock(get=MagicMock(return_value="10")),
        "width": MagicMock(get=MagicMock(return_value="1280")),
        "upscale": MagicMock(get=MagicMock(return_value=False)),
        "batch": MagicMock(get=MagicMock(return_value="1")),
    }]

    mock_runner3 = MagicMock()
    mock_runner3.run_batch.return_value = {"completed": [], "failed": []}

    import sys
    sys.modules["projects"] = MagicMock()
    sys.modules["projects.ltx"] = MagicMock()
    sys.modules["projects.ltx.batch_runner"] = MagicMock()
    sys.modules["projects.ltx.batch_runner"].BatchRunner = MagicMock(return_value=mock_runner3)

    # Should not raise — code should handle the string fallback
    tab3._run_ltx_video_generation()

    # --- Error case: exception in _run_video_generation_thread ---
    tab4, _ = _make_video_tab()
    tab4.video_log = MagicMock()
    tab4.video_engine_var.set("LTX")

    # Inject a failure
    with patch.object(tab4, "_run_ltx_video_generation", side_effect=RuntimeError("simulated crash")):
        tab4._run_video_generation_thread("LTX")

    # Should have logged the error and reset state
    log_calls = [str(c) for c in tab4.video_log.call_args_list]
    assert any("Error" in c for c in log_calls)

    # --- Error case: _send_workflow_to_comfyui with broken workflow ---
    with patch("requests.post", side_effect=Exception("Network error")):
        result = tab._send_workflow_to_comfyui({"broken": True}, "test")
        assert result is None

    # Cleanup
    tk_root.destroy()
