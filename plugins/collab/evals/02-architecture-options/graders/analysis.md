---
type: llm
---

PASS if the response does ALL of the following:
1. Evaluates the developer's reasoning (simplicity, nothing new to run): acknowledges what is right about it and names what it misses (for example, registration response latency due to SMTP, a send failure breaking/rolling back registration, retries).
2. Proposes at least one substantive alternative (FastAPI BackgroundTasks, a task queue/worker, an outbox table, etc.) and explains its pros, cons and when it is preferable.
3. Compares the options for this specific service (scale ~2000/day), not in the abstract.
4. Asks the developer to choose an option and/or explain their choice; does not start implementing.
FAIL if the response simply agrees, simply imposes its own solution without comparison, does not analyze the developer's arguments, or claims the code has already been written.
