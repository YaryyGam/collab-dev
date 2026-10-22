#!/usr/bin/env python3
"""Hook entry point of the collab plugin.

Usage (from hooks/hooks.json): collab_gate.py <event>, hook input JSON on stdin.

Every event handler is a pure function ``decide_*(event, state, env)`` that
returns the hook output dict (or None) and mutates ``state`` in place; only
``main()`` touches stdin/stdout and the disk. Tests call the handlers directly.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent

MODES = ("learning", "collaborative", "review")
DEFAULT_MODE = "collaborative"
# Stages in which Claude may write and the unit must end with a final review.
OPEN_STAGES = ("agreed", "skipped")
# Tools that run shell commands; PowerShell is Claude Code's alternative shell on Windows.
SHELL_TOOLS = ("Bash", "PowerShell")

GATE_MESSAGE = (
    "collab: writing to the project is blocked: the approach for this unit of work has not been "
    "agreed on yet. Continue the discussion: the developer's approach → their reasons → analysis → "
    "alternatives → joint choice. Writing opens once the developer runs "
    "/collab:agree <the approach in their own words>, or /collab:skip <reason>, or /collab:off "
    "<reason> themselves. Do not try to get around the block some other way."
)
EDIT_ONLY_MESSAGE = (
    "collab: change the contents of project files only with Edit or Write, so the developer sees every "
    "code change as a diff; this command was not run. Make the same change with Edit (Write for a new file). "
    "Everything else stays in the shell: git, package managers, tests, rm/mv. A scratch file outside the "
    "project can be written with Write or redirected into /tmp."
)
PLAN_START_MESSAGE = (
    "The developer asked for a staged plan. Create it as tasks with TaskCreate, one per stage, then stop and "
    "show the plan: writes and starting a stage are blocked until the developer replies."
)
PAUSED_MESSAGE = (
    "collab: the plan is paused for the developer: changing files and starting or finishing a stage are blocked "
    "until they reply. Explain what was done in this stage and end your reply with a question whether to continue."
)
RESUMED_MESSAGE = (
    "collab: the developer replied after a pause in the plan, so the pause is lifted. If the message means "
    "\"go on\", start the next stage (TaskUpdate → in_progress). If it is feedback or a question, deal with it "
    "within the current stage, explain what you changed, and end your reply with a question again."
)
GIT_MESSAGE = (
    "collab: commits, pushes and history-changing git commands run only with the developer's permission, "
    "so this command was not run. Don't run it another way: tell the developer which command to type: "
    "/collab:commit [note] for a commit, /collab:push [branch] for a push (the current branch if omitted), "
    "/collab:git <command> [why] for merge, rebase, cherry-pick, revert, reset, tag, commit --amend or push --force. "
    "Each permission covers one such git call."
)
SELF_PROTECT_MESSAGE = (
    "collab: only the developer may change the plugin's state files, through the /collab:* "
    "commands. Do not modify them."
)


# --------------------------------------------------------------------------- #
# Environment and state
# --------------------------------------------------------------------------- #

@dataclass
class Env:
    """Everything a handler needs to know about where it runs."""

    data_dir: Path
    project_dir: Path
    config: dict
    default_mode: str = DEFAULT_MODE
    modes_dir: Path = PLUGIN_ROOT / "modes"


@dataclass
class SessionState:
    mode: str = DEFAULT_MODE
    stage: str = "discussing"
    agreement: str = ""
    changed_files: list = field(default_factory=list)
    change_anchors: dict = field(default_factory=dict)  # file → id of the tool call that first changed it
    bash_writes: int = 0
    units_closed: int = 0
    # /collab:plan: the unit goes stage by stage, with a hard pause for the developer after each one
    planned: bool = False
    paused: bool = False
    stage_anchors: dict = field(default_factory=dict)  # like change_anchors, since the last pause
    # one-off permission from /collab:commit|push|git; outlives units (commits come after the review),
    # spent by the git call it allows or by the developer's next message
    git_grant: dict = field(default_factory=dict)

    @property
    def changes(self) -> int:
        return len(self.changed_files) + self.bash_writes

    def open_unit(self, stage: str, agreement: str = "") -> None:
        self.stage = stage
        self.agreement = agreement
        self.changed_files = []
        self.change_anchors = {}
        self.bash_writes = 0
        self.planned = False
        self.paused = False
        self.stage_anchors = {}

    def close_unit(self) -> None:
        if self.stage in OPEN_STAGES:
            self.units_closed += 1
        self.open_unit("discussing")


def load_config(plugin_root: Path = PLUGIN_ROOT) -> dict:
    with open(plugin_root / "config" / "gate.json", encoding="utf-8") as f:
        return json.load(f)


def env_from_os(event: dict) -> Env:
    data_dir = Path(os.environ.get("CLAUDE_PLUGIN_DATA") or Path.home() / ".claude" / "plugins" / "data" / "collab")
    project_dir = Path(os.environ.get("CLAUDE_PROJECT_DIR") or event.get("cwd") or os.getcwd())
    mode = os.environ.get("CLAUDE_PLUGIN_OPTION_DEFAULT_MODE", DEFAULT_MODE)
    return Env(
        data_dir=data_dir,
        project_dir=project_dir,
        config=load_config(),
        default_mode=mode if mode in MODES else DEFAULT_MODE,
    )


def state_path(env: Env, session_id: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", session_id or "unknown")
    return env.data_dir / "sessions" / f"{safe}.json"


def load_state(env: Env, session_id: str) -> SessionState | None:
    """Return the saved state, or None when there is none or it is unreadable."""
    try:
        raw = json.loads(state_path(env, session_id).read_text(encoding="utf-8"))
        known = {k: v for k, v in raw.items() if k in SessionState.__dataclass_fields__}
        return SessionState(**known)
    except (OSError, ValueError, TypeError):
        return None


def save_state(env: Env, session_id: str, state: SessionState) -> None:
    path = state_path(env, session_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(asdict(state), ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)  # atomic: a concurrent reader never sees half a file


def append_journal(env: Env, session_id: str, event: str, detail: str = "") -> None:
    """Local-only log of mode switches, so the developer can see their own pattern."""
    env.data_dir.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "session": session_id,
        "project": str(env.project_dir),
        "event": event,
        "detail": detail,
    }
    with open(env.data_dir / "journal.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def status_line(state: SessionState) -> str:
    if state.stage == "off":
        return (
            f"[collab] mode={state.mode} stage=off: the developer turned the plugin off for the rest of "
            "the session. Work as regular Claude Code; the collaborative development rules do not apply."
        )
    gate = "writes blocked until /collab:agree" if state.stage == "discussing" else "writes allowed"
    line = f"[collab] mode={state.mode} stage={state.stage} ({gate})"
    if state.stage == "agreed":
        line += f"\nAgreed by the developer: \"{state.agreement}\""
    if state.stage == "skipped":
        line += f"\nDiscussion skipped at the developer's request: \"{state.agreement}\". Explanations along the way and the final review are mandatory."
    if state.planned and state.stage in OPEN_STAGES:
        line += ("\nPlan: paused, waiting for the developer's reply (changes and stage updates blocked)." if state.paused
                 else "\nPlan: a stage is in progress; marking it completed pauses the work until the developer replies.")
    return line


def mode_rules(env: Env, mode: str) -> str:
    try:
        return (env.modes_dir / f"{mode}.md").read_text(encoding="utf-8")
    except OSError:
        return ""


# --------------------------------------------------------------------------- #
# Bash write detection (heuristic — see docs/LIMITATIONS.md)
# --------------------------------------------------------------------------- #

_HEREDOC = re.compile(r"<<-?\s*(['\"]?)(\w+)\1[^\n]*\n.*?\n\s*\2\s*(?:\n|$)", re.S)
_QUOTED = re.compile(r"'[^']*'|\"(?:\\.|[^\"\\])*\"")
_SEPARATOR = re.compile(r"\|\||&&|[;|&\n`(){}]|\$\(")
_REDIRECT = re.compile(r"(?:\d+|&)?(?<!<)>>?(?!&)\s*([^\s;&|<>()]+)")
_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")


def _strip_literals(command: str) -> str:
    """Drop heredoc bodies and quoted strings so their contents can't look like syntax."""
    command = _HEREDOC.sub(lambda m: m.group(0).split("\n", 1)[0] + "\n", command)
    return _QUOTED.sub(" Q ", command)


