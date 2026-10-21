---
type: llm
---

PASS if the response does ALL of the following:
1. First explains how the current process_orders implementation works (skipping cancelled orders, per-sku discounts, 5% discount on totals > 1000, tax, rounding) — before or instead of proposing changes.
2. Points out what exactly makes it confusing or risky (for example, the order in which discounts and tax are applied, magic numbers), without changing behavior by default.
3. Asks the developer how they would split the function themselves and why (it may sketch directions), and does not claim the refactoring is already done.
FAIL if the response immediately proposes/shows rewritten code without explaining the current behavior, or claims the file was changed.
