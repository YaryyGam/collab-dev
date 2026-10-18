---
name: off
description: Turn off collaborative development for the rest of the session — classic Claude Code
argument-hint: <reason — a couple of words is enough>
disable-model-invocation: true
---

The developer has turned off collaborative development for the rest of this session. Reason: $ARGUMENTS

From now on, work as regular Claude Code: the collaborative development rules don't apply and writing is not blocked. Confirm the switch in one line and mention that they can turn it back on with `/collab:on`. Don't comment on the developer's decision or try to talk them out of it.
