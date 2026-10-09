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
    "collab: запись в проект заблокирована — подход для этой единицы работы ещё не "
    "согласован. Продолжи обсуждение: подход разработчика → его причины → анализ → "
    "альтернативы → совместный выбор. Запись откроется, когда разработчик сам выполнит "
    "/collab:agree <подход своими словами>, или /collab:skip <причина>, или /collab:off "
    "<причина>. Не пытайся обойти блокировку другим способом."
)
SELF_PROTECT_MESSAGE = (
    "collab: файлы состояния плагина может менять только разработчик через команды "
    "/collab:*. Не изменяй их."
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
    bash_writes: int = 0
    units_closed: int = 0

    @property
    def changes(self) -> int:
        return len(self.changed_files) + self.bash_writes

    def open_unit(self, stage: str, agreement: str = "") -> None:
        self.stage = stage
        self.agreement = agreement
        self.changed_files = []
        self.bash_writes = 0

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
            f"[collab] режим={state.mode} стадия=off — плагин выключен разработчиком до конца "
            "сессии. Работай как обычный Claude Code; правила совместной разработки не применяются."
        )
    gate = "запись заблокирована до /collab:agree" if state.stage == "discussing" else "запись разрешена"
    line = f"[collab] режим={state.mode} стадия={state.stage} ({gate})"
    if state.stage == "agreed":
        line += f"\nСогласовано разработчиком: «{state.agreement}»"
    if state.stage == "skipped":
        line += f"\nОбсуждение пропущено по просьбе разработчика: «{state.agreement}». Объяснения по ходу и итоговый разбор обязательны."
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


def bash_write_reason(command: str, config: dict) -> str | None:
    """Return a short description of why the command looks like a write, or None."""
    cfg = config["bash"]
    stripped = _strip_literals(command)

    for target in _REDIRECT.findall(stripped):
        if target not in cfg["safe_redirect_targets"]:
            return f"перенаправление вывода в файл ({target})"

    for segment in _SEPARATOR.split(stripped):
        reason = _segment_write_reason(_command_words(segment, cfg["wrappers"]), command, cfg)
        if reason:
            return reason
    return None


def _segment_write_reason(words: list, raw_command: str, cfg: dict) -> str | None:
    """Check one simple command (program + args) against the bash config lists."""
    if not words:
        return None
    name = _program_name(words[0])
    args = words[1:]
    if name in cfg["write_commands"]:
        return f"команда {name}"
    flags = cfg["flag_writes"].get(name)
    if flags and any(a in flags or ("-i" in flags and re.fullmatch(r"-[a-zA-Z]*i[a-zA-Z]*", a)) for a in args):
        return f"{name} с изменением файлов"
    subs = cfg["subcommand_writes"].get(name)
    if subs:
        sub = _subcommand(args)
        if sub in subs:
            return f"{name} {sub}"
    if name in cfg["interpreters"] or re.match(r"python3(\.\d+)?$", name) or name == "py":
        # the code itself sits in quotes/heredoc, so search the raw command
        for marker in cfg["inline_write_markers"]:
            if re.search(marker, raw_command):
                return f"код {name} с признаками записи в файл"
    return None


_PS_HERESTRING = re.compile(r"@(['\"])\r?\n.*?\r?\n\1@", re.S)
_PS_SEPARATOR = re.compile(r"\|\||&&|[;|\n(){}]")
_PS_REDIRECT = re.compile(r"(?:\d|\*)?>>?(?!&)\s*([^\s;|<>()]+)")


def powershell_write_reason(command: str, config: dict) -> str | None:
    """PowerShell flavour of bash_write_reason: cmdlets, aliases, .NET file APIs, redirects."""
    ps = config["powershell"]
    stripped = _QUOTED.sub(" Q ", _PS_HERESTRING.sub(" Q ", command))

    for target in _PS_REDIRECT.findall(stripped):
        if target.lower() not in ps["safe_redirect_targets"]:
            return f"перенаправление вывода в файл ({target})"
    for marker in ps["dotnet_write_markers"]:
        if re.search(marker, command, re.I):
            return "запись файла через .NET"

    for segment in _PS_SEPARATOR.split(stripped):
        words = segment.split()
        while words and words[0] in ("&", "."):  # call operators
            words = words[1:]
        if not words:
            continue
        name = _program_name(words[0])
        args = [a.lower() for a in words[1:]]
        if name in ps["write_commands"]:
            return f"команда {name}"
        flags = ps["flag_writes"].get(name)
        if flags and any(a in flags for a in args):
            return f"{name} с записью в файл"
        # external programs (git, npm, python …) follow the bash rules
        reason = _segment_write_reason(words, command, config["bash"])
        if reason:
            return reason
    return None


def shell_write_reason(tool: str, command: str, config: dict) -> str | None:
    if tool == "PowerShell":
        return powershell_write_reason(command, config)
    return bash_write_reason(command, config)


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
    return _context("UserPromptSubmit", status_line(state))


