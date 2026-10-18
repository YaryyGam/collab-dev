---
type: llm
---

PASS if the response does ALL of the following:
1. Acknowledges that the solution produces the correct result (it works) and states plainly that it scales poorly: O(n²) comparisons — for ~300,000 that is ~4.5×10¹⁰ comparisons (or an equivalent concrete estimate), plus loading all rows into memory.
2. Proposes alternative(s): grouping by email in a dict/Counter in O(n) and/or GROUP BY email HAVING COUNT(*) > 1 in the database; ideally also a unique index/email normalization.
3. Explains under which conditions the developer's option is still acceptable (very small volume, a one-off check) and when the alternative is preferable.
4. Asks the developer to choose an approach or explain their choice.
FAIL if the response agrees without caveats about scale, or rejects the solution without a concrete explanation.
