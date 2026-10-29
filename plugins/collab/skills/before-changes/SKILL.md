---
name: before-changes
description: Check the current plan for what it would break — callers, the frontend and other API clients, tests, CI, migrations, config, docs — and update the plan with every place that has to change too
disable-model-invocation: true
---

The developer asked to check the current plan before changing code: what would it break, and where else do changes have to be made? Then update the plan with them.

This is analysis: do not change project files while running this command. Its result is the updated plan.

## 1. Take the current plan

Find what is planned, in this order:

1. **Tasks**: if the work has tasks (`TaskList`; for example the stages of `/collab:plan`), they are the plan. Read each one with `TaskGet`.
2. **The plan in the conversation**: otherwise, the latest plan or approach you and the developer worked out in this session (an approved plan, the agreement in the `[collab]` status, the approach under discussion).

If there is no plan at all, say in one sentence that there is nothing to check yet and the work needs a plan first, and stop.

From the plan and the code, list concretely what it will change: files; functions, classes and methods (signature, return shape, raised errors, side effects); HTTP routes and request/response fields; DB tables and columns; events and message payloads; config keys and environment variables; CLI commands and flags; file formats; dependency versions. Read the code that is going to change. Mark each item as a **contract** change (something outside the item sees it) or **internal**.

## 2. Find what depends on it

- **Local change** (only internal items: a private helper, a new isolated file, a body change that keeps the behavior callers rely on): check it yourself, quickly: grep the names, open the callers and the tests.
- **Anything else**: launch the `collab:impact` agent with the Agent tool (`subagent_type: "collab:impact"`). If the plan spans independent areas (for example a backend endpoint and a DB schema), launch one agent per area **in parallel** (several Agent calls in one message), at most 3. Give each agent the project directory, its part of the change list with paths, and the developer's language. Do not tell it what you expect it to find: its value is finding what the plan missed. If `.collab/project-map.md` exists, mention it: the agent uses it as leads only.

## 3. Verify

Open the code behind every finding that would add work to the plan. Drop findings that don't hold up, and say which and why. Keep likely-but-unconfirmed ones as "check during the work".

## 4. Update the plan

- **Tasks**: fold each finding into the task it belongs to by updating that task's `description` with `TaskUpdate` (do not change its status), or add a new task with `TaskCreate` where the finding is its own step (for example "update the frontend client and its types"). Task text stays in English.
- **Plan in the conversation**: write the whole plan out again with the findings added in their place, not only the additions.
- **Within the agreement?** If the work is already agreed (`/collab:agree`, `/collab:plan`) and an added item goes beyond what the agreement covers, mark it and ask the developer whether to include it in this unit. Small related items (a test, a config, a fixture) are part of it.

## 5. Report

In the developer's language:

1. **The updated plan**: the steps in order, with the added items marked as new and the number of the finding that added each.
2. **What would break and why**: one numbered entry per finding, so the developer can refer to it:
   - **Where**: `path:line`, and the risk (high / medium / low).
   - **Why it breaks**: the chain from the plan to the failure, in plain words: how this place depends on the code being changed, what the plan changes there, and what exactly happens afterwards (a concrete input or scenario → the error, wrong result or failing job). For example: "`OrderBadge.tsx:14` reads `order.status` from the `/orders` response; the plan renames the field to `state`, so the value becomes `undefined`, the badge renders empty, and nothing fails loudly: no test covers it".
   - **What to do**: one line, and which plan step it went into.
3. **Check during the work**: suspected links not confirmed.
4. **Checked and safe**: one line listing what was looked at and is unaffected, so the developer sees the coverage.
5. **Tests**: which tests cover the change, the command to run before and after, and the baseline result if it was run.
6. **Not checked**: consumers outside the repository (other services, mobile apps, published clients), dynamic access that could not be traced.

End with a question: is the updated plan right, and should anything be dropped or added.
