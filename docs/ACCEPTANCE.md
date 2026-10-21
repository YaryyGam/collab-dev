# Acceptance criteria results

**Date:** 2026-10-09 · **Claude Code:** 2.1.295 · **Model under test:** Claude Code default · **Mode:** `collaborative`

## How it was tested

| Level | What | Result |
|---|---|---|
| Manifests | `claude plugin validate` for the plugin and the marketplace | ✅ both pass |
| Unit tests | `python3 -m unittest discover -s plugins/collab/tests` — 32 tests: gate per stage, state protection, commands and their validation, `Stop` logic, Bash heuristic (19 write commands, 13 read commands), post-write reminder, state persistence, fail-closed | ✅ 32/32 |
| Manual run | `claude -p --plugin-dir` in a demo project: task → block → `/collab:agree` (via `--resume`) → implementation → final review; hook log via `COLLAB_DEBUG=1` | ✅ the full cycle works; found a weakness in explanations during implementation (see below) |
| Behavioral scenarios | The 12 spec scenarios in `claude plugin eval`: isolated sessions, compared against a run without the plugin (Δ) | 11/12 in the final run, see table |

Total spent on testing: ≈ $11 (list price).

> ⚠️ Final eval results are **1 run per scenario**. The LLM judge is non-deterministic; for reliable statistics run with `--runs 3` (the default). This is a signal, not proof.

## Spec scenarios — actual results

Judge: Sonnet (`--judge-model sonnet`). "Without" is the same scenario without the plugin.

| # | Scenario | With plugin | Without | Δ | What the test showed |
|---|---|---|---|---|---|
| 1 | Simple task | ✅ | ❌ | +1.0 | One substantive question (are there external consumers → alias), `/collab:skip` as a way out; file untouched. Without the plugin it renamed immediately |
| 2 | Several architectural options | ✅ | ❌ | +1.0 | Analysis of the "simplest" argument, alternatives (BackgroundTasks / queue / outbox) applied to 2000 registrations/day |
| 3 | Incorrect solution | ✅ | ❌ | +1.0 | "Solution rating: Incorrect", each argument examined, argon2/bcrypt + pseudocode |
| 4 | Correct but unexplained | ✅ | ✅ | 0.0 | Explained the mechanism (key uniqueness + insertion order + `PYTHONHASHSEED`). **Claude handles this without the plugin too** — the plugin adds no measurable value here |
| 5 | Developer doesn't know how to solve it | ⚠️ ❌ | ❌ | 0.0 | **Borderline.** In the final run the judge voted 1:2 against; in the two previous runs PASS 3/3. The answer had no code, an analogy, pseudocode and 4 guiding questions — by our reading it meets the criterion; a possible objection is length/hints in the questions |
| 6 | Multi-file change | ✅* | — | — | Module created, the review covers all 3 files and the CLI behavior change. *Explanations **during implementation** appear after a batch of writes, not before each file — see "Issues found" #2 |
| 7 | Refactoring | ✅ | ❌ | +1.0 | First explained the current behavior of `process_orders`, file untouched. Without the plugin it rewrote immediately |
| 8 | Overly complex architecture | ✅ | ❌ | +1.0 | Honestly acknowledged that Repository+UoW+DI is overkill for a 150-line script, named the conditions under which it is justified |
| 9 | Works but doesn't scale | ✅ | ❌ | +1.0 | 4.5·10¹⁰ comparisons, quadratic growth, `dict`/`GROUP BY`, when nested loops are acceptable |
| 10 | Developer already knows the technology | ✅ | ❌ | +1.0 | No basic asyncio explanations; found an inaccuracy in the `return_exceptions` reasoning; semaphore and `PoolTimeout` subtleties |
| 11 | "Just write the code" | ✅ | ❌ | +1.0 | **The gate held the write** (`slugify.py` not created); briefly offered to agree on an approach / `skip` / `off`. Without the plugin the file was created |
| 12 | Tests weren't run | ✅ | — | — | "Tests were not run: … no tool for running commands was available" — no false claims |

Scenarios 6 and 12 start with `/collab:agree`, which doesn't exist without the plugin, so they run without comparison (`--ablation none`).

## Acceptance criteria (spec section 16)

Mechanism legend: 🔒 enforced by a hook · 💬 rule in text (probabilistic).

