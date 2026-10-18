# Changing the plugin's rules

Almost all behavior is defined by text and config. Before making a change, identify **which layer** you are changing:

| I want to change… | Layer | File |
|---|---|---|
| How Claude runs the dialogue: stages, questions, analysis, review format | 💬 rules | `plugins/collab/output-styles/collab.md` |
| How modes differ | 💬 rules | `plugins/collab/modes/<mode>.md` |
| What Claude does after a command | 💬 rules | `plugins/collab/skills/<command>/SKILL.md` |
| What counts as a write (`bash` and `powershell` sections), restatement length, review headings | 🔒 gate parameters | `plugins/collab/config/gate.json` |
| Stage and blocking logic | 🔒 code | `plugins/collab/scripts/collab_gate.py` + `tests/` |
| Which events the plugin reacts to | 🔒 wiring | `plugins/collab/hooks/hooks.json` |

## Workflow

1. Make the change.
2. Locally: `claude --plugin-dir ./plugins/collab` (in an open session, `/reload-plugins`) and try it on a real task.
3. If you changed `gate.json` or code: `python3 -m unittest discover -s plugins/collab/tests -v`.
4. If you changed rules, run the affected scenarios, for example
   `cd plugins/collab && claude plugin eval . --case '03-*' --scaffold --allow-tools Write Edit --trust-plugin`.
5. Bump `version` in `plugins/collab/.claude-plugin/plugin.json` — **without this, the team's installed copies won't update.**
6. Commit; developers get the update via `/plugin` (or automatically, if marketplace auto-update is enabled).

## Examples

### Require a longer restatement in `/collab:agree`

`config/gate.json`:
```json
"min_agree_words": 10
```

### Configure the "explain the change in plain words" reminder

After the first change to each file, Claude gets a reminder to explain it and give pseudocode. The modes where it applies are in `config/gate.json`:
```json
"explain_after_write_modes": ["learning", "collaborative"]
```
An empty list `[]` turns the reminder off (the rule in the output style remains). The reminder text is the `_explain_reminder` function in `scripts/collab_gate.py`; what "In plain words" looks like is described in the "Stage 6" section of `output-styles/collab.md`.

### Add a command that should count as a write

For example, `alembic upgrade` changes the DB schema — block it until agreement:
```json
"subcommand_writes": {
  "alembic": ["upgrade", "downgrade", "revision"],
  ...
}
```
Add a test in `tests/test_collab_gate.py` (`BashWriteDetection.WRITES`).

### Allow a safe command that triggers the heuristic

If, for example, your `make lint` doesn't need to be in the list, just don't add `make`. If a false positive comes from a redirection (`cmd > /tmp/x`), add the target to `safe_redirect_targets` or describe the case in an issue: the heuristic is better refined with a test.

### Block writes through an MCP tool

`gate.json` → `"write_tools": [..., "mcp__plugin_fs_files__write_file"]`, plus the same tool in the `matcher` for `PreToolUse` and `PostToolUse` in `hooks/hooks.json`.

### Change the final review format

Edit the "Stage 7" section in `output-styles/collab.md`. **Don't change the headings** `## Final review` and `### Verification`, or change `review_heading_pattern` / `verification_heading_pattern` in `gate.json` along with them — the hook uses them to close the unit of work.

### Add your own mode

1. `modes/strict.md` — describe the differences.
2. `plugin.json` → `userConfig.default_mode.options` — add `"strict"`.
3. `scripts/collab_gate.py` → `MODES = (..., "strict")`.
4. `skills/mode/SKILL.md` → `argument-hint`.
5. A test in `Commands.test_mode_switch_injects_mode_rules`.

### Translate the rules into another language

The rules are plain Markdown; Claude follows them in any language and replies in the developer's language. When translating, keep the meaning of the review headings or add translations to the patterns in `gate.json`. The patterns already accept English, Russian and Ukrainian: `Final review|Итоговый разбор|Підсумковий розбір` and `Verification|Проверка|Перевірка`.

## What not to do

- Don't weaken the gate for the convenience of one scenario — that's what `/collab:skip` and `/collab:off` are for.
- Don't add long reference material to the output style: it's sent with every request and consumes context.
- Don't store state inside `${CLAUDE_PLUGIN_ROOT}` — this directory is replaced on plugin update.
