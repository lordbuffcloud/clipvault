#!/usr/bin/env bash
# ClipVault hosted installer
# Usage: curl -fsSL https://ck42x.com/install/clipvault.sh | bash
set -euo pipefail

REPO_URL="${CLIPVAULT_REPO_URL:-https://github.com/lordbuffcloud/clipvault.git}"
REF="${CLIPVAULT_REF:-main}"
INSTALL_ROOT="${CLIPVAULT_INSTALL_ROOT:-${HOME}/.local/share/ck42x}"
INSTALL_DIR="${CLIPVAULT_INSTALL_DIR:-${INSTALL_ROOT}/clipvault}"
BIN_DIR="${BIN_DIR:-${HOME}/.local/bin}"
TARBALL_URL="${CLIPVAULT_TARBALL_URL:-https://github.com/lordbuffcloud/clipvault/archive/refs/heads/${REF}.tar.gz}"

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "error: '$1' is required but not installed." >&2
    exit 1
  }
}

copy_from_tarball() {
  need_cmd curl
  need_cmd tar
  local tmp extracted
  tmp="$(mktemp -d)"
  trap 'rm -rf "$tmp"' EXIT
  echo "-> Downloading ClipVault source tarball..."
  curl -fsSL "$TARBALL_URL" -o "$tmp/clipvault.tar.gz"
  tar -xzf "$tmp/clipvault.tar.gz" -C "$tmp"
  extracted="$(find "$tmp" -maxdepth 1 -type d -name 'clipvault-*' | head -n 1)"
  if [[ -z "$extracted" ]]; then
    echo "error: could not find ClipVault source inside tarball." >&2
    exit 1
  fi
  rm -rf "$INSTALL_DIR"
  mkdir -p "$INSTALL_DIR"
  cp -a "$extracted/." "$INSTALL_DIR/"
}

install_or_update_source() {
  mkdir -p "$INSTALL_ROOT"
  if command -v git >/dev/null 2>&1; then
    if [[ -d "$INSTALL_DIR/.git" ]]; then
      echo "-> Updating ClipVault source in $INSTALL_DIR..."
      git -C "$INSTALL_DIR" fetch --depth 1 origin "$REF"
      git -C "$INSTALL_DIR" checkout -q "$REF" 2>/dev/null || git -C "$INSTALL_DIR" checkout -q -B "$REF" "origin/$REF"
      git -C "$INSTALL_DIR" reset --hard -q "origin/$REF"
    else
      echo "-> Cloning ClipVault source into $INSTALL_DIR..."
      rm -rf "$INSTALL_DIR"
      git clone --depth 1 --branch "$REF" "$REPO_URL" "$INSTALL_DIR"
    fi
  else
    copy_from_tarball
  fi
}

need_cmd python3
install_or_update_source

if [[ ! -x "$INSTALL_DIR/scripts/install-global.sh" ]]; then
  echo "error: installer not found at $INSTALL_DIR/scripts/install-global.sh" >&2
  exit 1
fi

echo "-> Installing ClipVault commands into $BIN_DIR..."
BIN_DIR="$BIN_DIR" bash "$INSTALL_DIR/scripts/install-global.sh" "$@"

cat <<DONE

[ok] ClipVault installer finished.

Try:
  clipvault --help
  clipvault

If your shell cannot find clipvault, add this to your profile:
  export PATH="$BIN_DIR:\$PATH"
DONE