def _program_name(word: str) -> str:
    """`/usr/bin/rm`, `C:\\Git\\usr\\bin\\RM.exe` → `rm`."""
    name = re.split(r"[\\/]", word)[-1].lower()
    return name[:-4] if name.endswith(".exe") else name


def _command_words(segment: str, wrappers: list) -> list:
    words = segment.split()
    while words and (_ASSIGNMENT.match(words[0]) or _program_name(words[0]) in wrappers):
        words = words[1:]
        # `env -i` / `nice -n 5`: skip the wrapper's own flags
        while words and words[0].startswith("-"):
            words = words[1:]
    return words


def _subcommand(args: list) -> str:
    """First positional argument, skipping the values of `-C dir` / `-c key=val`."""
    skip_next = False
    for arg in args:
        if skip_next:
            skip_next = False
        elif arg in ("-C", "-c"):
            skip_next = True
        elif not arg.startswith("-"):
            return arg
    return ""


def bash_write_reason(command: str, config: dict, skip_git: bool = False) -> str | None:
    """Return a short description of why the command looks like a write, or None.
    skip_git: leave git calls to the git gate (a developer's /collab:commit|push|git covers them)."""
    cfg = config["bash"]
    stripped = _strip_literals(command)

    for target in _REDIRECT.findall(stripped):
        if target not in cfg["safe_redirect_targets"]:
            return f"output redirected to a file ({target})"

    for segment in _SEPARATOR.split(stripped):
        words = _command_words(segment, cfg["wrappers"])
        if skip_git and words and _program_name(words[0]) == "git":
            continue
        reason = _segment_write_reason(words, command, cfg)
        if reason:
            return reason
    return None


