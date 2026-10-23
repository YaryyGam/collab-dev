# Known limitations

An honest list of what the plugin does **not** guarantee. Mechanisms fall into two groups:

- 🔒 **enforce** — Claude Code itself executes the hook's decision; the model can't bypass it through normal means;
- 💬 **influence** — rules text that makes the desired behavior more likely but doesn't guarantee it.

## Hard write gate

| # | Limitation | Consequence | What was done / what you can do |
|---|---|---|---|
| 1 | Writes via Bash are detected by a **heuristic** | Missed: `python script.py` / `make` / `npm run x` when the script writes files itself; `>\|`; writes via variables (`$CMD > f` is caught, `eval "$X"` is not). False positives: an unquoted `>` inside an argument, writing to `/tmp` via `mkdir`/`cp` in the `discussing` stage | Command and marker lists live in `config/gate.json`. A rule in the output style forbids bypassing the block. The full solution is banning Bash entirely until agreement (not chosen: Claude couldn't run tests or `git diff` during the discussion) |
| 2 | The gate only watches the `Write`, `Edit`, `MultiEdit`, `NotebookEdit`, `Bash`, `PowerShell` tools | Writes via MCP tools (e.g. a filesystem MCP server) are not blocked | Add the tool names to `write_tools` in `gate.json` and to the matcher in `hooks/hooks.json` |
| 3 | "Inside the project" = inside `CLAUDE_PROJECT_DIR` | If Claude Code is started from the home directory, all of `~` counts as the "project" | Start Claude Code from the project root |
| 4 | State-file protection looks for the data directory path in the Bash command text | A command that builds the path dynamically won't be detected | Residual risk; covered only by the "don't bypass the block" rule |
| 5 | A script error in `PreToolUse` closes writes | If Python or the script is broken, all writes are blocked | A deliberate choice (fail closed). Way out: disable the plugin in `/plugin`. If Python 3.9+ isn't found, `run_hook.sh` also blocks writes. If `sh` itself doesn't start (Windows without Git Bash), Claude Code treats it as a non-blocking error → writes are **open** |
| 6 | Hooks run with `disableAllHooks`, or in organizations with `allowManagedHooksOnly` | The plugin becomes a set of instructions with no gate | For mandatory use in an organization, enable the plugin via the managed settings `enabledPlugins` |

## Agreement and the unit of work

| # | Limitation | Consequence |
|---|---|---|
| 7 | `/collab:agree` checks the **length** of the restatement (≥ 6 words), not its meaning | You can write nonsense. Per the rules, Claude compares the restatement with the discussion and points out discrepancies — but that is 💬 |
| 8 | The semantic unit-of-work boundary ("this is a different task now") is decided by the model | While a unit is open, Claude may start an unrelated task without a new agreement if it doesn't notice the topic change. The only hard boundaries are the final review and `/collab:done` |
| 9 | `Stop` tells a pause from completion by a heuristic: "the last paragraph contains `?`" | A status-report message without a question mid-work is sent back with "check the agreement point by point; continue, ask, or give the review only if everything is done" — Claude may still review early (seen in a real session: two of three agreed tests). The unit then closes; the plugin tells the developer and `/collab:resume` reopens it with the same agreement. A rhetorical question at the end lets it finish without a review |
| 9a | The review is recognized by its heading: `## Final review` (Claude is told to write it in English in any conversation) or the Russian/Ukrainian variants `Итоговый разбор/обзор`, `Підсумковий розбір/огляд`. A looser heading (`## Підсумок`, `## Итог`) does not close the unit — deliberately, so a casual summary mid-work doesn't close it — and Claude is sent back with the exact heading |
| 10 | `Stop` blocks no more than once in a row (`stop_hook_active`) | If Claude still doesn't give a review after being sent back, the response ends without one. This avoids looping the session |
| 11 | The presence of the "Final review" and "Verification" sections is checked by headings | Section content (honesty about tests, completeness) is 💬. Headings are accepted in English, Russian and Ukrainian (`Final review\|Итоговый разбор\|Підсумковий розбір`, `Verification\|Проверка\|Перевірка`); the patterns are in `gate.json` |
| 12 | `UserPromptExpansion` with a name matcher isn't used — the script filters `collab:*` itself | The script is invoked on every slash command (tens of milliseconds) |

## Model behavior (💬)

| # | Limitation |
|---|---|
| 13 | All dialogue stages — asking for the developer's approach, asking for reasons, assessing the reasoning, alternatives, explanations **before** writing, adapting to the developer's level, proportionality — are set by the output style text. The model may drift, especially in long sessions after compaction (mode rules are re-delivered on compaction; the output style itself stays in the system prompt) |
| 14 | Explanations during implementation rely on a reminder **after** the first change to each file (the `PostToolUse` hook). This means: (a) the explanation comes after the change, not before it — the developer can influence a specific edit beforehand only by stopping Claude themselves (Esc); (b) Claude often writes several files in one batch (sequentially or via parallel calls) — the reminder arrives after the batch, and the explanation appears after it, usually only for the last file; (c) the content of explanations, cards and pseudocode is 💬: Claude sometimes skips "In plain words" for simple functions. Measured: before the reminder was introduced, Claude wrote files silently in two tests and explained everything only in the final review; with the reminder (`PostToolUse` → `decision: block`) and the card format, explanations during implementation appeared in 4 of 4 runs, but one per file before each file in only 1 of 4. If you need a guarantee of "an explanation before every file", use the "explain first" option (reject the first write to a file); see ARCHITECTURE §4. A later bench (Opus 5.5, 20 runs over a 3-file and a 7-file task) explained only 2 of 16 files along the way with the reminder; rewording it ("only reply text counts, your thinking isn't shown") changed nothing; rejecting the move to the next file raised it to about half but costs visible hook errors and blocks parallel edits. Hence the `Stop` check below (#14a) |
| 14a | The `Stop` check of "Explanation by file" is heuristic on both sides. A file counts as explained along the way if a text of Claude's of at least `explain_min_chars` (200) characters names the file (by its base name) after the tool call preceding its first change — a long text that merely mentions `api.py` counts. In the review, only a `#### …` heading naming the file under the section is checked, not what is written under it. Files are matched by base name, so two changed `__init__.py` are covered by one heading. If the transcript can't be read, every changed file needs a heading. Like the "Verification" check, it sends Claude back at most once |
| 14c | `/collab:plan` pauses on `TaskUpdate → completed`. Claude decides when to mark a stage completed: if it keeps working without marking stages, there is no pause, and only the final-review check (#14a) applies. Any developer message lifts the pause; whether it means "go on" or "fix this" is Claude's judgment, so after answering a question it may start the next stage in the same reply (the pause after that stage still holds). The task tools (`TaskCreate`/`TaskUpdate`) must be available: in an environment that only has the older `TodoWrite`, the plan is never paused. A file's explanation at a pause is recognised as in #14a (a text of 200+ characters naming it) |
| 14d | The git gate parses commands like the write gate (#1): git run from a script, a Makefile, a git alias (`git ci`), another tool (`gh pr merge`, an IDE's commit button) or a hook is not seen; `git pull` (which may merge) is not gated. "Current branch" for `/collab:push` without a branch means a push without a refspec or with `HEAD` — `git push origin main` is rejected even when `main` is current, and Claude is told to use `HEAD`. While a permission is active, other git calls (`add`, `checkout`, `stash`) also pass the discussion gate |
| 14e | `/collab:review` is only as good as the model behind the reviewer agent: it can miss bugs or report false ones (it is told to confirm each finding and mark guesses as "suspicion"). Its Bash is limited to reading and tests **by instruction only**: in `agreed`/`skipped` the plugin's write gate doesn't stop it, and running tests may leave caches (`__pycache__`). It finds the test command by convention (README, package.json, pyproject, Makefile, CI); otherwise it reports "tests were not run". `/collab:review` without arguments reviews the whole project: on a large project it reads selectively, says which parts it only skimmed, and costs noticeably more than `diff` (a diff review of a small repo cost ≈ $0.3–0.4). Each run costs a separate agent session. Reviewer notes are honoured by instruction: the reviewer may still mention a covered point, or skip too much under a broadly worded note; it lists what it skipped and flags notes that contradict the code, but a stale note (e.g. "no production DB" after launch) keeps suppressing findings until you delete it from `.collab/reviewer-notes.md` |
| 14b | "Contents only through Edit/Write" relies on the same shell parsing as the write gate (#1): a script file that writes on its own (`python gen.py`), a formatter rewriting files, `cp`/`mv` over a file and writes through variables (`> $OUT`) pass; any Python/Node one-liner with a write marker is rejected even if it writes to `/tmp` (use `Write` there). Files changed by the shell are not in the "Explanation by file" list |
| 15 | `/collab:off` disables the gate and the process, but the output style text stays in context — the model is told to ignore it. For 100% classic behavior, disable the plugin |
| 16 | Other plugins and the project's CLAUDE.md also influence the model. Conflicting instructions (e.g. "always implement right away") will weaken the process |

## Testing

| # | Limitation |
|---|---|
| 17 | `claude plugin eval` sends a single message. Multi-turn scenarios (the developer has already proposed a solution) are modeled as one "task + solution + reason" message; implementation scenarios start directly with `/collab:agree`, with no prior discussion |
| 18 | LLM graders are non-deterministic; a statistically meaningful result needs ≥ 3 runs per scenario (the default). Results in [ACCEPTANCE.md](ACCEPTANCE.md) are from 1 run — a signal, not proof |
| 19 | Eval runs are isolated from the developer's personal plugins; in a real session other plugins may change behavior |

## Platforms

| # | Limitation |
|---|---|
| 20 | **Native Windows is supported since version 0.2.0 but has not been tested on real Windows.** What was done: `run_hook.sh` finds `python3` / `python` / `py -3` and filters out the Microsoft Store shortcut; UTF-8 I/O (the Windows console defaults to cp1251/cp1252); control of the `PowerShell` tool (cmdlets, their aliases, `-OutFile`, `[IO.File]::Write…`, redirections); paths `C:\…`, `C:/…`, `/c/…`, `/mnt/c/…` and letter case |
| 20a | Hooks use the shell form via `sh`: on Windows they're run by Git Bash. **Without Git for Windows**, Claude Code runs hooks through PowerShell, `run_hook.sh` doesn't start, and the gate is **open** (see #5) |
| 20b | The found interpreter is cached in `${CLAUDE_PLUGIN_DATA}/python-command`. If you remove it or update Python so the command disappears, the cache is rechecked on the next call; if the command remains but now points to a Python version below 3.9, delete this file |
| 20c | The PowerShell heuristic, like the Bash one, doesn't see writes inside invoked scripts (`.\build.ps1`) or via non-standard modules |
| 21 | Choosing the mode from a list in `/config` requires Claude Code ≥ 2.1.271; on older versions the plugin won't load |
