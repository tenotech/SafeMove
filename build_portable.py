"""Builds dist\\SafeMove-portable.zip: runs on any Windows 10/11 x64 laptop, no install.

Contents: the official Python *embeddable* package (signed by the PSF) + tkinter copied from this
machine's Python (same version, also signed) + comtypes + our code. No unsigned .exe/.dll, so
Smart App Control does not block it.

    python build_portable.py
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

HERE = Path(__file__).parent
BUILD = HERE / "build" / "SafeMove"
DIST = HERE / "dist"
VERSION = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
TAG = f"{sys.version_info.major}{sys.version_info.minor}"  # e.g. 311
EMBED_URL = f"https://www.python.org/ftp/python/{VERSION}/python-{VERSION}-embed-amd64.zip"
CACHE = HERE / "build" / f"python-{VERSION}-embed-amd64.zip"

INSTALLER = r"""@echo off
rem Installs SafeMove for this Windows user: Desktop + Start menu shortcuts, entry in Settings > Apps.
cd /d "%~dp0"
start "" "%~dp0python\pythonw.exe" -m safemove.install
"""

LAUNCHER = r"""@echo off
rem Runs SafeMove straight from this folder, without installing.
cd /d "%~dp0"
start "" "%~dp0python\pythonw.exe" -m safemove.app
"""

REPORT_LAUNCHER = r"""@echo off
rem Writes SafeMove-device-report.txt on the Desktop (read-only, no file names). Attach it to GitHub issues.
cd /d "%~dp0"
"%~dp0python\python.exe" -m safemove.report
pause
"""

CONSOLE_LAUNCHER = r"""@echo off
rem Same app, with a console window that shows errors (for troubleshooting).
cd /d "%~dp0"
"%~dp0python\python.exe" -m safemove.app
pause
"""

README = """SafeMove (portable)
=======================

Moves photos and videos from an iPhone (USB cable) to this PC, oldest first, in chunks.
Each file is deleted from the iPhone only after its copy on the PC has been verified.

Install
-------
1. If you downloaded the zip: right-click it > Properties > tick "Unblock" > OK, before unzipping.
2. Unzip it anywhere and double-click "Install.cmd".
   It installs for your Windows user only (no admin rights): Desktop + Start menu shortcuts,
   and an entry in Settings > Apps (that is also where you uninstall it).
   To update later: run Install.cmd from the newer zip. Photos, logs and settings are kept.
3. Plug in the iPhone, unlock it, tap "Trust". It must show up in Explorer under "This PC".
4. Start "SafeMove" from the Desktop or the Start menu.

No install wanted? Double-click "SafeMove.cmd" to run it straight from the unzipped folder.

Before each run
---------------
- iPhone unlocked, Settings > Display & Brightness > Auto-Lock > Never
- iPhone setting: Settings > Apps > Photos > Transfer to Mac or PC > Keep Originals
- Laptop plugged into power

Good to know
------------
- Start with "Test mode" checked: it copies and verifies but never deletes.
- Edited photos/videos are copied but stay on the iPhone (the iPhone does not allow deleting them
  over USB). They are listed in <destination>\\logs\\edited-items-to-delete.txt.