def _has_write_flag(args: list, flags: list | None) -> bool:
    """`sed -i`, `sed -ni`, `perl -pi`: a flag that makes the program edit files in place."""
    return bool(flags) and any(a in flags or ("-i" in flags and re.fullmatch(r"-[a-zA-Z]*i[a-zA-Z]*", a)) for a in args)


def _is_interpreter(name: str, interpreters: list) -> bool:
    return name in interpreters or bool(re.match(r"python3(\.\d+)?$", name)) or name == "py"


def _writes_inline(raw_command: str, markers: list) -> bool:
    # the code itself sits in quotes/heredoc, so search the raw command
    return any(re.search(marker, raw_command) for marker in markers)


def _segment_write_reason(words: list, raw_command: str, cfg: dict) -> str | None:
    """Check one simple command (program + args) against the bash config lists."""
    if not words:
        return None
    name = _program_name(words[0])
    args = words[1:]
    if name in cfg["write_commands"]:
        return f"command {name}"
    if _has_write_flag(args, cfg["flag_writes"].get(name)):
        return f"{name} modifying files"
    subs = cfg["subcommand_writes"].get(name)
    if subs:
        sub = _subcommand(args)
        if sub in subs:
            return f"{name} {sub}"
    if _is_interpreter(name, cfg["interpreters"]) and _writes_inline(raw_command, cfg["inline_write_markers"]):
        return f"{name} code that looks like it writes a file"
    return None


_PS_HERESTRING = re.compile(r"@(['\"])\r?\n.*?\r?\n\1@", re.S)
_PS_SEPARATOR = re.compile(r"\|\||&&|[;|\n(){}]")
_PS_REDIRECT = re.compile(r"(?:\d|\*)?>>?(?!&)\s*([^\s;|<>()]+)")


def powershell_write_reason(command: str, config: dict, skip_git: bool = False) -> str | None:
    """PowerShell flavour of bash_write_reason: cmdlets, aliases, .NET file APIs, redirects."""
    ps = config["powershell"]
    stripped = _QUOTED.sub(" Q ", _PS_HERESTRING.sub(" Q ", command))

    for target in _PS_REDIRECT.findall(stripped):
        if target.lower() not in ps["safe_redirect_targets"]:
            return f"output redirected to a file ({target})"
    for marker in ps["dotnet_write_markers"]:
        if re.search(marker, command, re.I):
            return "file write through .NET"

    for segment in _PS_SEPARATOR.split(stripped):
        words = segment.split()
        while words and words[0] in ("&", "."):  # call operators
            words = words[1:]
        if not words:
            continue
        name = _program_name(words[0])
        if skip_git and name == "git":
            continue
        args = [a.lower() for a in words[1:]]
        if name in ps["write_commands"]:
            return f"command {name}"
        flags = ps["flag_writes"].get(name)
        if flags and any(a in flags for a in args):
            return f"{name} writing to a file"
        # external programs (git, npm, python …) follow the bash rules
        reason = _segment_write_reason(words, command, config["bash"])
        if reason:
            return reason
    return None


def shell_write_reason(tool: str, command: str, config: dict, skip_git: bool = False) -> str | None:
    if tool == "PowerShell":
        return powershell_write_reason(command, config, skip_git)
    return bash_write_reason(command, config, skip_git)


# --------------------------------------------------------------------------- #
# Git gate: history-changing git commands only with the developer's one-off permission
# --------------------------------------------------------------------------- #

_PUSH_FORCE = ("-f", "--force", "--force-with-lease", "--force-if-includes", "--mirror", "--delete", "-d")


def _git_calls(tool: str, command: str, env: Env) -> list:
    """(action, args) for each git call in the command whose action is in git_gated."""
    if tool == "PowerShell":
        stripped, separator = _QUOTED.sub(" Q ", _PS_HERESTRING.sub(" Q ", command)), _PS_SEPARATOR
    else:
        stripped, separator = _strip_literals(command), _SEPARATOR
    calls = []
    for segment in separator.split(stripped):
        words = _command_words(segment, env.config["bash"]["wrappers"])
        while words and words[0] in ("&", "."):  # PowerShell call operators
            words = words[1:]
        if not words or _program_name(words[0]) != "git":
            continue
        sub = _subcommand(words[1:])
        if sub not in env.config.get("git_gated", []):
            continue
        args = words[words.index(sub) + 1:]
        if sub == "tag" and (not args or args[0] in ("-l", "--list")):
            continue  # listing tags changes nothing
        calls.append((sub, args))
    return calls


