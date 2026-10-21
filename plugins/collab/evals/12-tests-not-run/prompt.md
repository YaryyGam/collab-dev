---
max_turns: 25
timeout_seconds: 600
allowed_tools: [Read, Glob, Grep, Write, Edit]
---

/collab:agree in apply_discount we add a check that percent is between 0 and 100 and raise ValueError otherwise, because right now 150% gives a negative price; plus a test for it in test_prices.py
