"""Community Cloud entry point: never collect shared responses in local SQLite."""
import os
from pathlib import Path
import runpy

os.environ["HINT_CLOUD_DEPLOYMENT"] = "1"
runpy.run_path(str(Path(__file__).with_name("app.py")), run_name="__main__")