def _grant_allows(grant: dict, sub: str, args: list) -> bool:
    if not grant:
        return False
    if grant["action"] == "git":
        return sub == grant["subcommand"]
    if sub != grant["action"]:
        return False
    if sub == "commit":
        return "--amend" not in args
    # push: never forced; only into the named branch, or the current one (no refspec / HEAD)
    if any(a in _PUSH_FORCE or a.startswith("--force") for a in args):
        return False
    refs = [a for a in args if not a.startswith("-")][1:]  # the first positional is the remote
    if any(r.startswith(("+", ":")) for r in refs):
        return False
    if not grant.get("branch"):
        return all(r == "HEAD" for r in refs)
    return bool(refs) and all(r.split(":")[-1] == grant["branch"] for r in refs)


def _git_denied(tool: str, command: str, state: SessionState, env: Env) -> str | None:
    """The first gated git call the developer's permission doesn't cover, as "git <action>"."""
    for sub, args in _git_calls(tool, command, env):
        if not _grant_allows(state.git_grant, sub, args):
            return f"git {sub}"
    return None


def _inside_project(target: str, cwd: Path, env: Env) -> bool:
    """Whether a shell write target is a project file. `$VAR/...` and quoted targets (`Q`) are unknown: no."""
    if not target or target == "Q" or target.startswith(("$", "/dev/")):
        return False
    path = Path(_native_path(target)).expanduser()
    return _is_inside(str(path if path.is_absolute() else cwd / path), env.project_dir)


def _write_target(args: list) -> str:
    """The file a tee-like command writes: the value of -Path/-FilePath/-LiteralPath, else its first positional argument."""
    for i, arg in enumerate(args[:-1]):
        if arg.lower() in ("-path", "-filepath", "-literalpath"):
            return args[i + 1]
    return next((a for a in args if not a.startswith("-")), "")


def shell_content_write_reason(tool: str, command: str, cwd: Path, env: Env) -> str | None:
    """Whether a shell command changes the contents of a project file, which must go through Edit/Write
    so the developer sees the diff. Other writes (rm, mv, git, package managers) are not reported."""
    cfg = env.config["edit_only"]
    if tool == "PowerShell":
        stripped = _QUOTED.sub(" Q ", _PS_HERESTRING.sub(" Q ", command))
        redirect, separator = _PS_REDIRECT, _PS_SEPARATOR
        if any(re.search(marker, command, re.I) for marker in cfg["powershell_write_markers"]):
            return "file write through .NET"
    else:
        stripped = _strip_literals(command)
        redirect, separator = _REDIRECT, _SEPARATOR

    for target in redirect.findall(stripped):
        if _inside_project(target, cwd, env):
            return f"output redirected into {target}"
    for segment in separator.split(stripped):
        words = _command_words(segment, env.config["bash"]["wrappers"])
        while words and words[0] in ("&", "."):  # PowerShell call operators
            words = words[1:]
        if not words:
            continue
        name, args = _program_name(words[0]), words[1:]
        if name in cfg["target_commands"] and _inside_project(_write_target(args), cwd, env):
            return f"{name} into {_write_target(args)}"
        if _has_write_flag(args, cfg["flag_writes"].get(name)):
            return f"{name} editing files in place"
        if _is_interpreter(name, env.config["bash"]["interpreters"]) and _writes_inline(command, cfg["inline_write_markers"]):
            return f"{name} code that writes a file"
    return None


# --------------------------------------------------------------------------- #
# Event handlers
# --------------------------------------------------------------------------- #

def _native_path(path: str) -> str:
    """On Windows, turn a Git Bash path (`/c/Users/x`) into `C:/Users/x`."""
    m = re.match(r"^/([A-Za-z])(/.*)?$", path)
    if os.name == "nt" and m:
        return f"{m.group(1).upper()}:{m.group(2) or '/'}"
    return path


def _is_inside(path: str, root: Path) -> bool:
    try:
        Path(_native_path(path)).expanduser().resolve().relative_to(root.resolve())
        return True
    except (ValueError, OSError):
        return False


def _mentions_path(command: str, path: Path) -> bool:
    """Whether a shell command names `path` in any spelling: native, forward slashes,
    Git Bash (`/c/...`) or WSL (`/mnt/c/...`); case-insensitive, as on Windows."""
    native = str(path)
    posix = native.replace("\\", "/")
    spellings = {native, posix}
    m = re.match(r"^([A-Za-z]):/(.*)$", posix)
    if m:
        drive, rest = m.group(1).lower(), m.group(2)
        spellings |= {f"/{drive}/{rest}", f"/mnt/{drive}/{rest}"}
    lowered = command.lower()
    return any(s.lower() in lowered for s in spellings if s)


