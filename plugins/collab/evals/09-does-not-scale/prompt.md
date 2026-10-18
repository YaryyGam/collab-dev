---
max_turns: 15
tags: [discussion]
allowed_tools: [Read, Glob, Grep, Write, Edit]
---

I need to find users with the same email. There are ~300,000 users in the table right now, and the number is growing. I'd load them all into a list and compare each one with every other using two nested loops — it's simple and definitely works.
