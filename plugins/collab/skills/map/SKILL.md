---
name: map
description: Reverse-engineer the whole project into one Markdown file (.collab/project-map.md) — stack, architecture diagrams, endpoints, data and connections, logic, file relations — so later sessions start from it instead of re-exploring
argument-hint: [focus area, optional]
disable-model-invocation: true
---

The developer asked for a full map of this project. Focus (may be empty; if given, map the whole project briefly and this area in depth): $ARGUMENTS

The goal: one file that explains the project completely, so neither the developer nor a later Claude session has to explore it from scratch. Accuracy beats volume: every fact must come from the code.

## 1. Survey (yourself, quickly)

- Size and shape: `git ls-files | wc -l`, `git ls-files | cut -d/ -f1-2 | sort | uniq -c | sort -rn | head -40`.
- Manifests and infrastructure: package.json / pyproject.toml / requirements / go.mod / pom.xml / Cargo.toml, lockfiles, Dockerfile, docker-compose, CI configs, Makefile.
- Existing docs: README, CLAUDE.md / AGENTS.md, docs/.
- If `.collab/project-map.md` already exists, read it: update it rather than starting over, and check `git log --since=<its date> --stat` for what changed.
- Never copy secret values from `.env` or configs: only variable names and purpose.

## 2. Decide how to analyze

Decide by **lines of source code**, not by the number of files: count them with `git ls-files | xargs wc -l`, leaving out lockfiles, generated and vendored code, fixtures and data files.

- **Up to about 5,000 lines**: analyze it yourself.
- **More than that**: launch `collab:analyst` agents **in parallel** (several Agent calls in one message, `subagent_type: "collab:analyst"`), one per area, 3–5 in total:
  1. stack, infrastructure, config, tests and CI;
  2. entry points and API;
  3. data layer;
  4. domain logic and module dependencies (split by top-level packages if the code is large: one agent per group);
  5. integrations, background work, sync/async.

  Give each agent the project directory, its area (and part of the repository, if split), your survey summary, the focus if any, and the developer's language. Do not give them conclusions to confirm.

## 3. Merge and verify

Merge the findings. Where they disagree or something looks off, read the code yourself. Spot-check at least 3–5 key claims (an endpoint handler, the DB connection setup, one main flow end to end). Anything you could not verify stays marked as unverified.

## 4. Write `.collab/project-map.md`

Write it with the Write tool (the plugin allows this file in every stage and keeps it out of git). Language: the developer's; identifiers, paths and code as they are. Every factual statement carries a `path:line` reference. Mermaid diagrams: keep each under ~25 nodes; split a bigger one.

```
# <Project name> — project map

> Generated <date> by /collab:map · commit <git rev-parse --short HEAD> · scope: whole project | focus: <…> · analyzed by: Claude alone | N analyst agents

## 1. What it is            — purpose, users, main capabilities, in 5–10 lines
## 2. Tech stack            — table: layer | technology | version | where | what for / why
## 3. Architecture          — Mermaid flowchart of components and external systems, then a short explanation
## 4. Repository layout     — table: directory/file → responsibility
## 5. Entry points and API  — table of endpoints: method | path | handler path:line | auth | what it does; then CLI, jobs, consumers, webhooks
## 6. Key flows             — for the 2–4 most important flows: Mermaid sequenceDiagram + numbered steps with path:line
## 7. Data                  — databases and stores; connection (driver, pool, sync or async, and why); Mermaid erDiagram of the main tables; migrations; transactions, locks, idempotency; caching
## 8. Domain logic          — per module: responsibility, key functions/classes (path:line), business rules, calculations, status transitions
## 9. Integrations and background work — external APIs (timeouts, retries, idempotency), queues, schedulers, concurrency model
## 10. Module dependencies  — Mermaid graph of who depends on whom + "if you change X, also check Y"
## 11. Configuration        — environment variables (name | purpose | default | required), config files; no secret values
## 12. Errors, logging, observability
## 13. Tests and CI/CD      — how to run, what is covered, what is not, pipeline steps
## 14. Risks and open questions — fragile spots, tech debt, inconsistencies, things marked unverified
## 15. Where to start       — the 5–10 files a new developer should read first, in order, and why
```

Skip a section only if the project has nothing for it, and say so in one line (for example "no background jobs").

## 5. Reply to the developer

In their language: where the file is, a 5–8 line summary of the project, what remains uncertain or unverified, and that later sessions will be pointed to the map automatically. Re-run `/collab:map` after big changes to refresh it.
