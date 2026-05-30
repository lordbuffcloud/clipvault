# Clipboard History Applet Implementation Plan

> **For Hermes:** Keep the implementation small, stdlib-only, and verifiable in WSL.

**Goal:** Build a local clipboard-history applet that monitors copied text, stores prior clipboard entries, and lets the user reload an older item for pasting.

**Architecture:** Use a small Python package with a tested core history/persistence layer, a platform-aware clipboard backend, and a curses terminal UI. The app stores history locally as JSON under the user's data directory and avoids extra dependencies.

**Tech Stack:** Python 3.12, standard library only (`curses`, `subprocess`, `json`, `unittest`).

---

## Assumptions

- Build a local app in a standalone project folder without touching existing home files.
- Default to text clipboard history; images/files are out of scope for the first version.
- Because this session is running in WSL, clipboard integration should prefer Windows clipboard commands when available (`powershell.exe Get-Clipboard`, `clip.exe`), with Linux/macOS fallbacks.

## Success Criteria

1. `python3 -m unittest discover -s tests` passes.
2. `python3 -m compileall clipvault tests` passes.
3. `python3 -m clipvault --help` shows usage.
4. User can run `python3 -m clipvault` to open the applet.
5. App supports: persistent history, dedupe, search, pin/unpin, delete, clear unpinned, copy selected item back to clipboard, pause/resume monitoring.

## Tasks

### Task 1: Core tests

Create tests for:
- adding non-empty copied text;
- ignoring empty text;
- moving duplicate text to the top instead of duplicating it;
- enforcing max history size while preserving pinned items when possible;
- searching content case-insensitively;
- saving and loading JSON history;
- deleting and pinning entries.

### Task 2: Core implementation

Create `clipvault/history.py` with:
- `ClipboardItem` dataclass;
- `ClipboardHistory` manager;
- JSON load/save;
- atomic writes;
- pure methods for add/search/delete/pin/clear.

### Task 3: Clipboard backend

Create `clipvault/clipboard_backends.py` with:
- platform command discovery;
- WSL Windows clipboard support;
- macOS and Linux fallbacks;
- clear error messages if no backend exists.

### Task 4: Applet UI

Create `clipvault/app.py` with a curses interface:
- list history entries;
- search bar;
- copy selected item;
- pin/unpin;
- delete;
- clear unpinned;
- pause/resume monitoring;
- status/help line.

### Task 5: Packaging and docs

Create:
- `clipvault/__main__.py` entry point;
- `pyproject.toml` metadata;
- `README.md` with run instructions and shortcuts.

### Task 6: Verification

Run:

```bash
python3 -m unittest discover -s tests
python3 -m compileall clipvault tests
python3 -m clipvault --help
```
