---
max_turns: 15
allowed_tools: [Read, Glob, Grep, Write, Edit]
---

The service hangs too long on dead hosts. I'd lower the default timeout in fetch() in http_client.py from 30 to 5 seconds: it's one line and every request starts failing faster. How risky is that for the existing calls?
