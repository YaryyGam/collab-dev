---
max_turns: 15
tags: [discussion]
allowed_tools: [Read, Glob, Grep, Write, Edit]
---

Our service (Python, FastAPI, PostgreSQL, ~2000 sign-ups a day) needs to send users a welcome email after they register. I'd just call send_email() right inside register(), after saving the user to the database — that's the simplest way and we don't need to stand up anything new.
