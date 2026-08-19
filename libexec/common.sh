#!/bin/bash
# Shared helpers for ntool. Sourced by bin/ntool. macOS bash 3.2 safe.

NTOOL_HOME="${NTOOL_HOME:-$HOME/.network-tool}"
NTOOL_PORT="${NTOOL_PORT:-8080}"
NTOOL_WEB_PORT="${NTOOL_WEB_PORT:-8081}"
NTOOL_CA="$HOME/.mitmproxy/mitmproxy-ca-cert.pem"

CAPTURES_DIR="$NTOOL_HOME/captures"
SESSIONS_DIR="$NTOOL_HOME/sessions"
RULES_FILE="$NTOOL_HOME/rules.json"
PID_FILE="$NTOOL_HOME/capture.pid"
META_FILE="$NTOOL_HOME/capture.meta"
HOSTS_FILE="$NTOOL_HOME/discovered-hosts.txt"

# MARK: - Output

_bold() { printf '\033[1m%s\033[0m\n' "$1"; }
log()   { printf '%s\n' "$*" >&2; }
die()   { printf 'error: %s\n' "$*" >&2; exit 1; }

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "$1 not found.${2:+ $2}"
}

ensure_dirs() {
  mkdir -p "$CAPTURES_DIR" "$SESSIONS_DIR"
}

# MARK: - mitmproxy

require_mitmproxy() {
  command -v mitmdump >/dev/null 2>&1 || \
    die "mitmdump not found. Install it with: brew install --cask mitmproxy"
}

ensure_ca() {
  if [ ! -f "$NTOOL_CA" ]; then
    log "generating mitmproxy CA…"
    ( mitmdump -q -n >/dev/null 2>&1 & local mpid=$!; sleep 3; kill "$mpid" 2>/dev/null )
  fi
  [ -f "$NTOOL_CA" ] || die "CA not generated at $NTOOL_CA"
}

# MARK: - Simulator

booted_udid() {
  xcrun simctl list devices booted 2>/dev/null \
    | grep -Eo '[0-9A-F]{8}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{12}' \
    | head -1
}

# lift_token <bundle_id> — prints the rm-authentication token from the booted sim
lift_token() {
  local bundle="$1" container plist
  container="$(xcrun simctl get_app_container booted "$bundle" data 2>/dev/null)" || return 1
  plist="$container/Library/Preferences/$bundle.plist"
  [ -f "$plist" ] || return 1
  /usr/bin/python3 - "$plist" <<'PY'
import plistlib, sys
try:
    data = plistlib.load(open(sys.argv[1], "rb"))
    print(data.get("rm-authentication", ""))
except Exception:
    pass
PY
}

# MARK: - Network services (system-proxy fallback)

active_services() {
  networksetup -listallnetworkservices 2>/dev/null | tail -n +2 | grep -v '^\*'
}