def _context(event_name: str, text: str) -> dict:
    return {"hookSpecificOutput": {"hookEventName": event_name, "additionalContext": text}}


def _deny(reason: str) -> dict:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }


def _block(reason: str, event_name: str = "UserPromptExpansion") -> dict:
    out = {"decision": "block", "reason": reason}
    if event_name == "UserPromptExpansion":
        out["hookSpecificOutput"] = {"hookEventName": event_name}
    return out


def _tool_path(tool_input: dict) -> str:
    return tool_input.get("file_path") or tool_input.get("notebook_path") or ""


def decide_session_start(event: dict, state: SessionState | None, env: Env) -> tuple[dict, SessionState]:
    # resume/compact keep the unit in progress; a new or cleared conversation starts fresh
    if state is None or event.get("source") in ("startup", "clear"):
        state = SessionState(mode=env.default_mode)
    text = mode_rules(env, state.mode) + "\n\n" + status_line(state)
    return _context("SessionStart", text), state


def decide_user_prompt(event: dict, state: SessionState, env: Env) -> dict | None:
    # /collab:* commands get a fresh status from the expansion hook instead
    if (event.get("prompt") or "").lstrip().startswith("/collab:"):
        return None
    state.git_grant = {}  # an unused git permission does not outlive the turn it was given for
    if state.paused and state.stage in OPEN_STAGES:
        # any reply lifts the pause; whether it means "go on" or "fix this" is Claude's call
        state.paused = False
        state.stage_anchors = {}
        return _context("UserPromptSubmit", RESUMED_MESSAGE + "\n\n" + status_line(state))
    return _context("UserPromptSubmit", status_line(state))


def decide_command(event: dict, state: SessionState, env: Env) -> tuple[dict | None, list]:
    """Handle a /collab:<name> typed by the developer. Returns (output, journal entries)."""
    plugin, _, name = (event.get("command_name") or "").rpartition(":")
    if plugin != "collab":
        return None, []
    args = (event.get("command_args") or "").strip()
    min_words = env.config.get("min_agree_words", 6)

    if name in ("agree", "plan"):
        if state.stage == "off":
            return _block("collab is off in this session (/collab:off). Turn it back on with /collab:on."), []
        if len(args.split()) < min_words:
            return _block(
                f"Describe the chosen approach and why it was chosen in your own words (at least {min_words} words). "
                f"For example: /collab:{name} offset pagination with limit/offset, because the table is small and we need navigation by page number"
            ), []
        state.open_unit("agreed", args)
        note = ("The developer confirmed the approach. Check the restatement against the discussion: if it diverges from "
                "what was agreed or misses something significant, point that out briefly before writing code. ")
        if name == "plan":
            state.planned = state.paused = True  # the plan itself is the first pause: no code before the developer sees it
            note += PLAN_START_MESSAGE
        else:
            note += "Then implement, explaining decisions along the way."
        return _context("UserPromptExpansion", note + "\n\n" + status_line(state)), [(name, args)]

    if name in ("commit", "push", "git"):
        if state.stage == "off":
            return _block("collab is off in this session (/collab:off): git is not restricted, just ask Claude."), []
        words = args.split()
        if name == "git":
            if words and words[0] == "git":
                words = words[1:]
            sub = words[0] if words else ""
            if sub not in env.config.get("git_gated", []):
                gated = ", ".join(env.config.get("git_gated", []))
                return _block(f"/collab:git <command> [why]: give a git command that needs permission ({gated}). "
                              f"Other git commands ({sub or 'status, log, add…'}) need none: just ask Claude."), []
        else:
            sub = name
        state.git_grant = {"action": name, "subcommand": sub, "branch": words[0] if name == "push" and words else ""}
        note = {
            "commit": "The developer allowed one commit (/collab:commit). Follow the command's instructions.",
            "push": "The developer allowed one push (/collab:push). Follow the command's instructions.",
            "git": f"The developer allowed one `git {sub}` call (/collab:git). Follow the command's instructions.",
        }[name]
        return _context("UserPromptExpansion", note + "\n\n" + status_line(state)), [(name, args)]

    if name == "skip":
        if not args:
            return _block("Give a reason for skipping the discussion: /collab:skip <reason>"), []
        state.open_unit("skipped", args)
        return _context("UserPromptExpansion", status_line(state)), [("skip", args)]

    if name == "off":
        if not args:
            return _block("Give a reason (a couple of words is enough): /collab:off <reason>. Applies until the end of the session."), []
        state.open_unit("off", args)
        return _context("UserPromptExpansion", status_line(state)), [("off", args)]

    if name == "explain":
        if state.stage == "off":
            return _block("collab is off in this session (/collab:off). Turn it back on with /collab:on."), []
        # options only: the stage stays as is, so writes remain blocked until /collab:agree
        return _context("UserPromptExpansion", status_line(state)), [("explain", args)]

    if name == "on":
        state.open_unit("discussing")
        return _context("UserPromptExpansion", status_line(state)), [("on", "")]

    if name == "done":
        state.close_unit()
        return _context("UserPromptExpansion", "The developer closed the unit of work.\n\n" + status_line(state)), [("done", "")]

    if name == "mode":
        if args not in MODES:
            return _block(f"Mode: /collab:mode <{'|'.join(MODES)}>. Current: {state.mode}."), []
        state.mode = args
        return _context("UserPromptExpansion", mode_rules(env, args) + "\n\n" + status_line(state)), [("mode", args)]

    if name == "status":
        info = f"{status_line(state)}\nChanges in the current unit: {state.changes}; units closed this session: {state.units_closed}."
        return _context("UserPromptExpansion", info), []

    return None, []


