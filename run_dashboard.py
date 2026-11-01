"""Convenience launcher: python run_dashboard.py"""
from importlib.util import find_spec
from pathlib import Path
import os
import subprocess
import sys

if sys.version_info < (3, 11):
    raise SystemExit("Install Python 3.11 or newer before launching.")
if find_spec("streamlit") is None:
    raise SystemExit("Install dependencies first: python -m pip install -r requirements.txt")
root = Path(__file__).resolve().parent
os.chdir(root)
raise SystemExit(subprocess.call([sys.executable, "-m", "streamlit", "run", str(root / "app.py"), *sys.argv[1:]]))