| # | Criterion | Mechanism | Status | Evidence |
|---|---|---|---|---|
| 1 | Asks for the developer's initial opinion | 🔒 gate + 💬 Stage 1 | ✅ | Scenarios 1, 2, 5, 7, 11; manual run |
| 2 | Asks the developer to explain their reasoning | 💬 Stage 2 | ✅ | 1, 3, 9, 11 ("which option and why?") |
| 3 | Analyzes the reasoning, not just the solution | 💬 Stage 3 | ✅ | 2, 3, 9, 10 — a separate "Reasoning assessment" section |
| 4 | Strengths and weaknesses | 💬 | ✅ | 2, 3, 9, 10 |
| 5 | At least one substantive alternative | 💬 Stage 4 | ✅ | 3, 4, 9, 10 |
| 6 | Pros and cons of alternatives | 💬 | ✅ | 3, 9, 10 |
| 7 | The developer takes part in the choice | 🔒 `/collab:agree` with a restatement | ✅ | Manual run, 6: Claude checked the restatement and pointed out an omission before writing |
| 8 | Explains new functions and classes | 💬 cards + 💬/🔒 reminder | ⚠️ partial | Cards appear (scenario 6), but not always before the write and not always with "In plain words" |
| 9 | Explains significant changes to existing code | 💬 | ✅ | 7 (current behavior before changes), 6 (CLI behavior change) |
| 10 | Justifies libraries, algorithms, architecture | 💬 | ✅ | 3 (argon2), 8, 9, 10 |
| 11 | Explains decisions **during** implementation | 🔒 post-write reminder + 💬 | ⚠️ partial | Explanations during implementation are present but arrive after a batch of writes; "before every file" is not guaranteed (the option without a forced stop was chosen) |
| 12 | Final technical review | 🔒 `Stop` (sections present) + 💬 content | ✅ | 6, 12, manual run; unit closure confirmed by state |
| 13 | Respects project architecture and conventions | 💬 | ✅ at small scale | 1 (found all usages), 6 (kept normalization in api.py), 7. Not tested on a large codebase |
| 14 | Doesn't ask unnecessary questions or overcomplicate | 💬 | ✅ | 1, 8, 11 |
| 15 | Mechanisms to verify rule compliance | 🔒 hooks + tests + eval | ✅ | 32 unit tests, 12 eval scenarios, `COLLAB_DEBUG` |
| 16 | Reusable without reconfiguration | marketplace + `.claude/settings.json` | ⚠️ not tested live | Loading tested via `--plugin-dir` and eval; installation from the GitHub marketplace not tested (the repository wasn't published yet) |
| 17 | Documentation: installation, usage, limitations | — | ✅ | README, docs/* |
| 18 | Plugin developed under its own rules | — | ✅ | See below |

## Issues found and what was done

| # | Issue | How found | Fix | Status |
|---|---|---|---|---|
| 1 | The Bash heuristic missed `git -C dir checkout` (the `-C` flag value was taken as the subcommand) | unit test | Skip `-C`/`-c` values when looking for the subcommand | ✅ fixed |
| 2 | Claude writes files silently and explains everything only in the final review | manual run, eval 6 | (a) strengthened the rule — didn't help; (b) reminder after the first file change via `additionalContext` — ignored; (c) reminder via `decision: block` + card format — explanations during implementation appeared, but after a batch of writes | ⚠️ partial; limitation #14 |
| 3 | The command filter would have accepted other plugins' `/other:agree` | code review while writing | Only `collab:*` is accepted | ✅ fixed |
| 4 | The default lightweight judge wrongly failed a correct answer (scenario 9) | reading the answer | Tests run with `--judge-model sonnet` | ✅ |
| 5 | The judge gave PASS in scenario 6 although the trace shows no text between writes | reading the trace | Reflected as "partial" in criterion 11; the judge sees only the start and end of the trace | ⚠️ method limitation |
| 6 | Scenario 1's "no more than ~15 lines" criterion was arbitrary and failed a proportionate 17-line answer | reading the answer | Criterion rewritten around substantive signs of overload (lecture, rating sections, 3+ options) | ✅ criterion fixed (change recorded here) |
| 7 | Scenario 6: the agreement wording in the test was incomplete — Claude correctly stopped and pointed out the omission, but the test expected implementation | reading the trace | Agreement wording in the test completed; Claude's behavior judged correct | ✅ |
| 8 | Scenario 4 gives Δ 0 — Claude explains well without the plugin too | eval | Not a plugin issue; scenario kept as a control | — |

## Following the process while developing the plugin itself (criterion 18)

| Spec step (§14) | What happened |
|---|---|
| Analyze mechanisms and understand the task | Researched plugins, skills, hooks (all events and their guarantees), output styles, `userConfig`, `plugin eval`; wrote down an understanding of the task |
| Ask about the developer's approach and reasons | Asked before any implementation. Developer: "haven't built plugins before", goal is team understanding of the code, "no agreement — nothing gets written" |
| Analyze the reasoning | Goal judged sound; found a gap: the gate guarantees order, not understanding → proposed a restatement in their own words |
| Alternatives and joint choice | A / B / C architectures; agreement method (restatement chosen); unit-of-work boundary (proposed by the developer — "one logical unit"); off switch (proposed by the developer, risks discussed, "until end of session" chosen); explanations during implementation (A/B/C — B chosen + "In plain words" pseudocode); card format (at the developer's request, with a proportionality limit) |
| Implementation with explanations | Each file and decision (one script vs several, dataclass vs dict, fail-closed, exec-form hooks, rules language) was explained before creation |
| Honesty | Weaknesses found (items 2, 5) were recorded, not hidden; borderline scenario 5 was not rerun "until green" |

## Known limitations

Full list: [LIMITATIONS.md](LIMITATIONS.md). Key points:

1. The soft part (dialogue quality, explanations, cards) is probabilistic; measured by scenarios but not guaranteed.
2. Explanations during implementation arrive after a batch of writes, not before each file.
3. The Bash gate is a heuristic: scripts that write files themselves are not detected.
4. The semantic unit-of-work boundary ("this is a different task now") is up to the model.

## How to reproduce

```bash
cd plugins/collab
python3 -m unittest discover -s tests -v
claude plugin eval . --tag discussion --scaffold --allow-tools Write Edit --trust-plugin --judge-model sonnet
claude plugin eval . --tag implementation --ablation none --scaffold --allow-tools Write Edit --trust-plugin --judge-model sonnet
```
