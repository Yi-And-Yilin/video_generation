import sys
import importlib.util

spec = importlib.util.spec_from_file_location("test_video_tab", "tests/test_video_tab.py")
mod = importlib.util.module_from_spec(spec)
try:
    spec.loader.exec_module(mod)
    print("Module loaded OK")
    for name in dir(mod):
        if name.startswith("test_"):
            print(f"  Found: {name}")
except Exception as e:
    print(f"Load error: {e}")
    import traceback
    traceback.print_exc()
