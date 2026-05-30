#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BIN_DIR="${BIN_DIR:-$HOME/.local/bin}"
STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/clipvault"
DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/clipvault"
INSTALL_AUTOSTART=auto
UNINSTALL=0
UNINSTALL_AUTOSTART_ONLY=0

usage() {
  cat <<'USAGE'
ClipVault installer

Installs the ClipVault terminal clipboard-history app for the current user.

Usage:
  bash scripts/install-global.sh [options]

Options:
  --bin-dir DIR       Install command wrappers into DIR (default: ~/.local/bin)
  --no-autostart     Do not install the Windows-login Startup launcher
  --autostart        Force Windows-login Startup launcher installation
  --uninstall        Remove installed wrappers and Startup launcher
  -h, --help         Show this help

Installed commands:
  clipvault                    Interactive terminal UI
  clipvaultd                   Headless clipboard daemon
  clipvault-autostart-install  Recreate Windows Startup launcher from WSL
  clipvault-autostart-remove   Remove Windows Startup launcher
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --bin-dir)
      BIN_DIR="${2:?--bin-dir requires a directory}"
      shift 2
      ;;
    --no-autostart)
      INSTALL_AUTOSTART=0
      shift
      ;;
    --autostart)
      INSTALL_AUTOSTART=1
      shift
      ;;
    --uninstall)
      UNINSTALL=1
      shift
      ;;
    --uninstall-autostart-only)
      UNINSTALL_AUTOSTART_ONLY=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

quote_for_bash() {
  printf "%q" "$1"
}

is_wsl() {
  [[ -d /mnt/c ]] && grep -qi microsoft /proc/version 2>/dev/null
}

windows_startup_dir() {
  if command -v powershell.exe >/dev/null 2>&1 && command -v wslpath >/dev/null 2>&1; then
    local appdata
    appdata="$(powershell.exe -NoProfile -Command '[Console]::OutputEncoding=[Text.Encoding]::UTF8; $env:APPDATA' 2>/dev/null | tr -d '\r' | tail -n 1)"
    if [[ -n "$appdata" ]]; then
      wslpath -u "$appdata/Microsoft/Windows/Start Menu/Programs/Startup"
      return 0
    fi
  fi
  return 1
}

write_autostart_launcher() {
  if ! is_wsl; then
    echo "Windows Startup launcher skipped: this does not look like WSL."
    return 0
  fi

  local startup_dir launcher quoted_root daemon_command vbs_command
  startup_dir="$(windows_startup_dir || true)"
  if [[ -z "$startup_dir" ]]; then
    echo "Windows Startup launcher skipped: could not resolve Windows APPDATA." >&2
    return 1
  fi

  launcher="$startup_dir/ClipVaultDaemon.vbs"
  mkdir -p "$startup_dir" "$STATE_DIR" "$DATA_DIR"
  quoted_root="$(quote_for_bash "$PROJECT_ROOT")"
  daemon_command="mkdir -p ~/.local/state/clipvault; cd $quoted_root && PYTHONDONTWRITEBYTECODE=1 exec python3 -m clipvault --daemon >> ~/.local/state/clipvault/startup.log 2>&1"
  vbs_command="$daemon_command"

  cat >"$launcher" <<VBS
Set WshShell = CreateObject("WScript.Shell")
cmd = "wsl.exe -e bash -lc ""$vbs_command"""
WshShell.Run cmd, 0, False
VBS

  echo "Installed Windows Startup launcher: $launcher"
  echo "Daemon log: $STATE_DIR/startup.log"
}

remove_autostart_launcher() {
  local startup_dir launcher
  startup_dir="$(windows_startup_dir || true)"
  if [[ -n "$startup_dir" ]]; then
    launcher="$startup_dir/ClipVaultDaemon.vbs"
    rm -f "$launcher"
    echo "Removed Windows Startup launcher if present: $launcher"
  else
    echo "Windows Startup launcher removal skipped: could not resolve Windows APPDATA."
  fi
}

if [[ "$UNINSTALL" -eq 1 ]]; then
  rm -f "$BIN_DIR/clipvault" \
        "$BIN_DIR/clipvaultd" \
        "$BIN_DIR/clipvault-autostart-install" \
        "$BIN_DIR/clipvault-autostart-remove"
  remove_autostart_launcher
  echo "ClipVault commands removed from $BIN_DIR"
  echo "Local history was preserved at: $DATA_DIR/history.json"
  exit 0
fi

mkdir -p "$BIN_DIR" "$STATE_DIR" "$DATA_DIR"
QUOTED_ROOT="$(quote_for_bash "$PROJECT_ROOT")"

cat >"$BIN_DIR/clipvault" <<WRAPPER
#!/usr/bin/env bash
cd $QUOTED_ROOT
exec python3 -m clipvault "\$@"
WRAPPER
chmod +x "$BIN_DIR/clipvault"

cat >"$BIN_DIR/clipvaultd" <<WRAPPER
#!/usr/bin/env bash
cd $QUOTED_ROOT
exec python3 -m clipvault --daemon "\$@"
WRAPPER
chmod +x "$BIN_DIR/clipvaultd"

cat >"$BIN_DIR/clipvault-autostart-install" <<WRAPPER
#!/usr/bin/env bash
cd $QUOTED_ROOT
exec bash scripts/install-global.sh --autostart "\$@"
WRAPPER
chmod +x "$BIN_DIR/clipvault-autostart-install"

cat >"$BIN_DIR/clipvault-autostart-remove" <<WRAPPER
#!/usr/bin/env bash
cd $QUOTED_ROOT
exec bash scripts/install-global.sh --no-autostart --uninstall-autostart-only "\$@"
WRAPPER
chmod +x "$BIN_DIR/clipvault-autostart-remove"

# The generated remove wrapper calls back into this script with a private flag.
# Handle it after wrapper creation so old installations can self-heal on reinstall.
if [[ "$UNINSTALL_AUTOSTART_ONLY" -eq 1 ]]; then
  remove_autostart_launcher
  exit 0
fi

if [[ "$INSTALL_AUTOSTART" == "1" || ( "$INSTALL_AUTOSTART" == "auto" && -d /mnt/c ) ]]; then
  write_autostart_launcher || true
else
  echo "Windows Startup launcher not installed. Run clipvault-autostart-install later if needed."
fi

cat <<DONE

ClipVault installed.

Commands:
  clipvault                    interactive TUI
  clipvaultd                   foreground daemon
  clipvault --daemon --once    one-shot clipboard capture test
  clipvault-autostart-install  enable Windows-login daemon
  clipvault-autostart-remove   disable Windows-login daemon

Paths:
  history  $DATA_DIR/history.json
  daemon   $DATA_DIR/daemon.lock
  logs     $STATE_DIR/startup.log

If 'clipvault' is not found, add this to your shell profile:
  export PATH="$BIN_DIR:\$PATH"
DONE
