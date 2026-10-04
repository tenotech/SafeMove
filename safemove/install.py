"""Install / uninstall the portable build for the current user (no admin rights needed).

    python\\python.exe -m safemove.install              install (from the unzipped folder)
    python\\pythonw.exe -m safemove.install --uninstall  uninstall (Settings > Apps does this)

Install = copy the app to %LOCALAPPDATA%\\Programs\\SafeMove, create Desktop + Start menu shortcuts
that start the signed pythonw.exe, and register an entry in Settings > Apps. Nothing here creates a
new executable, so Smart App Control has nothing to block. Photos (C:\\SafeMove) and settings are never touched.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tkinter as tk
import winreg
from pathlib import Path
from tkinter import messagebox

import comtypes.client

from . import __version__

NAME = "SafeMove"
TARGET = Path(os.environ["LOCALAPPDATA"]) / "Programs" / "SafeMove"
UNINSTALL_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\SafeMove"


def _source_root() -> Path:
    return Path(__file__).resolve().parent.parent  # folder that holds python\, lib\, safemove\


def _shell():
    return comtypes.client.CreateObject("WScript.Shell", dynamic=True)


def _shortcut_paths(shell) -> dict[str, Path]:
    programs = Path(shell.SpecialFolders("Programs"))
    return {
        "desktop": Path(shell.SpecialFolders("Desktop")) / f"{NAME}.lnk",
        "start": programs / f"{NAME}.lnk",
        "report": programs / f"{NAME} - device report.lnk",
    }


def _remove_legacy(shell) -> None:
    """Removes an install of the app under its old name (iPhone Mover). Photos and logs are not touched."""
    programs = Path(shell.SpecialFolders("Programs"))
    for link in (Path(shell.SpecialFolders("Desktop")) / "iPhone Mover.lnk", programs / "iPhone Mover.lnk",
                 programs / "iPhone Mover - device report.lnk"):
        link.unlink(missing_ok=True)
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Uninstall\iPhoneMover")
    except OSError:
        pass
    shutil.rmtree(Path(os.environ["LOCALAPPDATA"]) / "Programs" / "iPhoneMover", ignore_errors=True)


def _make_shortcut(shell, path: Path, args: str, description: str) -> None:
    link = shell.CreateShortcut(str(path))
    link.TargetPath = str(TARGET / "python" / "pythonw.exe")
    link.Arguments = args
    link.WorkingDirectory = str(TARGET)
    link.IconLocation = str(TARGET / "safemove" / "app.ico")
    link.Description = description
    link.Save()


def _app_running_from_target() -> bool:
    out = subprocess.run(["powershell", "-NoProfile", "-Command",
                          "Get-CimInstance Win32_Process -Filter \"Name='pythonw.exe'\" | "
                          "Select-Object -ExpandProperty ExecutablePath"],
                         capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
    return str(TARGET).lower() in out.stdout.lower()


def install() -> None:
    src = _source_root()
    if _app_running_from_target():
        messagebox.showwarning(NAME, "SafeMove is running. Close it, then run Install again.")
        return
    if src != TARGET:
        TARGET.mkdir(parents=True, exist_ok=True)
        for item in ("python", "lib", "safemove", "README.txt", "USER_GUIDE.md", "LICENSE.txt"):
            s, d = src / item, TARGET / item
            if s.is_dir():
                if d.exists() and item == "safemove":
                    shutil.rmtree(d)  # replace our code entirely on update
                shutil.copytree(s, d, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__"))
            elif s.exists():
                shutil.copy2(s, d)

    shell = _shell()
    _remove_legacy(shell)
    paths = _shortcut_paths(shell)
    _make_shortcut(shell, paths["desktop"], "-m safemove.app", "Safely move phone photos and videos to this PC")
    _make_shortcut(shell, paths["start"], "-m safemove.app", "Safely move phone photos and videos to this PC")
    _make_shortcut(shell, paths["report"], "-m safemove.report",
                   "Describe how this iPhone shows its photos over USB (for bug reports)")

    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY) as k:
        values = {
            "DisplayName": NAME,
            "DisplayVersion": __version__,
            "Publisher": "SafeMove (open source, MIT)",
            "InstallLocation": str(TARGET),
            "DisplayIcon": str(TARGET / "safemove" / "app.ico"),
            "UninstallString": f'"{TARGET / "python" / "pythonw.exe"}" -m safemove.install --uninstall',
        }
        for name, value in values.items():
            winreg.SetValueEx(k, name, 0, winreg.REG_SZ, value)
        winreg.SetValueEx(k, "NoModify", 0, winreg.REG_DWORD, 1)
        winreg.SetValueEx(k, "NoRepair", 0, winreg.REG_DWORD, 1)

    if messagebox.askyesno(NAME, f"{NAME} {__version__} is installed.\n\n"
                                 "Start it from the Desktop or the Start menu.\n"
                                 "Uninstall: Settings > Apps > Installed apps.\n\nStart it now?"):
        subprocess.Popen([str(TARGET / "python" / "pythonw.exe"), "-m", "safemove.app"], cwd=TARGET)


def uninstall() -> None:
    if not messagebox.askyesno(NAME, f"Uninstall {NAME}?\n\nYour photos (e.g. C:\\SafeMove) and logs are kept."):
        return
    shell = _shell()
    for p in _shortcut_paths(shell).values():
        p.unlink(missing_ok=True)
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY)
    except OSError:
        pass
    # This Python runs from TARGET, so the folder is removed by a separate process after we exit.
    subprocess.Popen(f'cmd /c timeout /t 3 /nobreak >nul & rmdir /s /q "{TARGET}"',
                     creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS)
    messagebox.showinfo(NAME, f"{NAME} was uninstalled.")


def main() -> None:
    root = tk.Tk()
    root.withdraw()
    try:
        uninstall() if "--uninstall" in sys.argv else install()
    except Exception as e:  # show problems instead of failing silently
        messagebox.showerror(NAME, f"Something went wrong:\n{e!r}")
    finally:
        root.destroy()


if __name__ == "__main__":
    main()
