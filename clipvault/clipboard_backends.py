"""Platform-aware text clipboard access."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess
from typing import Sequence


class ClipboardError(RuntimeError):
    """Raised when clipboard access is unavailable or fails."""


@dataclass(frozen=True)
class ClipboardCommand:
    name: str
    read_command: Sequence[str]
    write_command: Sequence[str]


class ClipboardBackend:
    """Read and write plain text through the first available system clipboard."""

    def __init__(self, command: ClipboardCommand | None = None, timeout: float = 2.0):
        self.command = command or detect_clipboard_command()
        self.timeout = timeout

    @property
    def name(self) -> str:
        return self.command.name

    def read_text(self) -> str:
        try:
            completed = subprocess.run(
                self.command.read_command,
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.timeout,
            )
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            raise ClipboardError(f"Could not read clipboard with {self.command.name}: {exc}") from exc
        return completed.stdout.rstrip("\r\n")

    def write_text(self, text: str) -> None:
        try:
            subprocess.run(
                self.command.write_command,
                input=text,
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.timeout,
            )
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            raise ClipboardError(f"Could not write clipboard with {self.command.name}: {exc}") from exc


def _which_or_existing_path(command: str, *fallback_paths: str) -> str | None:
    found = shutil.which(command)
    if found:
        return found
    for path in fallback_paths:
        if Path(path).exists():
            return path
    return None


def detect_clipboard_command() -> ClipboardCommand:
    """Return the best clipboard command for this host."""

    powershell = _which_or_existing_path(
        "powershell.exe",
        "/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe",
        "/mnt/c/Windows/Sysnative/WindowsPowerShell/v1.0/powershell.exe",
    )
    clip = _which_or_existing_path(
        "clip.exe",
        "/mnt/c/Windows/System32/clip.exe",
        "/mnt/c/Windows/Sysnative/clip.exe",
    )
    if powershell and clip:
        return ClipboardCommand(
            name="windows-clipboard-from-wsl",
            read_command=[powershell, "-NoProfile", "-Command", "Get-Clipboard -Raw"],
            write_command=[clip],
        )

    pbpaste = shutil.which("pbpaste")
    pbcopy = shutil.which("pbcopy")
    if pbpaste and pbcopy:
        return ClipboardCommand(
            name="macos-pasteboard",
            read_command=[pbpaste],
            write_command=[pbcopy],
        )

    wl_paste = shutil.which("wl-paste")
    wl_copy = shutil.which("wl-copy")
    if wl_paste and wl_copy:
        return ClipboardCommand(
            name="wayland-clipboard",
            read_command=[wl_paste, "--no-newline"],
            write_command=[wl_copy],
        )

    xclip = shutil.which("xclip")
    if xclip:
        return ClipboardCommand(
            name="xclip",
            read_command=[xclip, "-selection", "clipboard", "-out"],
            write_command=[xclip, "-selection", "clipboard", "-in"],
        )

    xsel = shutil.which("xsel")
    if xsel:
        return ClipboardCommand(
            name="xsel",
            read_command=[xsel, "--clipboard", "--output"],
            write_command=[xsel, "--clipboard", "--input"],
        )

    raise ClipboardError(
        "No clipboard backend found. Install wl-clipboard/xclip/xsel, run on macOS, "
        "or run from WSL with powershell.exe and clip.exe on PATH."
    )
