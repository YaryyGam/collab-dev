# Architecture

## 1. The problem the architecture solves

Before any code change, Claude Code must go through a cycle with the developer: "developer's approach → their reasons → analysis of the solution and reasoning → alternatives → joint choice → implementation with explanations → final review". At the same time:

- the mandatory part (no code before agreement) must not depend on whether the model "obeys";
- the plugin must be reusable across projects and stacks without reconfiguration;
- rules must be changed by editing text, not code;
- there must be an honest way back to the classic mode.

## 2. Claude Code mechanisms considered

| Mechanism | What it does | Enforces or influences | Role in the plugin |
|---|---|---|---|
| **Output style** (`force-for-plugin`) | Instructions sent with every request; enabled automatically with the plugin | 💬 Influences. The docs say explicitly: the style is not enforced | **Core process rules** |
| **Skills** (`/plugin:skill`) | Instructions loaded on invocation; `disable-model-invocation` forbids the model from invoking them | 💬 Influences (text) / 🔒 enforces who may invoke | `/collab:*` commands |
| **Hook `PreToolUse`** | Before a tool call; `permissionDecision: deny` cancels the call in any permission mode | 🔒 Enforces | Blocking writes until agreement, protecting state files |
| **Hook `UserPromptExpansion`** | Fires only when **a human typed** a slash command; can reject it | 🔒 Enforces | Accepting agreement and switches — the trust boundary |
| **Hook `UserPromptSubmit`** | Before each message; adds context. Also fires on subagent reports and messages from other sessions | 💬 Influences (context) | Status line in every message |
| **Hook `SessionStart`** | Session start/resume/compaction; adds context | 💬 Influences | Mode rules, state initialization |
| **Hook `PostToolUse`** | After a tool; `decision: block` attaches a note to the result (does not cancel the write — it has already happened) | 💬 Influences (the reminder fires deterministically; the response to it is up to the model). The `block` channel was chosen over `additionalContext`: in testing, Claude ignored the reminder delivered via `additionalContext` | Change tracking; after the first change to a file — a reminder to explain it with "In plain words" pseudocode |
| **Hook `Stop`** | Before the response ends; `decision: block` forces continuation (limit: 8 in a row) | 🔒 Enforces *that it continues*; not the content | Requiring a final review with "Verification" |
| Prompt/agent hooks | A judge model makes the decision | 💬 Probabilistic, adds latency and cost | **Not used** (see §4) |
| CLAUDE.md in a plugin | Not loaded from plugins | — | Not applicable |
| `userConfig` | Typed plugin settings, a choice list in `/config` | — | Default mode |
| `claude plugin eval` | Isolated `claude -p` runs, with/without plugin comparison, graders | Measures | Testing the 12 scenarios |

## 3. Chosen architecture: "soft rules + hard gate"

```
                         ┌───────────────────────────────────────────────┐
                         │   output-styles/collab.md   (every request)   │  💬 HOW to run the dialogue
                         │   modes/<mode>.md           (SessionStart,    │
                         │                              /collab:mode)    │
                         └───────────────────────────────────────────────┘
 developer                                     │
     │  regular message ──► UserPromptSubmit ──► "[collab] mode=… stage=…" into context
     │                                                                         │
     │  /collab:agree … ───► UserPromptExpansion ──► validate arguments ──► sessions/<id>.json
     │  /collab:explain|skip|off|on|done|mode          (block on error)            ▲    │
     │                                                                             │    │
 Claude ── Write/Edit/Bash ──► PreToolUse ──► stage discussing? ──► deny ──────────┘    │
                                         └──► state files? ──► deny (always)            │
        ── after write ─────► PostToolUse ──► +1 change; new file? ──► "explain + pseudocode"
        ── end of response ─► Stop ──► changes without review? ──► block "write the review"
                                  └──► has "Final review" + "Verification" ──► close unit
```

**Separation principle:** anything that can be checked mechanically (step order, who gave agreement, presence of a review) is checked by code. Anything that needs judgment (quality of analysis, relevance of questions, depth of explanations) is set by the rules text and measured by eval scenarios.

### State

`${CLAUDE_PLUGIN_DATA}/sessions/<session_id>.json` — mode, stage (`discussing | agreed | skipped | off`), agreement text, changed files, count of closed units. One file per session: parallel sessions don't interfere; `CLAUDE_PLUGIN_DATA` survives plugin updates. Writes are atomic (`os.replace`).

`${CLAUDE_PLUGIN_DATA}/journal.jsonl` — a local log of switches (`agree/skip/off/on/done/mode`). Never sent anywhere.

### Trust boundary: why agreement can't be forged "from inside"

1. Only the `UserPromptExpansion` hook changes the stage, and it fires only on a command **typed by a human** (not on the model calling the Skill tool, and not on subagent messages).
2. The `/collab:*` skills are marked `disable-model-invocation: true` — Claude can't invoke them.
3. In every stage, `PreToolUse` forbids Write/Edit on paths inside `CLAUDE_PLUGIN_DATA` and Bash commands that mention that path.

The residual risk is a Bash command that writes to the state file without naming the path explicitly (e.g. via variables). It is covered only by a rule in the output style ("don't bypass the block"); see [LIMITATIONS.md](LIMITATIONS.md).

### Fault tolerance

