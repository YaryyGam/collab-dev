---
max_turns: 25
timeout_seconds: 600
allowed_tools: [Read, Glob, Grep, Write, Edit]
---

/collab:agree в apply_discount добавляем проверку что percent от 0 до 100 и бросаем ValueError иначе, потому что сейчас 150% даёт отрицательную цену; плюс тест на это в test_prices.py
