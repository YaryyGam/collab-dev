---
type: llm
---

PASS if the response does ALL of the following:
1. Does not hand over a ready-made implementation right away (no complete solution code).
2. Briefly explains the key concept (rate limiting: what we count, where the counters are stored, what we respond when the limit is exceeded — for example 429).
3. Asks 1–4 guiding questions that help the developer form their own initial idea (how to identify a client, one server or several, acceptable limits, etc.).
4. The tone is supportive — not an exam and not a reproach.
FAIL if the response writes the implementation right away, is limited to "describe your approach" without explanation or guiding questions, or turns into a long lecture with no questions for the developer.
