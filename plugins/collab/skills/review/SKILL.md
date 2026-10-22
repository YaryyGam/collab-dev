---
name: review
description: Independent review by a separate read-only agent — of the latest changes (bugs, tests, docs and comments out of sync), or of the whole project with "all"
argument-hint: [all]
disable-model-invocation: true
---

The developer asked for an independent review. Arguments: $ARGUMENTS

1. Mode: **all** if the arguments say `all`, otherwise **changes**.
2. Launch the `collab:reviewer` agent with the Agent tool (`subagent_type: "collab:reviewer"`). In the prompt give it the mode, the project directory and the developer's language. Do not pass it your own view of the changes or why they were made: its value is a fresh look.
3. Show the developer the agent's report: scope, tests, the numbered findings as they are. If you are sure a finding is wrong (you know the code it misreads), keep it in the list and add one line why you disagree; do not drop findings silently.
4. Do not fix anything now. End with: which numbers to fix — the developer names them (for example "1, 3"), and then runs `/collab:skip fix review findings 1, 3` (or discusses them first).
