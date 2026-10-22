---
name: review
description: Independent review by a separate read-only agent — of the whole project, or with "diff" of the latest changes — for bugs, tests, and docs and comments out of sync; skips what /collab:note rules cover
argument-hint: [diff]
disable-model-invocation: true
---

The developer asked for an independent review. Arguments: $ARGUMENTS

1. Mode: **diff** if the arguments say `diff` (the latest changes only), otherwise **all** (the whole project).
2. Launch the `collab:reviewer` agent with the Agent tool (`subagent_type: "collab:reviewer"`). In the prompt give it the mode, the project directory and the developer's language. Do not pass it your own view of the code or why it was written: its value is a fresh look. It reads the developer's notes (`.collab/reviewer-notes.md`) itself.
3. Show the developer the agent's report: scope, tests, what was skipped per the notes, the numbered findings as they are. If you are sure a finding is wrong (you know the code it misreads), keep it in the list and add one line why you disagree; do not drop findings silently.
4. Do not fix anything now. End with: which numbers to fix — the developer names them (for example "1, 3"), and then runs `/collab:skip fix review findings 1, 3` (or discusses them first). If a finding is something they accept on purpose, they can record it with `/collab:note <rule>` so the reviewer skips it next time.
