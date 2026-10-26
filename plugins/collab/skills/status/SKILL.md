---
name: status
description: Show the collaborative development mode, stage and current agreement
disable-model-invocation: true
---

Show the developer the collaborative development state from the `[collab]` line in the context: mode, stage, agreement text (if any), number of changes in the current unit. Then, in one line, what needs to happen next at this stage (for example, "propose an approach and justify it", "confirm it with /collab:agree", "wait for the final review"). If the status has a `Plan:` line, say whether the plan is paused waiting for the developer or a stage is in progress. Available commands: `/collab:agree`, `/collab:plan`, `/collab:commit`, `/collab:push`, `/collab:git`, `/collab:review`, `/collab:note`, `/collab:map`, `/collab:resume`, `/collab:explain`, `/collab:skip`, `/collab:done`, `/collab:mode`, `/collab:off`, `/collab:on`.
