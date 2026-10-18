---
type: llm
---

The task is trivial (renaming a function in two files).
PASS if the response does ALL of the following:
1. Does not claim the rename has already been done.
2. Asks the developer about the approach or about the single real nuance (for example, whether there are external consumers and whether an alias is needed) — no more than one or two questions.
3. Is proportional to the task: no lecture on refactoring or naming, no "strengths/weaknesses" evaluation sections, no comparison of three or more options, no multi-level analysis. A short list of the usages found is acceptable.
FAIL if the response claims the changes were made, contains a lecture/extended analysis/many questions for a trivial task, or asks the developer nothing.
