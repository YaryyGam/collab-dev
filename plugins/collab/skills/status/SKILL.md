---
name: status
description: Show the collaborative development mode, stage and current agreement
disable-model-invocation: true
---

Show the developer the collaborative development state from the `[collab]` line in the context: mode, stage, agreement text (if any), number of changes in the current unit. Then, in one line, what needs to happen next at this stage (for example, "propose an approach and justify it", "confirm it with /collab:agree", "wait for the final review"). Available commands: `/collab:agree`, `/collab:explain`, `/collab:skip`, `/collab:done`, `/collab:mode`, `/collab:off`, `/collab:on`.