- Every moved file is recorded in <destination>\\logs\\manifest.csv.
- If something goes wrong, use "SafeMove (console).cmd": it shows error messages.
- Full guide: USER_GUIDE.md (open it with Notepad or any Markdown viewer).
"""


def step(text: str) -> None:
    print(f"\n== {text}")


def main() -> None:
    if BUILD.exists():
        shutil.rmtree(BUILD)
    py = BUILD / "python"
    py.mkdir(parents=True)

    step(f"Python {VERSION} embeddable package")
    if not CACHE.exists():
        print(f"downloading {EMBED_URL}")
        urllib.request.urlretrieve(EMBED_URL, CACHE)
    with zipfile.ZipFile(CACHE) as z:
        z.extractall(py)

    step("tkinter (from this machine's Python, same version)")
    base = Path(sys.base_prefix)
    for name in ("_tkinter.pyd", "tcl86t.dll", "tk86t.dll", "zlib1.dll"):
        src = base / "DLLs" / name
        if src.exists():
            shutil.copy2(src, py / name)
            print(f"  {name}")
    shutil.copytree(base / "Lib" / "tkinter", py / "Lib" / "tkinter",
                    ignore=shutil.ignore_patterns("__pycache__", "test"))
    # Leave out unused Tcl extras; they contain the only unsigned binaries (dde, registry, tix, nmake helper).
    shutil.copytree(base / "tcl", py / "tcl",
                    ignore=shutil.ignore_patterns("*demos*", "dde*", "reg1*", "tix*", "nmake"))

    step("comtypes")
    import comtypes
    src = Path(comtypes.__file__).parent
    shutil.copytree(src, BUILD / "lib" / "comtypes",
                    ignore=shutil.ignore_patterns("__pycache__", "test", "gen"))
    (BUILD / "lib" / "comtypes" / "gen").mkdir()
    (BUILD / "lib" / "comtypes" / "gen" / "__init__.py").write_text("# generated wrappers go here\n")

    step("safemove")
    shutil.copytree(HERE / "safemove", BUILD / "safemove", ignore=shutil.ignore_patterns("__pycache__"))

    step("python path, launchers, readme")
    (py / f"python{TAG}._pth").write_text(
        f"python{TAG}.zip\n.\nLib\n..\\lib\n..\n", encoding="ascii")
    (BUILD / "Install.cmd").write_text(INSTALLER.replace("\n", "\r\n"), encoding="ascii")
    (BUILD / "Device report.cmd").write_text(REPORT_LAUNCHER.replace("\n", "\r\n"), encoding="ascii")
    shutil.copy2(HERE / "LICENSE", BUILD / "LICENSE.txt")
    (BUILD / "SafeMove.cmd").write_text(LAUNCHER.replace("\n", "\r\n"), encoding="ascii")
    (BUILD / "SafeMove (console).cmd").write_text(CONSOLE_LAUNCHER.replace("\n", "\r\n"), encoding="ascii")
    (BUILD / "README.txt").write_text(README, encoding="utf-8")
    shutil.copy2(HERE / "docs" / "USER_GUIDE.md", BUILD / "USER_GUIDE.md")

    step("self-test with the portable Python")
    import os
    env = {k: v for k, v in os.environ.items() if not k.startswith("PYTHON")}  # don't leak this machine's Python
    env.update(TCL_LIBRARY=str(py / "tcl" / "tcl8.6"), TK_LIBRARY=str(py / "tcl" / "tk8.6"))
    test = ("import safemove, tkinter, comtypes, safemove.app, safemove.wpd, safemove.install, safemove.report; "
            "r = tkinter.Tk(); r.withdraw(); print('tk', r.tk.call('info', 'patchlevel')); r.destroy(); "
            "print('OK', comtypes.__version__)")
    out = subprocess.run([str(py / "python.exe"), "-c", test], cwd=BUILD, env=env,
                         capture_output=True, text=True, timeout=120)
    print(out.stdout.strip(), out.stderr.strip()[-2000:])
    if out.returncode != 0:
        sys.exit("self-test FAILED")

    step("zip")
    DIST.mkdir(exist_ok=True)
    target = DIST / "SafeMove-portable.zip"
    target.unlink(missing_ok=True)
    # remove caches created by the self-test, so the zip is clean
    for cache in BUILD.rglob("__pycache__"):
        shutil.rmtree(cache)
    for gen in (BUILD / "lib" / "comtypes" / "gen").glob("*.py"):
        if gen.name != "__init__.py":
            gen.unlink()
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(BUILD.rglob("*")):
            if f.is_file():
                z.write(f, Path("SafeMove") / f.relative_to(BUILD))
    print(f"{target}  ({target.stat().st_size / 2**20:.1f} MB)")


if __name__ == "__main__":
    main()
