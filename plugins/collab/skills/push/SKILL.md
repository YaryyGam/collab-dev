---
name: push
description: Allow Claude one push — to the given branch, or to the current branch when none is given; never forced
argument-hint: [branch]
disable-model-invocation: true
---

The developer allowed one push. Target branch (empty means the current branch): $ARGUMENTS

1. Show what will be pushed: the current branch and the commits not yet on the remote (`git status -sb`, `git log --oneline @{u}..HEAD` or, without an upstream, the last few commits).
2. Push once:
   - a branch was given: `git push origin HEAD:<branch>` (add `-u` if the branch has no upstream yet);
   - no branch: `git push`, or `git push -u origin HEAD` if the current branch has no upstream.

   The plugin allows only a push into that branch and never `--force`, `+ref` or deleting a branch (those need `/collab:git push …`).
3. Report the remote, the branch and the commits pushed. If the push is rejected (for example, non-fast-forward), do not force it: explain why and suggest what the developer can run (for example `/collab:git rebase origin/<branch>` or `/collab:git push --force-with-lease …`).
