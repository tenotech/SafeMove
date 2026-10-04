"""SafeMove: move photos/videos from an iPhone to this PC, verified, oldest first."""

import os
import sys
from pathlib import Path

__version__ = "1.2.0"

# Portable/installed build: Tcl/Tk live in <python>\tcl. Shortcuts can't set environment variables,
# so point tkinter at them here, before anything imports tkinter.
_tcl = Path(sys.base_prefix) / "tcl"
if (_tcl / "tcl8.6").is_dir():
    os.environ.setdefault("TCL_LIBRARY", str(_tcl / "tcl8.6"))
    os.environ.setdefault("TK_LIBRARY", str(_tcl / "tk8.6"))
