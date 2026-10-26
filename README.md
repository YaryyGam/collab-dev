<div align="center">

# 🤝 Collaborative Development

**A Claude Code plugin: the developer thinks first, then Claude writes**

*Claude writes no code until the developer has proposed an approach, explained the choice,<br>compared it with alternatives and confirmed the decision in their own words.*

`Claude Code ≥ 2.1.271` · `Python 3.9+` · `macOS / Linux / Windows (Git Bash or WSL)`

</div>

---

## Contents

- [Why this matters](#-why-this-matters)
- [What working with it looks like](#-what-working-with-it-looks-like)
- [Installation](#-installation)
- [Commands](#-commands)
- [Modes](#-modes)
- [Lifecycle of a unit of work](#-lifecycle-of-a-unit-of-work)
- [What is guaranteed and what is not](#-what-is-guaranteed-and-what-is-not)
- [Configuring and changing the rules](#-configuring-and-changing-the-rules)
- [Testing the plugin](#-testing-the-plugin)
- [Troubleshooting](#-troubleshooting)
- [Repository structure](#-repository-structure)

---

## 💡 Why this matters

The usual loop with an AI assistant: *state the task → Claude picks the architecture and writes the code → the developer skims it and accepts*. Speed goes up, but the developer becomes a spectator: they made no decisions, don't know the alternatives, and a week later can't explain why the code is built the way it is. Reviewing finished code leaves almost nothing in memory; what sticks is what you formulated yourself.

The plugin changes the order:

```
 Task ─► Claude studies the context and does NOT write code
      ─► The developer proposes their approach  ─► and explains why
      ─► Claude evaluates the solution AND the reasoning, offers alternatives, compares
      ─► The developer chooses and confirms: /collab:agree <in their own words>
      ─► Claude implements, explaining decisions along the way
      ─► Final review: what was done, why, what was verified, comprehension questions
```

The goal is not the maximum number of questions but the **maximum conscious participation** of the developer without losing speed: simple tasks take one or two short messages, complex ones get a full discussion.

---

## 👀 What working with it looks like

<details open>
<summary><b>Short example</b> (full examples for every scenario are in <a href="docs/EXAMPLES.md">docs/EXAMPLES.md</a>)</summary>

> **Developer:** Add pagination to list_users. Just write the code.

> **Claude:** Right now `list_users()` (`users.py:4`) returns all 500 users, and the test `test_users.py:5` checks for exactly 500.
> Writing files is blocked until we agree on an approach. Answer in 1–2 sentences:
> 1. **Parameters**: `page/page_size`, `offset/limit`, or a cursor?
> 2. **What to return**: still a list, or an object with `items/total`? This decides whether the current test breaks.
> 3. **Why** this choice?
>
> Skip the discussion: `/collab:skip [reason]` (this task) or `/collab:off [reason]` (for the rest of the session).

> **Developer:** `/collab:agree offset and limit as optional parameters, by default return everyone so the test and the calling code don't break; there is little data, so a cursor isn't needed`

> **Claude:** Your summary matches what we agreed. One addition: negative `offset`/`limit` would give an unexpected result via Python slicing (`USERS[-5:]`), so I'll raise `ValueError`.
> *…implementation with explanations…*
>
> ## Final review
> …
> ### Verification
> **Tests were not run**: running `pytest` required permission. To check: `python3 -m pytest -q`.
>
> **Comprehension question:** what will a client paging through with offset see if a user is added in the meantime, and why does a cursor protect against that?

*(This is a real excerpt from a test run, slightly shortened.)*

</details>

---

## 🚀 Installation

### Option 1. For the whole team, via the project (recommended)

1. Publish this repository to git (GitHub, GitLab, Bitbucket, any host).
2. In the **project repository** the team works in, create or extend `.claude/settings.json` and commit it:

```json
{
  "extraKnownMarketplaces": {
    "collab-dev": {
      "source": { "source": "git", "url": "https://github.com/YaryyGam/collab-dev.git" }
    }
  },
  "enabledPlugins": {
    "collab@collab-dev": true
  }
}
```

Every developer who opens the project in Claude Code will be prompted to trust the marketplace and install the plugin, with no manual setup. For GitHub you can use the short form `"source": { "source": "github", "repo": "YaryyGam/collab-dev" }`.

### Option 2. Manually, for yourself

```text
/plugin marketplace add https://github.com/YaryyGam/collab-dev.git
/plugin install collab@collab-dev
```

During installation choose a scope: `user` (all your projects), `project` (this project, via `.claude/settings.json`) or `local` (this project, only you).

### Option 3. Locally, for developing the plugin itself

```bash
claude --plugin-dir ./plugins/collab
# after editing plugin files in an open session:
/reload-plugins
```

### Check that everything works

```text
/collab:status
```

You should see a line like `[collab] mode=collaborative stage=discussing (writes blocked until /collab:agree)`.

> **Requirements:** Claude Code ≥ 2.1.271 (mode selection as a list in `/config`) and Python 3.9+ (standard library only). Hooks run via `scripts/run_hook.sh`, which finds `python3`, `python` or `py -3` on its own.
>
> **Windows** (including VS Code on Windows): you need **Git for Windows** (Claude Code runs hooks through its Git Bash) and Python 3.9+ from python.org or the Microsoft Store. Under WSL the plugin works as on Linux. ⚠️ Native Windows support in version 0.2.0 is written but **has not yet been tested on real Windows**: check `/collab:status` and try asking Claude to create a file before `/collab:agree`; the write should be blocked.

---

## ⌨️ Commands

All commands are invoked **by a human only**: Claude cannot run them itself (`disable-model-invocation`), and the hook accepts them only from a message the developer typed.

| Command | What it does | Example |
|---|---|---|
| `/collab:agree <approach and why>` | Confirms the agreed approach **in your own words** and unlocks writing code for the current unit of work. At least 6 words are required: the restatement is the comprehension check. Claude compares it with the discussion and points out any mismatches | `/collab:agree cache the exchange rate response in Redis for 5 minutes, because the API is paid and the data rarely changes` |
| `/collab:plan <approach and why>` | Same as `/collab:agree`, plus Claude carries the work out **stage by stage**: it creates the stages as tasks (a checklist in Claude Code), shows the plan and waits. After each stage it stops, explains every file changed in that stage and waits for your reply. Any reply lifts the pause: "go on" starts the next stage, feedback gets fixed within the current one. The pause is enforced by the hook | `/collab:plan move settings into a frozen dataclass loaded from env, then pass it explicitly to db, supplier and service, so values aren't duplicated` |
| `/collab:commit [note]` | Allows Claude **one commit**: it looks at all changes, stages files by name and writes a message saying what changed in each file. Without this command Claude can't commit at all (the hook rejects it), in any stage except `off` | `/collab:commit` |
| `/collab:push [branch]` | Allows **one push** into the given branch, or the current one if none is given. Never forced | `/collab:push feature/pagination` |
| `/collab:git <command> [why]` | Allows **one** history-changing git command: `merge`, `rebase`, `cherry-pick`, `revert`, `reset`, `tag`, `commit --amend`, `push --force` | `/collab:git rebase origin/main bring in the fresh main` |
| `/collab:review [diff]` | A **separate read-only agent** reviews the whole project: bugs, the project's tests, and docs or comments that no longer match the code. `diff` reviews only what was just done (uncommitted changes, else unpushed commits, else the last commit), with docs and comments checked across the whole project. It skips what your `/collab:note` rules cover and lists what it skipped. You get numbered findings; nothing is fixed until you name the numbers and run `/collab:skip` | `/collab:review diff` |
| `/collab:note <rule>` | Records a rule for the reviewer **word for word**: a decision made on purpose, the project's state, a corner case covered elsewhere. The plugin itself appends it to `.collab/reviewer-notes.md` and keeps that file out of git via `.git/info/exclude` (local, the repository doesn't change). Claude can read the file but not change it; edit or delete lines by hand | `/collab:note no production DB yet: don't report unapplied migrations` |
| `/collab:explain [focus]` | For when you **don't know how to solve the task** or which approach to pick. Claude analyzes the task itself and proposes 2–4 solution options: how each works, which libraries and technologies it would use and why, pros, cons, when each wins, plus a recommendation. Writing stays blocked: you pick an option and confirm it with `/collab:agree` in your own words | `/collab:explain how to rate-limit the public API` |
| `/collab:skip [reason]` | Skips the approach discussion **for one unit of work**. Explanations along the way and the final review remain. The reason is optional; if given, it shows in the status | `/collab:skip standard CRUD following the orders pattern` |
| `/collab:off [reason]` | **Classic Claude Code for the rest of the session**: no blocking and no process. A new session starts in collaborative mode again | `/collab:off prod is on fire, hotfix` |
| `/collab:on` | Turns collaborative development back on in the current session | |
| `/collab:map [focus]` | **Reverse-engineers the whole project into one file**, `.collab/project-map.md`: what it is, stack with versions, architecture and flow diagrams (Mermaid), every endpoint with its handler, databases and how they connect (sync/async and why), data model, domain logic per module, integrations and background work, module dependencies, config, tests/CI, risks, and where a newcomer should start. Every fact links to `file:line`. Small projects are analyzed by Claude alone, larger ones by 3–5 parallel read-only `collab:analyst` agents. Works in any stage, the file stays out of git (`.git/info/exclude`), and every new session is pointed to it so you don't have to explain the project again | `/collab:map` or `/collab:map payments` |
| `/collab:done` | Closes the current unit of work manually; the next task starts with a new agreement | |
| `/collab:resume` | Reopens the **last closed** unit of work with the same agreement, for when Claude gave the final review (or you ran `/collab:done`) before everything agreed was done. No new restatement needed. When a unit closes, the plugin tells you so and names this command | `/collab:resume` |
| `/collab:mode <mode>` | Changes the mode for the rest of the session: `learning`, `collaborative`, `review` | `/collab:mode learning` |
| `/collab:status` | Shows the mode, stage, current agreement and what to do next | |

> 💡 If you have no idea what's going on and just need it done, `/collab:off [reason]` honestly switches to the normal mode. Every switch is written to a **local** journal (`~/.claude/plugins/data/<plugin>/journal.jsonl`). It is never sent anywhere and exists for you: it shows which topics are worth brushing up on.

---

## 🎚 Modes

The default mode is set in **`/config` → Collaborative Development → Default collaboration mode** (stored per developer). For a single session, use `/collab:mode`.

| | 🎓 **Learning** | 🤝 **Collaborative** *(default)* | 🔍 **Review** |
|---|---|---|---|
| **Purpose** | New technology, a hard task, building skills | Everyday development | The developer designs and writes the code, Claude reviews |
| **Approach discussion** | Detailed, with follow-up questions | Mandatory, concise | The developer proposes the whole implementation |
| **Reasoning analysis** | Point by point: correct / mistaken assumptions / overlooked | Main pros, cons, the key factor | Mistakes, overlooked constraints |
| **Alternatives** | 2, if both are substantive | 1 substantive | Offered, but the code is not rewritten for the developer |
| **Explanations during implementation** | Every new function, class, non-trivial construct | Significant decisions | Claude writes code only on direct request after `/collab:agree` |
| **Final review** | Full, 2–3 comprehension questions | Key changes, a question if there was an important decision | Focus on what the developer decided and fixed themselves |

Blocking writes until agreement, explaining significant decisions and the final review apply **in all modes**.

---

## 🔄 Lifecycle of a unit of work

A **unit of work** is one coherent piece of functionality ("pagination for the users endpoint"). An agreement is valid only within it.

```
                ┌──────────────── /collab:on ◄─────────────────┐
                ▼                                              │
        ┌──────────────┐  /collab:agree <summary>    ┌────────┐ │
 start ►│  discussing  │────────────────────────────►│ agreed │ │
session │writes BLOCKED│  /collab:skip [reason]      │skipped │ │
        └──────────────┘────────────────────────────►└────────┘ │
                ▲                                        │      │
                │  "## Final review" + "### Verification"│      │
                └──────────── or /collab:done ◄──────────┘      │
                                                                │
        /collab:off [reason] (from any stage) ────────►  off  ──┘
                                            (classic until the session ends)
```

- While the stage is `discussing`, the hook **blocks** writes to project files (`Write`, `Edit`, `NotebookEdit`) and write-like Bash commands (`>`, `rm`, `sed -i`, `git commit`, `npm install`…). Reading, searching and running tests are always allowed. Writing outside the project (notes, scratchpad) is allowed.
- After agreement, Claude changes file contents **only with `Edit`/`Write`**, so every code change shows up as a diff you can read. Shell commands that write file contents in the project (`cat > file`, `echo >>`, `sed -i`, `tee`, a script one-liner that writes a file) are rejected; git, package managers, tests and `rm`/`mv` still run in the shell.
- After the **first** change to each file within a unit of work, Claude gets a reminder: explain what changed and why, and show how it works "in plain words" with short pseudocode. For mechanical edits one sentence is enough.
- If in the `agreed` stage Claude finishes **with changes but without a final review** and without a question for you, the hook sends it back to write the review. A review with a "Verification" section closes the unit, and the next task starts with a discussion again.
- Every changed file must be explained: along the way, or in the review under `### Explanation by file` with a `#### <file>` heading per file. Files Claude skipped during the work are listed back to it before the unit can close.
- If the task drifts away from what was agreed, the rules require Claude to propose closing the unit and agreeing on a new one (this is model behavior, see below).

---

## 🛡 What is guaranteed and what is not

The plugin combines two kinds of mechanisms, and it is important to be honest about the difference.

| Requirement | Mechanism | Strength |
|---|---|---|
| Nothing is written to the project before agreement | `PreToolUse` hook → `deny` for `Write`/`Edit`/`NotebookEdit` | 🔒 **Hard**: Claude Code itself rejects the call, in any permission mode |
| Same for writes via Bash | `PreToolUse` hook + heuristic command parsing | 🔐 **Hard, but heuristic**: common ways of writing are caught; elaborate ones (`python script.py` that writes files) are not |
| Only a human can give agreement | `UserPromptExpansion` hook (fires only on a command typed by a human), `disable-model-invocation`, a ban on writing to state files | 🔒 **Hard** (within the limits of the Bash heuristic) |
| Agreement is a restatement, not "ok" | At least 6 words in `/collab:agree` | 🔒 Length is hard; Claude checks the **meaning**, which is soft |
| Code changes are visible as diffs | `PreToolUse` hook rejects shell commands that write file contents in the project during an open unit | 🔐 **Hard, but heuristic** (same parsing as the Bash gate): a script file that writes on its own is not caught |
| An explanation of each changed file during the work, with "in plain words" pseudocode | A `PostToolUse` hook adds a reminder for Claude after the first change to each file | 💬 The reminder always arrives, but in measurements Claude acted on it for only ~1 file in 8. The guarantee is the next row |
| Every changed file is explained by the end of the unit | `Stop` hook: files without a long enough text naming them in the transcript need a `#### <file>` heading under `### Explanation by file` in the review | 🔐 Presence of a heading per file is hard (one retry); **content** is soft |
| A final review with an honest "Verification" section | `Stop` hook → won't let Claude finish without the headings (`## Final review` / `### Verification`, written in English in any conversation; Russian and Ukrainian variants are accepted too) | 🔐 Presence of the sections is hard (one retry); **content** is soft |
| The unit is not closed early without you noticing | `Stop` tells Claude to check the agreement point by point before a review; a closed unit is announced to you with `/collab:resume` to reopen it | 💬 Not reviewing early is soft; 🔒 the announcement and `/collab:resume` are hard |
| Claude never commits, pushes or rewrites history on its own | `PreToolUse` rejects `git commit/push/merge/rebase/cherry-pick/revert/reset/tag` unless the developer's `/collab:commit`, `/collab:push` or `/collab:git` gave a one-off permission (only a typed command can, via `UserPromptExpansion`) | 🔐 **Hard, but heuristic**: git called from a script, an alias or another tool (`make release`, `gh pr merge`) is not seen |
| Small decisions come as 2–3 options; a number is enough to answer | Rule in the output style | 💬 Soft |
| `/collab:review` checks with fresh eyes and changes nothing | The `collab:reviewer` agent gets only the mode, not the author's reasoning; it has no Write/Edit tools | 🔐 No edits is hard for files (no tools); its Bash is restricted by instruction only. **What it finds** is soft |
| Reviewer notes are only the developer's words | `/collab:note` is written by the hook itself (`UserPromptExpansion`, a typed command only); `PreToolUse` rejects Claude's Write/Edit of the file and shell writes that name it, in every stage | 🔐 **Hard, but heuristic** for the shell (a command that builds the path otherwise isn't seen). That the reviewer **honours** the notes is soft |
| `/collab:plan`: a pause after every stage, with the stage's files explained | `PostToolUse` on `TaskUpdate → completed` pauses the unit; `PreToolUse` blocks changes and stage updates until your next message; `Stop` checks that each file of the stage is named in an explanation | 🔐 The pause is hard once a stage is marked completed; **marking it** and judging whether your reply means "go on" are soft |
| The developer's approach first, reasoning analysis, alternatives, explanations along the way, adapting to the developer's level, honesty | Output style (rules in every request) + mode context from hooks | 💬 **Soft**: raises the likelihood, doesn't guarantee it. Measured by eval scenarios |
| "Unrelated task → new agreement" | A rule in the output style | 💬 Soft: a hook cannot judge whether tasks are related in meaning |

Details: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) and [docs/LIMITATIONS.md](docs/LIMITATIONS.md).

---

## 🛠 Configuring and changing the rules

All behavior is described in text and config; you almost never need to touch code.

| What you want to change | Where | Code needed? |
|---|---|---|
| The process: stages, what to ask, how to analyze, the final review format | [`plugins/collab/output-styles/collab.md`](plugins/collab/output-styles/collab.md) | No |
| Differences between modes | [`plugins/collab/modes/*.md`](plugins/collab/modes) | No |
| Minimum length of `/collab:agree`, which tools/Bash commands count as writes, final review headings | [`plugins/collab/config/gate.json`](plugins/collab/config/gate.json) | No |
| Command texts and what Claude does after them | [`plugins/collab/skills/*/SKILL.md`](plugins/collab/skills) | No |
| Blocking and stage logic | [`plugins/collab/scripts/collab_gate.py`](plugins/collab/scripts/collab_gate.py) + tests | Yes |

After a change: bump `version` in `plugin.json` (otherwise installed copies won't update), run the unit tests and evals. A step-by-step guide with examples: [docs/CUSTOMIZING.md](docs/CUSTOMIZING.md).

---

## ✅ Testing the plugin

```bash
# 1. Manifests
claude plugin validate ./plugins/collab && claude plugin validate .

# 2. Unit tests of the hard logic (blocking, stages, commands, Bash heuristic): seconds, free
python3 -m unittest discover -s plugins/collab/tests -v

# 3. Behavioral scenarios from the spec (real Claude sessions, cost money)
cd plugins/collab
#   discussion scenarios: with and without the plugin (Δ shows the plugin's contribution)
claude plugin eval . --tag discussion --scaffold --allow-tools Write Edit --trust-plugin --judge-model sonnet
#   implementation scenarios: start with /collab:agree, so plugin only
claude plugin eval . --tag implementation --ablation none --scaffold --allow-tools Write Edit --trust-plugin --judge-model sonnet
```

The 12 scenarios from the spec live in [`plugins/collab/evals/`](plugins/collab/evals); actual results and the issues found are in [docs/ACCEPTANCE.md](docs/ACCEPTANCE.md).

---

## 🩺 Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `/collab:*` is not in the menu | The plugin is not enabled: `/plugin` → check `collab@collab-dev`; after edits, `/reload-plugins` |
| Claude says "writes are blocked" even though you agreed | The agreement wasn't confirmed with the command. Run `/collab:agree <summary>`; a spoken "yes" is not enough. The plugin also shows you this hint when it blocks a write, and Claude ends the discussion with a draft `/collab:agree …` line to put into your own words |
| Writes got blocked right after Claude's summary, though work remained | The final review closed the unit early. Run `/collab:resume`: the same agreement opens again and Claude continues with what is left |
| `/collab:agree` is rejected | The summary is shorter than the minimum (6 words). Describe the approach and the reason |
| A read-only Bash command is blocked | A false positive of the heuristic (for example, `>` in an unquoted argument). Report it: the command can be added to the exceptions in `gate.json`; Claude can use Read/Grep |
| The message "internal hook error, writes are blocked" | The script failed; the block deliberately fails closed. Run with `COLLAB_DEBUG=1` (see below) and report it; as a workaround, disable the plugin in `/plugin` |
| Windows: Claude writes files before `/collab:agree`, `/collab:status` doesn't show the `[collab]` line | The hooks didn't run. Check that Git for Windows is installed and that `python --version` or `py -3 --version` shows 3.9+. Details are in the Claude Code debug log (`claude --debug`) |
| "collab: Python 3.9+ not found … writes are blocked" | Python wasn't found as `python3`, `python` or `py -3`. Install Python 3.9+ or disable the plugin in `/plugin` |
| You need "pure" classic mode without the rules text in context | `/collab:off` turns off blocking and the process, but the rules text stays in context. For 100% classic: `/plugin` → disable `collab` and restart |

**Debugging:** `COLLAB_DEBUG=1 claude …` writes the inputs and outputs of all hooks to `~/.claude/plugins/data/<plugin>/debug.jsonl`; session state is in `…/sessions/<session_id>.json`.

---

## 📁 Repository structure

```
.
├── .claude-plugin/marketplace.json     # marketplace: the team connects it with one URL
├── plugins/collab/                     # the plugin itself
│   ├── .claude-plugin/plugin.json      # manifest + default_mode setting in /config
│   ├── output-styles/collab.md         # ⭐ CORE PROCESS RULES (enabled automatically)
│   ├── modes/                          # learning / collaborative / review: mode differences
│   ├── agents/reviewer.md              # read-only reviewer behind /collab:review
│   ├── agents/analyst.md               # read-only analysts behind /collab:map
│   ├── skills/                         # commands /collab:agree, plan, commit, push, git, review, note, map, explain, skip, off, on, done, resume, mode, status
│   ├── hooks/hooks.json                # which events invoke the script
│   ├── scripts/run_hook.sh             # hook launcher: finds python3 / python / py -3
│   ├── scripts/collab_gate.py          # hard logic: blocking, stages, review check
│   ├── config/gate.json                # configurable logic parameters
│   ├── tests/                          # unit tests for the script
│   └── evals/                          # 12 behavioral scenarios from the spec
└── docs/
    ├── ARCHITECTURE.md                 # architecture and rationale for the chosen mechanisms
    ├── EXAMPLES.md                     # example dialogues by scenario
    ├── CUSTOMIZING.md                  # how to change the rules
    ├── LIMITATIONS.md                  # known limitations
    └── ACCEPTANCE.md                   # results of checking against the acceptance criteria
```

---

<div align="center">

*The goal is not to get code faster, but for everyone on the team to be able to explain why the code is built the way it is.*

</div>
