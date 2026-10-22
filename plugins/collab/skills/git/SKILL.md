---
name: git
description: Allow Claude one history-changing git command — merge, rebase, cherry-pick, revert, reset, tag, commit --amend or push --force
argument-hint: <git command> [why]
disable-model-invocation: true
---

The developer allowed one git command: $ARGUMENTS

1. Separate the command from the explanation: the command is the `git …` part (the leading `git` may be omitted), the rest is why the developer wants it.
2. If the command can lose work (`reset --hard`, `push --force`, a rebase of commits already pushed, `checkout` over uncommitted changes), check `git status` first. If uncommitted changes or unpushed commits would be lost, stop and say so instead of running it.
3. Run that command once, exactly as given. The permission covers one call of this git action only; anything else (another commit, a push) needs its own command from the developer.
4. Report the result: what changed in the history (`git log --oneline -5`, `git status -sb`), and any conflicts with how to resolve them.