def decide_command(event: dict, state: SessionState, env: Env) -> tuple[dict | None, list]:
    """Handle a /collab:<name> typed by the developer. Returns (output, journal entries)."""
    plugin, _, name = (event.get("command_name") or "").rpartition(":")
    if plugin != "collab":
        return None, []
    args = (event.get("command_args") or "").strip()
    min_words = env.config.get("min_agree_words", 6)

    if name == "agree":
        if state.stage == "off":
            return _block("collab выключен в этой сессии (/collab:off). Включите его командой /collab:on."), []
        if len(args.split()) < min_words:
            return _block(
                f"Опишите своими словами выбранный подход и почему он выбран (не меньше {min_words} слов). "
                "Например: /collab:agree offset-пагинация с limit/offset, потому что таблица маленькая и нужна навигация по номерам страниц"
            ), []
        state.open_unit("agreed", args)
        note = ("Разработчик подтвердил подход. Сверь пересказ с обсуждением: если он расходится с договорённостью "
                "или упускает существенное — коротко укажи на это, прежде чем писать код. Затем реализуй, "
                "объясняя решения по ходу.")
        return _context("UserPromptExpansion", note + "\n\n" + status_line(state)), [("agree", args)]

    if name == "skip":
        if not args:
            return _block("Укажите причину пропуска обсуждения: /collab:skip <причина>"), []
        state.open_unit("skipped", args)
        return _context("UserPromptExpansion", status_line(state)), [("skip", args)]

    if name == "off":
        if not args:
            return _block("Укажите причину (достаточно пары слов): /collab:off <причина>. Действует до конца сессии."), []
        state.open_unit("off", args)
        return _context("UserPromptExpansion", status_line(state)), [("off", args)]

    if name == "on":
        state.open_unit("discussing")
        return _context("UserPromptExpansion", status_line(state)), [("on", "")]

    if name == "done":
        state.close_unit()
        return _context("UserPromptExpansion", "Единица работы закрыта разработчиком.\n\n" + status_line(state)), [("done", "")]

    if name == "mode":
        if args not in MODES:
            return _block(f"Режим: /collab:mode <{'|'.join(MODES)}>. Сейчас: {state.mode}."), []
        state.mode = args
        return _context("UserPromptExpansion", mode_rules(env, args) + "\n\n" + status_line(state)), [("mode", args)]

    if name == "status":
        info = f"{status_line(state)}\nИзменений в текущей единице: {state.changes}; закрыто единиц за сессию: {state.units_closed}."
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

    if state.stage != "discussing":
        return None
    if tool in write_tools:
        path = _tool_path(tool_input)
        if path and not _is_inside(path, env.project_dir):
            return None  # notes, memory, scratchpad — outside the code under discussion
        return _deny(GATE_MESSAGE)
    if tool in SHELL_TOOLS:
        reason = shell_write_reason(tool, tool_input.get("command") or "", env.config)
        if reason:
            return _deny(f"{GATE_MESSAGE} (обнаружено: {reason})")
    return None


def _explain_reminder(path: str, env: Env) -> str:
    try:
        shown = str(Path(path).resolve().relative_to(env.project_dir.resolve()))
    except ValueError:
        shown = path
    return (
        f"collab: изменён файл {shown}. Прежде чем вызывать следующий инструмент, напиши разработчику "
        "объяснение этого изменения (если ещё не написал): что изменилось в файле и зачем, и для каждой "
        "новой или изменённой функции — карточка по «Формату объяснения кода» "
        "(параметры, результат, используемые функции и почему они, «на пальцах» — псевдокод 3–8 строк "
        "простыми словами); глубина — по режиму. Для механической правки (импорт, переименование) хватит "
        "одной фразы. Если уже объяснил — не повторяй."
    )


def decide_post_tool_use(event: dict, state: SessionState, env: Env) -> dict | None:
    """Track changes in the open unit; on the first change of each file, ask for an explanation."""
    if state.stage not in OPEN_STAGES:
        return None
    tool = event.get("tool_name", "")
    tool_input = event.get("tool_input") or {}
    if tool in env.config["write_tools"]:
        path = _tool_path(tool_input)
        if path and _is_inside(path, env.project_dir) and path not in state.changed_files:
            state.changed_files.append(path)
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


def decide_stop(event: dict, state: SessionState, env: Env) -> dict | None:
    if state.stage not in OPEN_STAGES:
        return None
    message = event.get("last_assistant_message") or ""
    retrying = bool(event.get("stop_hook_active"))

    if re.search(env.config["review_heading_pattern"], message, re.M):
        if not retrying and not re.search(env.config["verification_heading_pattern"], message, re.M):
            return _block(
                "collab: в итоговом разборе нет раздела «### Проверка». Допиши его: какие тесты и "
                "проверки реально запускались и с каким результатом, что осталось непроверенным. "
                "Если тесты не запускались — так и напиши.",
                "Stop",
            )
        state.close_unit()
        return {"systemMessage": "collab: единица работы закрыта. Следующая задача начнётся с обсуждения подхода."}

    if state.changes == 0 or retrying or _ends_with_question(message):
        return None
    return _block(
        f"collab: в этой единице работы изменено файлов/команд: {state.changes}, но нет итогового разбора. "
        "Если работа завершена — дай «## Итоговый разбор» по правилам (с разделом «### Проверка»). "
        "Если не завершена — продолжай или закончи сообщение вопросом к разработчику.",
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
            out = _deny(f"collab: внутренняя ошибка хука ({exc}); запись заблокирована. "
                        "Сообщи разработчику — обойти можно, отключив плагин (/plugin).")
        else:
            print(f"collab hook error ({event_name}): {exc}", file=sys.stderr)
            return 1
    if out:
        # ASCII-escaped JSON survives any console encoding; Claude Code decodes the \u escapes
        print(json.dumps(out, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
