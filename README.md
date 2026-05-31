# ClipVault

ClipVault is a local terminal clipboard-history applet from CK42X. It keeps a small searchable history of copied text so one accidental copy does not bury the thing you needed to paste.

It is intentionally boring where it matters: no cloud account, no third-party Python packages, no telemetry, and no hidden service. Your clipboard history is stored as plain JSON on your own machine.

```text
      (__)    CK42X // CLIPVAULT                                                           LIVE
      (oo)    clipboard recovery console // moo-ving clips back into reach
   /---\/
  /| CV||     FILTER  press / to filter
  *|---||
   ^^  ^^
────────────────────────────────────────────────────────────────────────────────────────────────
┌───────────────────────────────────────────────────────────────┐  ┌─────────────────────────┐
│ HISTORY BUFFER                                                │  │ OPS                     │
│ ▶ ★ 001 │ release notes: polish clipboard history UI         │  │  items    42            │
│      002 │ python3 -m clipvault --history ./history.json      │  │  visible  42            │
│      003 │ support reply: thanks, I will test this today      │  │  pinned   3             │
└───────────────────────────────────────────────────────────────┘  └─────────────────────────┘
```

## What it does

- Watches your text clipboard while ClipVault is running.
- Saves copied text to a local JSON history file.
- Deduplicates repeated clips instead of cluttering the list.
- Searches old clipboard entries from a keyboard-first terminal UI.
- Pins important clips so they survive normal cleanup.
- Copies a selected old item back to the system clipboard.
- Runs as either an interactive TUI or a headless daemon.
- Installs global `clipvault` / `clipvaultd` commands.
- Can create a Windows-login Startup launcher when installed from WSL.

## Install

From the repo folder:

```bash
bash scripts/install-global.sh
```

That installs command wrappers into `~/.local/bin`:

| Command | Purpose |
| --- | --- |
| `clipvault` | Open the interactive terminal UI |
| `clipvaultd` | Run the headless clipboard daemon in the foreground |
| `clipvault-autostart-install` | Recreate the Windows Startup launcher from WSL |
| `clipvault-autostart-remove` | Remove the Windows Startup launcher |

If your shell cannot find `clipvault`, add this to your shell profile:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

### Installer options

```bash
bash scripts/install-global.sh --help
bash scripts/install-global.sh --no-autostart
bash scripts/install-global.sh --bin-dir "$HOME/bin"
bash scripts/uninstall.sh
```

The installer preserves your local history when uninstalling.

## Run without installing

```bash
python3 -m clipvault
python3 -m clipvault --help
python3 -m clipvault --snapshot-ui
```

Run a headless daemon:

```bash
python3 -m clipvault --daemon
python3 -m clipvault --daemon --once
```

Use a custom history file or size limit:

```bash
python3 -m clipvault --history ./history.json --max-items 200
```

## Keyboard shortcuts

| Key | Action |
| --- | --- |
| `q` | Quit |
| `↑` / `k` | Move up |
| `↓` / `j` | Move down |
| `Enter` / `c` | Copy selected item back to clipboard |
| `p` | Pin/unpin selected item |
| `d` | Delete selected item |
| `x` | Clear unpinned items |
| `/` | Search |
| `Esc` | Clear search |
| `Space` | Pause/resume monitoring |
| `r` | Read current clipboard now |
| `?` | Toggle help |

## Clipboard backend support

ClipVault tries these clipboard backends in order:

1. WSL using Windows clipboard commands: `powershell.exe Get-Clipboard -Raw` and `clip.exe`.
2. macOS: `pbpaste` and `pbcopy`.
3. Wayland Linux: `wl-paste` and `wl-copy`.
4. X11 Linux: `xclip`.
5. X11 Linux: `xsel`.

If no backend is available, the app still opens but cannot read or write the system clipboard until a backend exists on `PATH`.

## Data and privacy

Default history path:

```text
~/.local/share/clipvault/history.json
```

Startup daemon log path:

```text
~/.local/state/clipvault/startup.log
```

Clipboard content can be sensitive. ClipVault stores text locally in plain JSON so you can inspect, back up, edit, or delete it. Do not pin or retain secrets you do not want stored on disk.

Useful cleanup commands:

```bash
clipvault --print-path
rm ~/.local/share/clipvault/history.json
```

## Development

```bash
python3 -m unittest discover -s tests
python3 -m compileall clipvault tests
python3 -m clipvault --help
PYTHONDONTWRITEBYTECODE=1 python3 -m clipvault --snapshot-ui
```

## Support

ClipVault is free. If it saves you time, you can support CK42X here:

https://buymeacoffee.com/napalmlighs

## License

MIT. See [LICENSE](LICENSE).
