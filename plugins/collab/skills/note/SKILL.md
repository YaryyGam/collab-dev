---
name: note
description: Record a rule for the reviewer (a decision made, a known project state, a covered corner case) — written word for word, kept out of git; /collab:review skips what it covers
argument-hint: <rule for the reviewer>
disable-model-invocation: true
---

The developer recorded a rule for the reviewer:

> $ARGUMENTS

The plugin has already written it word for word to `.collab/reviewer-notes.md` and excluded that file from git through `.git/info/exclude`. Confirm in one line what was recorded. Do not edit the file yourself, do not rephrase or add notes: only the developer writes them. If the plugin reported that the file could not be excluded from git, tell the developer.
