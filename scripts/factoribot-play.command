#!/usr/bin/env bash
#
# One-click launcher for factoribot on macOS.
#
# Double-click in Finder (or run from a terminal). It starts the daemon and
# launches Factorio with --enable-lua-udp on a port that differs from the
# daemon's, which is the bit Steam's launch-options field can't do on macOS.
#
# The port triangle (all must agree, game != daemon):
#   daemon (this script)         : DAEMON_PORT  (default 25001)
#   Factorio --enable-lua-udp=   : GAME_PORT    (default 25000)
#   mod setting "daemon port"    : must equal DAEMON_PORT (its default is 25001)
#
# Overrides via env, e.g.:  FACTORIO_BIN=/path/to/factorio DAEMON_PORT=26000 ./factoribot-play.command
set -uo pipefail

DAEMON_PORT="${DAEMON_PORT:-25001}"
GAME_PORT="${GAME_PORT:-25000}"

# Project root = parent of this script's dir, so it works on any machine/checkout.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR" || { echo "Can't cd to project dir $PROJECT_DIR"; exit 1; }

FACTORIBOT="$PROJECT_DIR/.venv/bin/factoribot"
if [[ ! -x "$FACTORIBOT" ]]; then
  echo "No venv entry point at $FACTORIBOT — run 'make setup' first."
  read -r -p "Press return to close." _
  exit 1
fi

# --- Locate the Factorio binary -------------------------------------------
CANDIDATES=(
  "${FACTORIO_BIN:-}"
  "/Volumes/Spess/SteamLibrary/steamapps/common/Factorio/factorio.app/Contents/MacOS/factorio"
  "$HOME/Library/Application Support/Steam/steamapps/common/Factorio/factorio.app/Contents/MacOS/factorio"
  "/Applications/factorio.app/Contents/MacOS/factorio"
)
FACTORIO_BIN=""
for c in "${CANDIDATES[@]}"; do
  if [[ -n "$c" && -x "$c" ]]; then FACTORIO_BIN="$c"; break; fi
done
if [[ -z "$FACTORIO_BIN" ]]; then
  echo "Couldn't find the Factorio binary. Set FACTORIO_BIN=/path/to/factorio and re-run."
  read -r -p "Press return to close." _
  exit 1
fi

# --- Start the daemon (only if not already running) -----------------------
STARTED_DAEMON=""
if pgrep -f "factoribot.* serve" >/dev/null 2>&1; then
  echo "Daemon already running; using it."
else
  echo "Starting daemon on port $DAEMON_PORT ..."
  "$FACTORIBOT" serve --port "$DAEMON_PORT" --verbose &
  STARTED_DAEMON=$!
  sleep 1
  if ! kill -0 "$STARTED_DAEMON" 2>/dev/null; then
    echo "Daemon failed to start (missing API key or data dump?). See output above."
    read -r -p "Press return to close." _
    exit 1
  fi
fi

cleanup() {
  if [[ -n "$STARTED_DAEMON" ]]; then
    echo "Stopping daemon ($STARTED_DAEMON) ..."
    kill "$STARTED_DAEMON" 2>/dev/null
  fi
}
trap cleanup EXIT INT TERM

# --- Launch the game (blocks until you quit Factorio) ---------------------
echo "Launching Factorio (--enable-lua-udp=$GAME_PORT)"
echo "  binary: $FACTORIO_BIN"
echo "In-game: Ctrl+K (or /factoribot ...). Watch this window for daemon traffic."
echo "--------------------------------------------------------------------------"
"$FACTORIO_BIN" --enable-lua-udp="$GAME_PORT"

echo "Factorio exited."
