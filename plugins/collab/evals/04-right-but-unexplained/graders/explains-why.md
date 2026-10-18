---
type: llm
---

PASS if the response does ALL of the following:
1. Confirms the solution is correct.
2. Explains the mechanism: dict keys are unique and dict preserves insertion order (guaranteed since Python 3.7), so fromkeys keeps the first occurrence in the original order; set() does not guarantee order.
3. Helps the developer understand rather than just telling them: for example, asks a guiding question, shows a small example, or invites the developer to explain it in their own words.
4. Mentions at least one alternative (a loop with a `seen` set, normalizing email case, etc.) or a condition that would change the choice.
FAIL if the response is limited to "yes, good solution" without explaining why, or if the explanation is factually wrong.
