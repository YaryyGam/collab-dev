---
max_turns: 30
timeout_seconds: 600
allowed_tools: [Read, Glob, Grep, Write, Edit]
---

/collab:agree выносим проверку email из api.py и cli.py в новый модуль validators.py с одной функцией is_valid_email, потому что логика продублирована и уже разошлась между файлами; оба файла импортируют её, поведение берём точно как в api.py, включая чувствительность к регистру TLD (это исправим отдельной задачей); strip и lower остаются в api.py, CLI станет строже — это осознанно
