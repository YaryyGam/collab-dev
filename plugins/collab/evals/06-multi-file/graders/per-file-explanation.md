---
type: llm
focus: trace
---

PASS if ALL of the following hold:
1. During implementation — before writing a file or right after it, before the next group of changes (not only in the final message) — the assistant explains what it is changing in the files and why.
2. For new/changed logic (the is_valid_email function and/or the change to the check in cli.py) there is an "In plain words" explanation: short pseudocode or a step-by-step description in simple language.
3. The final review states, for each of the three files (validators.py, api.py, cli.py), its purpose and what changed, and explains how the changes relate to each other; it notes that cli.py's behavior changed.
FAIL if explanations appear only in the final message, there is no "In plain words" explanation for the new logic, or any of the files is not described.
