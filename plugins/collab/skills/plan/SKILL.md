---
name: plan
description: Confirm the agreed approach in your own words and have Claude carry it out as a staged plan, pausing for you after every stage
argument-hint: <the chosen approach and why — in your own words>
disable-model-invocation: true
---

The developer has confirmed the approach for the current unit of work and asked to carry it out as a staged plan:

> $ARGUMENTS

1. Check this restatement against what was discussed. If it diverges from what was agreed or misses something significant (a constraint, a risk, an accepted trade-off), point it out briefly and specifically. If it is accurate, confirm it in one sentence without perfunctory praise.
2. Split the work into 2–6 stages. A stage is a coherent step the developer can review on its own as a diff (for example "data model", "endpoint", "tests"), not a single line and not the whole task. Create each stage as a task with `TaskCreate`: `subject` is what the stage achieves, `description` lists the files it touches and what changes in them.
3. Show the plan in your reply (stages in order, files of each) and end with a question whether to start. Do not write code now: the plugin blocks changes until the developer replies.

Then, for each stage, after the developer's go-ahead:

- Mark the stage `in_progress` with `TaskUpdate`, make its changes with Edit/Write only, then mark it `completed`.
- The plugin pauses the work at that point. In your reply, explain each file changed in the stage: what changed and why, and a card for each new or changed function following the "Code explanation format". End with a question whether to continue with the next stage.
- If the developer's reply means "go on", start the next stage. If it is feedback or a question, deal with it within the current stage, explain what you changed, and end with a question again.

After the last stage, give the final review (`## Final review`, with a `### Verification` section) instead of a question.
