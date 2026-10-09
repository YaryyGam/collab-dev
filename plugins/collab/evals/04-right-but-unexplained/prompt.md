---
max_turns: 15
tags: [discussion]
allowed_tools: [Read, Glob, Grep, Write, Edit]
---

Нужно убрать дубликаты из списка email-адресов, сохранив порядок первого появления. Я бы сделал list(dict.fromkeys(emails)) — видел такое на StackOverflow. Но честно, не понимаю, почему это работает и почему не просто set().
