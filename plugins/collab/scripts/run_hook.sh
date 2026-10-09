#!/bin/sh
# Hook launcher: finds a working Python 3.9+ and runs collab_gate.py with it.
# Usage (from hooks/hooks.json): sh run_hook.sh <event>   — hook input JSON on stdin.
#
# Why a launcher: the interpreter is `python3` on macOS/Linux but usually `python`
# or `py -3` on Windows, where `python3` may be a Microsoft Store alias that does
# not run Python at all. On Windows Claude Code runs this through Git Bash.

event="$1"
root="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
script="$root/scripts/collab_gate.py"
data="${CLAUDE_PLUGIN_DATA:-$HOME/.claude/plugins/data/collab}"
cache="$data/python-command"

is_python39() {
    "$@" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' </dev/null >/dev/null 2>&1
}

# Fast path: the interpreter found on an earlier run (checked only for existence).
if [ -f "$cache" ]; then
    py=$(cat "$cache")
    if command -v ${py%% *} >/dev/null 2>&1; then
        exec $py "$script" "$event"
    fi
fi

for candidate in python3 python "py -3"; do
    if is_python39 $candidate; then
        mkdir -p "$data" 2>/dev/null && printf '%s' "$candidate" > "$cache" 2>/dev/null
        exec $candidate "$script" "$event"
    fi
done

# No Python: the write gate fails closed, every other event is skipped.
if [ "$event" = "pre-tool-use" ]; then
    printf '%s\n' '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"collab: Python 3.9+ not found (tried python3, python, py -3), so writes are blocked. Install Python 3.9+ or disable the collab plugin in /plugin."}}'
else
    echo "collab: Python 3.9+ not found (tried python3, python, py -3)" >&2
fi
exit 0
