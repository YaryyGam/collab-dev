---
name: plan
description: Confirm the agreed approach in your own words and have Claude carry it out as a staged plan, pausing for you after every stage
argument-hint: <the chosen approach and why — in your own words>
disable-model-invocation: true
---

The developer has confirmed the approach for the current unit of work and asked to carry it out as a staged plan:

> $ARGUMENTS

1. Check this restatement against what was discussed. If it diverges from what was agreed or misses something significant (a constraint, a risk, an accepted trade-off), point it out briefly and specifically. If it is accurate, confirm it in one sentence without perfunctory praise.
2. Split the work into 2–6 stages. A stage is a coherent step the developer can review on its own as a diff (for example "data model", "endpoint", "tests"), not a single line and not the whole task. Create each stage as a task with `TaskCreate`, in English whatever the conversation language: `subject` is what the stage achieves, `description` lists the files it touches and what changes in them. If `/collab:before-changes` was run for this work, put each of its items into the stage it belongs to.
3. Show the plan in your reply, in the developer's language (stages in order, files of each). If `/collab:before-changes` was not run and the change touches code other parts depend on (shared functions, an API, a DB schema, config, CI), say in one line that running it now adds what else has to change to the plan. End with a question whether to start. Do not write code now: the plugin blocks changes until the developer replies.

Then, for each stage, after the developer's go-ahead:

- Mark the stage `in_progress` with `TaskUpdate`, make its changes with Edit/Write only, then mark it `completed`.
- The plugin pauses the work at that point. In your reply, explain each file changed in the stage: what changed and why, and a card for each new or changed function following the "Code explanation format". End with a question whether to continue with the next stage.
- If the developer's reply means "go on", start the next stage. If it is feedback or a question, deal with it within the current stage, explain what you changed, and end with a question again.

After the last stage, give the final review (`## Final review`, with a `### Verification` section) instead of a question.

## When the task tools are missing

The plan lives in tasks so that it survives a long session and the plugin can pause after each stage. Before step 2, check that `TaskCreate` and `TaskUpdate` are among your tools. If they are only listed as deferred tools, load them first (`ToolSearch` with `select:TaskCreate,TaskUpdate,TaskList,TaskGet`) and go on as usual.

If the session has no task tools at all (newer models get them only when `CLAUDE_CODE_ENABLE_TODO_TOOLS=1` was set before Claude Code started), you cannot turn them on from inside the session. Do not silently replace tasks with text:

1. Show the plan in your reply as numbered stages, as in step 3.
2. Tell the developer in two or three lines: the task tools are off in this session, so the stages are not saved as tasks and the plugin will not pause after them; the plugin turns them on for the project by itself at session start (`"env": {"CLAUDE_CODE_ENABLE_TODO_TOOLS": "1"}` in `.claude/settings.local.json`), but this session built its tool list without it. Check that the file has this line (read it; do not edit it) and say what you found.
3. Ask which they want: restart Claude Code and run `/collab:plan` again (recommended: tasks and pauses work), or go on now without tasks.

If they go on without tasks: keep the same rhythm by hand. After each stage stop, explain its files as above and end with a question whether to continue; and at every stop repeat the full list of stages with each marked done, current or pending, so the plan is not lost when the conversation gets long.