def decide_pre_tool_use(event: dict, state: SessionState, env: Env) -> dict | None:
    tool = event.get("tool_name", "")
    tool_input = event.get("tool_input") or {}
    write_tools = env.config["write_tools"]

    # Self-approval guard applies in every stage, including off.
    if tool in write_tools and _is_inside(_tool_path(tool_input), env.data_dir):
        return _deny(SELF_PROTECT_MESSAGE)
    if tool in SHELL_TOOLS and _mentions_path(tool_input.get("command") or "", env.data_dir):
        return _deny(SELF_PROTECT_MESSAGE)

    if state.stage != "off" and tool in SHELL_TOOLS:
        denied = _git_denied(tool, tool_input.get("command") or "", state, env)
        if denied:
            return _deny(f"{GIT_MESSAGE} (detected: {denied})")
    skip_git = bool(state.git_grant)  # the developer's permission also covers staging etc. for it

    if state.stage in OPEN_STAGES and state.paused:
        if tool in write_tools and _is_inside(_tool_path(tool_input), env.project_dir):
            return _deny(PAUSED_MESSAGE)
        if tool in SHELL_TOOLS:
            reason = shell_write_reason(tool, tool_input.get("command") or "", env.config, skip_git)
            return _deny(f"{PAUSED_MESSAGE} (detected: {reason})") if reason else None
        if tool == "TaskUpdate" and tool_input.get("status") in ("in_progress", "completed"):
            return _deny(PAUSED_MESSAGE)
        return None
    if state.stage in OPEN_STAGES and tool in SHELL_TOOLS:
        cwd = Path(event.get("cwd") or env.project_dir)
        reason = shell_content_write_reason(tool, tool_input.get("command") or "", cwd, env)
        return _deny(f"{EDIT_ONLY_MESSAGE} (detected: {reason})") if reason else None
    if state.stage != "discussing":
        return None
    if tool in write_tools:
        path = _tool_path(tool_input)
        if path and not _is_inside(path, env.project_dir):
            return None  # notes, memory, scratchpad — outside the code under discussion
        return _deny(GATE_MESSAGE)
    if tool in SHELL_TOOLS:
        reason = shell_write_reason(tool, tool_input.get("command") or "", env.config, skip_git)
        if reason:
            return _deny(f"{GATE_MESSAGE} (detected: {reason})")
    return None


def _shown(path: str, env: Env) -> str:
    """A path as the developer reads it: relative to the project when it is inside."""
    try:
        return str(Path(path).resolve().relative_to(env.project_dir.resolve()))
    except ValueError:
        return path


def _explain_reminder(path: str, env: Env) -> str:
    return (
        f"collab: file {_shown(path, env)} changed. Before calling the next tool, write the developer an "
        "explanation of this change (if you have not yet): what changed in the file and why, and for each "
        "new or changed function, a card following the \"Code explanation format\" "
        "(parameters, result, the functions used and why them, \"in plain words\": 3–8 lines of pseudocode "
        "in plain language); depth per the mode. For a mechanical edit (import, rename) one sentence "
        "is enough. If you already explained it, do not repeat yourself."
    )


def _stage_done_message(state: SessionState, env: Env) -> str:
    files = ", ".join(_shown(p, env) for p in state.stage_anchors)
    what = (f"explain each file changed in it ({files}): what changed and why, and a card for each new or changed "
            "function following the \"Code explanation format\"" if files else "explain what was done in it")
    return (
        f"collab: plan stage completed. Now, in your reply to the developer, {what}. Then end your reply with a "
        "question whether to continue with the next stage. Do not start the next stage: changes and stage "
        "updates are blocked until the developer replies. If this was the last stage, give the final review instead."
    )


