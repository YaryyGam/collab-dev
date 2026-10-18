---
max_turns: 30
timeout_seconds: 600
allowed_tools: [Read, Glob, Grep, Write, Edit]
---

/collab:agree we're moving the email check out of api.py and cli.py into a new module validators.py with a single function is_valid_email, because the logic is duplicated and has already diverged between the files; both files import it, we take the behavior exactly as in api.py, including TLD case sensitivity (we'll fix that in a separate task); strip and lower stay in api.py, the CLI becomes stricter — that's intentional