- Script error in `PreToolUse` → **deny** (fail closed): a bug must not silently open writes.
- Error in other events → non-blocking error, work continues (fail open): broken tracking must not stop the developer.
- Unreadable state file → default state (`discussing`), i.e. closed again.

### Code: `scripts/collab_gate.py`

One module, invoked with the event name. Handlers are pure functions `decide_*(event, state, env)` that don't touch disk or stdout, so they are tested directly. `main()` → `run()` handle I/O and state.

| Element | Responsibility |
|---|---|
| `Env` (dataclass) | Where we run: data directory, project root, config, default mode. Tests substitute a temporary one |
| `SessionState` (dataclass) | Session state; `open_unit()` / `close_unit()` are the only transitions between units of work |
| `powershell_write_reason()` / `shell_write_reason()` | The same for PowerShell: cmdlets and their aliases, `-OutFile`, .NET write methods, redirections; `shell_write_reason` picks the heuristic by tool name |
| `bash_write_reason()` | Heuristic for "does this Bash command look like a write": strips heredocs and quoted strings, splits on `; && \|`, checks redirections, commands, flags, subcommands, inline interpreter code. All lists live in `config/gate.json` |
| `decide_session_start` | New state for `startup/clear`, kept for `resume/compact`; mode context |
| `decide_user_prompt` | Status line (except for `/collab:*`, whose status comes from `decide_command`) |
| `decide_command` | Parsing `/collab:*`: argument validation, stage change, journal entries |
| `decide_pre_tool_use` | State protection + write gate |
| `decide_post_tool_use` | Change tracking in the open unit; on the first change to a file — a reminder to explain it "In plain words" (modes: `explain_after_write_modes` in `gate.json`) |
| `decide_stop` | Requiring the final review, closing the unit |

**Why Python and the standard library:** readable code for the team, built-in `json`/`re`/`unittest`, no dependencies or installation. The `bash + jq` alternative is shorter but harder to read and test, and `jq` isn't available everywhere.

**Launching via `scripts/run_hook.sh`:** the interpreter has different names (`python3` on macOS/Linux, `python` or `py -3` on Windows, where `python3` may be a Microsoft Store shortcut). The wrapper checks the candidates once (`python -c` with a version check ≥ 3.9) and caches the found command in `${CLAUDE_PLUGIN_DATA}/python-command`; after that it only runs `command -v`, with no extra Python launch. No Python → writes are denied for `PreToolUse` (fail closed). The cost: Windows needs Git Bash, since Claude Code runs shell hooks through it.

**Windows:** `PowerShell` is the second shell tool (`SHELL_TOOLS`), with its own heuristic `powershell_write_reason` (the `powershell` section in `gate.json`); stdin/stdout are explicitly UTF-8, JSON output is ASCII-escaped; paths are normalized (`_native_path`, `_mentions_path`).

**Why one script instead of six:** all events share state, config and response format; one module avoids duplicating them.

## 4. Options considered and rejected

| Option | Why rejected |
|---|---|
| **A. Instructions only** (output style / skill / CLAUDE.md) | Fails the main requirement "nothing gets written before agreement": under pressure ("just write the code") the model sometimes writes right away. Instructions remain, but as a quality layer, not a control layer |
| **C. Gate + LLM judge** (prompt/agent hooks judge "was it a real discussion") | The judge makes mistakes itself → false blocks annoy the team; latency and cost on every message; the developer is the best judge of discussion quality. Instead of a judge — a restatement in their own words in `/collab:agree` |
| **Agreement by keyword** ("agreed") | Within a week it becomes a reflexive "ok". A restatement of ≥ 6 words turns entering implementation into a comprehension exercise |
| **Unit-of-work boundary by file paths** (`/collab:agree` lists allowed files) | More reliable, but gets in the way in practice: you can't predict up front that a test or config will need a fix. Chosen instead: a boundary "at the final review" + a rule about unrelated tasks |
| **Explanations only as a rule in text** | Testing showed the model ignored the "explain before writing" rule twice (manual run and eval scenario 06): it wrote several files silently and explained everything only in the final review |
| **"Explain first": reject the first write to each file until Claude writes an explanation** | The only option that guarantees text *before* the change, but: an extra round-trip per file, a "blocked by hook" line in the terminal, and it fires even when Claude has already explained (the hook can't see the response text). The developer chose a smoother option: a post-write reminder + "In plain words" pseudocode |
| **Off switch across sessions** | Developers who need the plugin most would stay in classic mode forever. Chosen: only until end of session, with a reason |
| **Inject mode rules into every message** | The text piles up in context and wastes tokens. The mode is delivered at start/compaction/switch; the status as a short line |
| **Rules in SessionStart context instead of an output style** | Then `/collab:off` could "remove" them only for new sessions, and after compaction the rules would have to be re-delivered; an output style also has a stronger position in the system prompt. An output style with `keep-coding-instructions: true` adds the process without removing Claude Code's standard engineering instructions |

## 5. Reusability

- Nothing is tied to a stack: the rules say "study the project's structure, stack and conventions", and the example constructs (generators, DI, ORM) are only guides for explanation depth.
- Distribution is a git marketplace repository; enabling it in a project takes two lines in `.claude/settings.json`.
- Developer settings (`default_mode`) are stored with the developer, not in the project.