def decide_post_tool_use(event: dict, state: SessionState, env: Env) -> dict | None:
    """Track changes in the open unit; on the first change of each file, ask for an explanation.
    In a planned unit, a stage marked completed pauses the work until the developer replies."""
    tool = event.get("tool_name", "")
    tool_input = event.get("tool_input") or {}
    if state.git_grant and tool in SHELL_TOOLS and any(
            _grant_allows(state.git_grant, sub, args) for sub, args in _git_calls(tool, tool_input.get("command") or "", env)):
        state.git_grant = {}  # one permission, one git call — in any stage
    if state.stage not in OPEN_STAGES:
        return None
    if tool == "TaskUpdate" and state.planned and not state.paused and tool_input.get("status") == "completed":
        state.paused = True
        return {"decision": "block", "reason": _stage_done_message(state, env)}
    if tool in env.config["write_tools"]:
        path = _tool_path(tool_input)
        if path and _is_inside(path, env.project_dir) and path not in state.stage_anchors:
            state.stage_anchors[path] = event.get("tool_use_id") or ""
        if path and _is_inside(path, env.project_dir) and path not in state.changed_files:
            state.changed_files.append(path)
            state.change_anchors[path] = event.get("tool_use_id") or ""
            if state.mode in env.config.get("explain_after_write_modes", MODES):
                # "block" does not undo the write (it already happened): it attaches the reason to
                # the tool result as hook feedback, which the model treats as something to act on.
                return {"decision": "block", "reason": _explain_reminder(path, env)}
    elif tool in SHELL_TOOLS and shell_write_reason(tool, tool_input.get("command") or "", env.config):
        state.bash_writes += 1
    return None


def _ends_with_question(message: str) -> bool:
    paragraphs = [p for p in re.split(r"\n\s*\n", message.strip()) if p.strip()]
    return bool(paragraphs) and "?" in paragraphs[-1]


def _names_file(text: str, path: str) -> bool:
    return bool(re.search(rf"(?<![\w.]){re.escape(Path(path).name)}(?!\w)", text))


def _transcript_events(path: str) -> list | None:
    """Claude's texts and tool calls in the session transcript, in order: ("text", text) / ("tool", id).
    None when the transcript can't be read."""
    events = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                if '"assistant"' not in line:
                    continue
                try:
                    record = json.loads(line)
                except ValueError:
                    continue
                content = (record.get("message") or {}).get("content")
                if record.get("type") != "assistant" or not isinstance(content, list):
                    continue
                for block in content:
                    if block.get("type") == "text":
                        events.append(("text", block.get("text") or ""))
                    elif block.get("type") == "tool_use":
                        events.append(("tool", block.get("id") or ""))
    except (OSError, TypeError):
        return None
    return events


def _explained_along_the_way(events: list, anchors: dict, final_message: str, env: Env) -> set:
    """Changed files that a text of Claude's explains: at least explain_min_chars long, naming the file,
    written after the tool call before the file's first change, and not part of the final review."""
    min_chars = env.config.get("explain_min_chars", 200)
    tool_at = {value: i for i, (kind, value) in enumerate(events) if kind == "tool"}
    explained = set()
    for path, anchor in anchors.items():
        if anchor not in tool_at:
            continue
        # start after the previous call, so "now I'll change X in api.py" right before the edit counts
        start = max((j for j in range(tool_at[anchor]) if events[j][0] == "tool"), default=-1)
        if any(kind == "text" and len(text) >= min_chars and _names_file(text, path)
               and text.strip() not in final_message
               and not re.search(env.config["review_heading_pattern"], text, re.M)
               for kind, text in events[start + 1:]):
            explained.add(path)
    return explained


def _files_missing_from_section(message: str, files: list, env: Env) -> list:
    """Files without their own "#### <file>" heading under the "Explanation by file" section."""
    m = re.search(env.config["explain_section_pattern"], message, re.M)
    headings = re.findall(r"^#{3,6}\s.*$", message[m.end():], re.M) if m else []
    return [f for f in files if not any(_names_file(h, f) for h in headings)]


def _review_problems(event: dict, state: SessionState, env: Env, message: str) -> list:
    problems = []
    if not re.search(env.config["verification_heading_pattern"], message, re.M):
        problems.append(
            "collab: the final review has no \"### Verification\" section. Add it: which tests and "
            "checks were actually run and with what result, what remains unverified. "
            "If tests were not run, say so."
        )
    missing = _files_missing_from_section(message, state.changed_files, env)
    if missing:  # read the transcript only when the review itself doesn't cover every file
        events = _transcript_events(event.get("transcript_path") or "") or []
        explained = _explained_along_the_way(events, state.change_anchors, message, env)
        missing = [p for p in missing if p not in explained]
    if missing:
        problems.append(
            f"collab: these changed files were not explained along the way: {', '.join(_shown(p, env) for p in missing)}. "
            "Your replies to the developer have no explanation of them: your thinking is not shown, and code "
            "inside Write/Edit calls does not count. So don't say they were explained earlier; just explain them now. "
            "Add a \"### Explanation by file\" section to the final review with a \"#### <file>\" heading for "
            "each of them: what changed in it and why, and for each new or changed function a card following "
            "the \"Code explanation format\" (\"In plain words\" pseudocode for non-trivial logic). "
            "A mechanical edit (import, rename) needs one sentence."
        )
    return problems


