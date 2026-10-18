"""Independent receipt/error/restart smoke, on an owned ephemeral server."""
from pathlib import Path
import runpy
runpy.run_path(str(Path(__file__).with_name('stability_browser.py')),run_name='__main__')
