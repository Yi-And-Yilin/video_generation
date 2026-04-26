"""
Latent File Utilities for ComfyUI workflows.

Helper functions for managing latent files between ComfyUI output and input folders.

Filename Patterns:
- Image: {work_id}.png
- Video Latent: video_{work_id}*.latent
- Audio Latent: audio_{work_id}*.latent
- Conditioning: positive_conditioning_{work_id}.pt, negative_conditioning_{work_id}.pt
- Video: {work_id}.mp4
"""

import os
import glob
import shutil
import logging

# Configure logging
logger = logging.getLogger(__name__)

# Default paths - can be overridden via environment variables
COMFYUI_ROOT = os.environ.get("COMFYUI_ROOT", r"D:\ComfyUI_windows_portable\ComfyUI")
OUTPUT_FOLDER = os.environ.get("OUTPUT_FOLDER", os.path.join(COMFYUI_ROOT, "output"))
INPUT_FOLDER = os.environ.get("INPUT_FOLDER", os.path.join(COMFYUI_ROOT, "input"))
LATENTS_FOLDER = os.path.join(OUTPUT_FOLDER, "latents")
CONDITIONINGS_FOLDER = os.path.join(OUTPUT_FOLDER, "conditionings")


def delete_image_files(work_id: str,
                       output_folder: str = None,
                       log_func: callable = None) -> dict:
    """
    Delete image file from output folder after video generation step.
    
    Filename pattern: {work_id}.png
    
    Args:
        work_id: The work ID of the image file
        output_folder: Path to output folder (default: OUTPUT_FOLDER)
        log_func: Optional logging function
    
    Returns:
        dict: Summary with 'deleted' (list of deleted files) and 'errors' (list of errors)
    """
    def log(msg):
        if log_func:
            log_func(msg)
        else:
            logger.info(msg)
    
    if output_folder is None:
        output_folder = OUTPUT_FOLDER
    
    result = {
        'deleted': [],
        'errors': []
    }
    
    if not os.path.exists(output_folder):
        log(f"Warning: Output folder not found: {output_folder}")
        return result
    
    # Search for image file: {work_id}.png and variants
    patterns = [
        os.path.join(output_folder, f"{work_id}.png"),
        os.path.join(output_folder, f"{work_id}_*.png"),
    ]
    
    files_to_delete = set()
    for pattern in patterns:
        files_to_delete.update(glob.glob(pattern))
    
    # Filter out directories
    files_to_delete = [f for f in files_to_delete if os.path.isfile(f)]
    
    if not files_to_delete:
        log(f"No image files found to delete for work_id '{work_id}'")
        return result
    
    log(f"Found {len(files_to_delete)} image file(s) to delete for work_id '{work_id}'")
    
    for file_path in files_to_delete:
        filename = os.path.basename(file_path)
        try:
            os.remove(file_path)
            log(f"Deleted image file: {filename}")
            result['deleted'].append(filename)
        except Exception as e:
            error_msg = f"Error deleting {filename}: {e}"
            log(error_msg)
            result['errors'].append({'file': filename, 'error': str(e)})
    
    return result


def delete_consumed_latents(work_id: str,
                            latents_folder: str = None,
                            input_folder: str = None,
                            log_func: callable = None) -> dict:
    """
    Delete latent files that have been consumed by the final workflow step.
    
    Filename patterns:
    - video_{work_id}*.latent
    - audio_{work_id}*.latent
    
    Args:
        work_id: The work ID of the latent files
        latents_folder: Path to latents folder (default: LATENTS_FOLDER)
        input_folder: Path to input folder (default: INPUT_FOLDER)
        log_func: Optional logging function
    
    Returns:
        dict: Summary with 'deleted' (list of deleted files) and 'errors' (list of errors)
    """
    def log(msg):
        if log_func:
            log_func(msg)
        else:
            logger.info(msg)
    
    if latents_folder is None:
        latents_folder = LATENTS_FOLDER
    if input_folder is None:
        input_folder = INPUT_FOLDER
    
    result = {
        'deleted': [],
        'errors': []
    }
    
    # Search patterns for video and audio latent files
    patterns = []
    
    # Search in latents folder
    if os.path.exists(latents_folder):
        patterns.extend([
            os.path.join(latents_folder, f"video_{work_id}*.latent"),
            os.path.join(latents_folder, f"audio_{work_id}*.latent"),
        ])
    
    # Search in input folder (if latents were moved there)
    if os.path.exists(input_folder):
        patterns.extend([
            os.path.join(input_folder, f"video_{work_id}*.latent"),
            os.path.join(input_folder, f"audio_{work_id}*.latent"),
        ])
    
    files_to_delete = set()
    for pattern in patterns:
        files_to_delete.update(glob.glob(pattern))
    
    # Filter out directories
    files_to_delete = [f for f in files_to_delete if os.path.isfile(f)]
    
    if not files_to_delete:
        log(f"No latent files found to delete for work_id '{work_id}'")
        return result
    
    log(f"Found {len(files_to_delete)} latent file(s) to delete for work_id '{work_id}'")
    
    for file_path in files_to_delete:
        filename = os.path.basename(file_path)
        try:
            os.remove(file_path)
            log(f"Deleted latent file: {filename}")
            result['deleted'].append(filename)
        except Exception as e:
            error_msg = f"Error deleting {filename}: {e}"
            log(error_msg)
            result['errors'].append({'file': filename, 'error': str(e)})
    
    return result