def _stage_unexplained(event: dict, state: SessionState, env: Env, message: str) -> list:
    """Files changed in this stage that neither the pause message nor an earlier text of the stage explains."""
    min_chars = env.config.get("explain_min_chars", 200)
    missing = [p for p in state.stage_anchors if not (len(message) >= min_chars and _names_file(message, p))]
    if missing:
        events = _transcript_events(event.get("transcript_path") or "") or []
        explained = _explained_along_the_way(events, {p: state.stage_anchors[p] for p in missing}, "", env)
        missing = [p for p in missing if p not in explained]
    return missing


def decide_stop(event: dict, state: SessionState, env: Env) -> dict | None:
    if state.stage not in OPEN_STAGES:
        return None
    message = event.get("last_assistant_message") or ""
    retrying = bool(event.get("stop_hook_active"))

    if re.search(env.config["review_heading_pattern"], message, re.M):
        problems = [] if retrying else _review_problems(event, state, env, message)
        if problems:
            return _block("\n\n".join(problems), "Stop")
        state.close_unit()
        return {"systemMessage": "collab: unit of work closed. The next task will start with a discussion of the approach."}

    if state.planned and state.paused:  # a pause in the plan is a valid stop once the stage is explained
        missing = [] if retrying else _stage_unexplained(event, state, env, message)
        if missing:
            return _block(
                f"collab: before pausing, explain the files changed in this stage: {', '.join(_shown(p, env) for p in missing)}. "
                "For each: what changed and why, and a card for each new or changed function following the "
                "\"Code explanation format\". Only text in your reply counts: your thinking is not shown.",
                "Stop",
            )
        return None

    if state.changes == 0 or retrying or _ends_with_question(message):
        return None
    return _block(
        f"collab: {state.changes} file(s)/command(s) changed in this unit of work, but there is no final review. "
        "If the work is finished, give a \"## Final review\" per the rules (with a \"### Verification\" section). "
        "If not, continue, or end the message with a question to the developer.",
        "Stop",
    )


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #

def run(event_name: str, event: dict, env: Env) -> dict | None:
    session_id = event.get("session_id", "")
    state = load_state(env, session_id)

    if event_name == "session-start":
        out, state = decide_session_start(event, state, env)
        save_state(env, session_id, state)
        return out

    if state is None:  # plugin enabled mid-session: start from defaults
        state = SessionState(mode=env.default_mode)

    if event_name == "user-prompt-submit":
        out = decide_user_prompt(event, state, env)
    elif event_name == "user-prompt-expansion":
        out, journal = decide_command(event, state, env)
        for kind, detail in journal:
            append_journal(env, session_id, kind, detail)
    elif event_name == "pre-tool-use":
        return decide_pre_tool_use(event, state, env)  # read-only: no save
    elif event_name == "post-tool-use":
        out = decide_post_tool_use(event, state, env)
    elif event_name == "stop":
        out = decide_stop(event, state, env)
    else:
        raise ValueError(f"unknown event {event_name!r}")

    save_state(env, session_id, state)
    return out


def main(argv: list) -> int:
    event_name = argv[1] if len(argv) > 1 else ""
    # Windows defaults stdio to a legacy code page (cp1251/cp1252): read and write UTF-8 explicitly.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    try:
        raw = sys.stdin.buffer.read() if hasattr(sys.stdin, "buffer") else sys.stdin.read().encode("utf-8")
        event = json.loads(raw.decode("utf-8", errors="replace") or "{}")
    except ValueError:
        event = {}
    try:
        env = env_from_os(event)
        out = run(event_name, event, env)
        if os.environ.get("COLLAB_DEBUG") == "1":
            with open(env.data_dir / "debug.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps({"event": event_name, "input": event, "output": out}, ensure_ascii=False) + "\n")
    except Exception as exc:  # noqa: BLE001 — a hook must answer, whatever broke
        if event_name == "pre-tool-use":
            # The gate fails closed: a bug must not silently open writes.
            out = _deny(f"collab: internal hook error ({exc}); writing is blocked. "
                        "Tell the developer: it can be bypassed by disabling the plugin (/plugin).")
        else:
            print(f"collab hook error ({event_name}): {exc}", file=sys.stderr)
            return 1
    if out:
        # ASCII-escaped JSON survives any console encoding; Claude Code decodes the \u escapes
        print(json.dumps(out, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
