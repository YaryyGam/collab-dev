---
max_turns: 15
tags: [discussion]
allowed_tools: [Read, Glob, Grep, Write, Edit]
---

I need to remove duplicates from a list of email addresses while keeping the order of first appearance. I'd do list(dict.fromkeys(emails)) — I saw it on StackOverflow. But honestly, I don't understand why it works or why not just use set().