def delete_conditioning_files(work_id: str,
                              conditionings_folder: str = None,
                              log_func: callable = None) -> dict:
    """
    Delete conditioning files for a work ID.
    
    Filename patterns:
    - positive_conditioning_{work_id}.pt
    - negative_conditioning_{work_id}.pt
    
    Args:
        work_id: The work ID of the conditioning files
        conditionings_folder: Path to conditionings folder (default: CONDITIONINGS_FOLDER)
        log_func: Optional logging function
    
    Returns:
        dict: Summary with 'deleted' (list of deleted files) and 'errors' (list of errors)
    """
    def log(msg):
        if log_func:
            log_func(msg)
        else:
            logger.info(msg)
    
    if conditionings_folder is None:
        conditionings_folder = CONDITIONINGS_FOLDER
    
    result = {
        'deleted': [],
        'errors': []
    }
    
    if not os.path.exists(conditionings_folder):
        log(f"Warning: Conditionings folder not found: {conditionings_folder}")
        return result
    
    # Search for conditioning files
    patterns = [
        os.path.join(conditionings_folder, f"positive_conditioning_{work_id}*.pt"),
        os.path.join(conditionings_folder, f"negative_conditioning_{work_id}*.pt"),
        os.path.join(conditionings_folder, f"pos_{work_id}*.pt"),
        os.path.join(conditionings_folder, f"neg_{work_id}*.pt"),
    ]
    
    files_to_delete = set()
    for pattern in patterns:
        files_to_delete.update(glob.glob(pattern))
    
    # Filter out directories
    files_to_delete = [f for f in files_to_delete if os.path.isfile(f)]
    
    if not files_to_delete:
        log(f"No conditioning files found to delete for work_id '{work_id}'")
        return result
    
    log(f"Found {len(files_to_delete)} conditioning file(s) to delete for work_id '{work_id}'")
    
    for file_path in files_to_delete:
        filename = os.path.basename(file_path)
        try:
            os.remove(file_path)
            log(f"Deleted conditioning file: {filename}")
            result['deleted'].append(filename)
        except Exception as e:
            error_msg = f"Error deleting {filename}: {e}"
            log(error_msg)
            result['errors'].append({'file': filename, 'error': str(e)})
    
    return result


def get_latent_files(work_id: str = None, 
                     search_folders: list = None,
                     latents_folder: str = None,
                     input_folder: str = None) -> list:
    """
    Get a list of latent files, optionally filtered by work_id.
    
    Args:
        work_id: Optional work ID to filter by
        search_folders: List of folders to search (default: [latents, input])
        latents_folder: Path to latents folder
        input_folder: Path to input folder
    
    Returns:
        list: List of dicts with 'path', 'filename', 'folder' keys
    """
    if latents_folder is None:
        latents_folder = LATENTS_FOLDER
    if input_folder is None:
        input_folder = INPUT_FOLDER
    
    if search_folders is None:
        search_folders = [latents_folder, input_folder]
    
    results = []
    
    for folder in search_folders:
        if not os.path.exists(folder):
            continue
        
        for filename in os.listdir(folder):
            file_path = os.path.join(folder, filename)
            
            # Check if it's a file with .latent extension
            if not os.path.isfile(file_path):
                continue
            
            if not filename.endswith('.latent'):
                continue
            
            # Filter by work_id if provided
            if work_id and work_id not in filename:
                continue
            
            results.append({
                'path': file_path,
                'filename': filename,
                'folder': folder
            })
    
    return results


# Legacy function names for backward compatibility
def move_latents_to_input(work_id: str, 
                          latent_output_folder: str = None, 
                          input_folder: str = None,
                          log_func: callable = None) -> dict:
    """
    Legacy function - no longer needed for LTX workflow.
    Latent files are saved directly to the correct location.
    """
    def log(msg):
        if log_func:
            log_func(msg)
        else:
            logger.info(msg)
    
    log("move_latents_to_input is deprecated - latents are saved to correct location directly")
    return {'moved': [], 'errors': []}


# Example usage
if __name__ == "__main__":
    print("Testing latent_utils...")
    
    # Test with a sample work_id
    test_work_id = "test123"
    
    # Get latent files (will be empty if none exist)
    files = get_latent_files()
    print(f"Found {len(files)} latent files total")
    
    files_with_id = get_latent_files(test_work_id)
    print(f"Found {len(files_with_id)} latent files with work_id '{test_work_id}'")
