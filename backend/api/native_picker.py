"""Native GUI file and folder picker dialogs for Sovereign Workbench."""

import subprocess
import sys
from pathlib import Path


def pick_folder_gui(title: str = "Select Folder to Add to Sovereign Workbench") -> str | None:
    """Open native OS directory picker dialog and return selected absolute path or None."""
    py_code = """
import tkinter as tk
from tkinter import filedialog
root = tk.Tk()
root.withdraw()
try:
    root.wm_attributes('-topmost', 1)
except Exception:
    pass
path = filedialog.askdirectory(title='Select Folder to Add to Sovereign Workbench')
root.destroy()
if path:
    print(path.strip())
"""
    try:
        proc = subprocess.run(
            [sys.executable, "-c", py_code],
            capture_output=True,
            text=True,
            timeout=180,
        )
        val = proc.stdout.strip()
        if val and Path(val).exists():
            return str(Path(val).resolve())
        return None
    except Exception:
        return None


def pick_files_gui(title: str = "Select Files to Add to Sovereign Workbench") -> list[str]:
    """Open native OS file picker dialog and return list of selected paths."""
    py_code = """
import tkinter as tk
from tkinter import filedialog
root = tk.Tk()
root.withdraw()
try:
    root.wm_attributes('-topmost', 1)
except Exception:
    pass
filetypes = [
    ("All Supported Documents", "*.pdf *.docx *.xlsx *.xls *.png *.jpg *.jpeg *.txt *.json *.csv *.md *.yaml *.yml *.py *.sql"),
    ("PDF Documents", "*.pdf"),
    ("Office Documents", "*.docx *.xlsx *.xls *.csv"),
    ("Images & Scans", "*.png *.jpg *.jpeg"),
    ("Text & Code", "*.txt *.json *.md *.yaml *.yml *.py *.sql"),
    ("All Files", "*.*"),
]
paths = filedialog.askopenfilenames(title='Select Files to Add to Sovereign Workbench', filetypes=filetypes)
root.destroy()
if paths:
    for p in paths:
        print(p.strip())
"""
    try:
        proc = subprocess.run(
            [sys.executable, "-c", py_code],
            capture_output=True,
            text=True,
            timeout=180,
        )
        lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
        valid = [str(Path(l).resolve()) for l in lines if Path(l).exists()]
        return valid
    except Exception:
        return []


if __name__ == "__main__":
    print("Testing native picker module imports successfully.")
