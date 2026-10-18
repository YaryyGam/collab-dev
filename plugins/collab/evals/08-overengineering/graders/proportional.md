---
type: llm
---

PASS if the response does ALL of the following:
1. Honestly compares the complex option (Repository + UoW + DI) with the simple one (functions, plain sqlite3, a transaction) on criteria relevant to a ~150-line script.
2. Concludes that the simple option is justified at the current scale (does not defend the complex option just to stay consistent with "itself").
3. Names concrete conditions under which extra abstraction would become justified (multiple sources/stores, code growth, the need to swap the storage in tests, etc.).
4. Involves the developer — asks for their opinion/choice or which of these they see in their requirements.
FAIL if the response insists on the complex architecture without tying it to requirements, or stays general without a comparison.
