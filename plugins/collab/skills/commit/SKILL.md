---
name: commit
description: Allow Claude one commit — it reviews all changes, stages them by name and writes a message describing what changed in each file
argument-hint: [note for the commit message]
disable-model-invocation: true
---

The developer allowed one commit. Their note (may be empty): $ARGUMENTS

1. Look at everything that changed: `git status` and `git diff` (staged and unstaged). If something looks unrelated to the work or should not be committed (secrets, `.env`, build artifacts, editor folders, files from another task), do not commit it: list it and ask the developer.
2. Stage the files by name (`git add <files>`), not `git add -A` / `git add .`.
3. Write the message in the style of this repository (check `git log --oneline -10` for language and format): a short subject line in the imperative, then a body that says what changed in each file and why. Take the developer's note into account.
4. Run one `git commit`. Do not amend (that needs `/collab:git commit --amend`) and do not push (that needs `/collab:push`): the plugin rejects both.
5. Show the developer the commit hash and the message.
