---
name: explain
description: The developer doesn't know how to solve the task — Claude analyzes it and proposes several solution options with their trade-offs, libraries and technologies; writing stays blocked until /collab:agree
argument-hint: [task or the part you're stuck on]
disable-model-invocation: true
---

The developer doesn't know which solution to choose or how to approach the problem, and asks you to lay out the options yourself. Focus: $ARGUMENTS

If the focus is empty, use the task currently under discussion. If there is no such task, ask in one sentence what to solve and stop.

Do not write or change any files: this is still the discussion stage, and writing stays blocked until the developer runs `/collab:agree`.

1. **Study the project first** (see "Existing project" in the rules): stack, existing patterns, dependencies already in use, and code that can be reused. Base the options on this project, not on an abstract one.
2. **The task in 2–4 lines:** how you understood it, and the constraints and assumptions that actually affect the choice (data volume, load, who calls the code, what already exists). If a missing fact would change the choice, name it and say which option it would favor; don't invent it.
3. **2–4 substantive options**, from the simplest that works to the more capable ones. Don't pad the list with straw men. For each option:
   - **How it works:** the idea in a few sentences, plus 3–8 lines of pseudocode "in plain words" if the logic is non-trivial.
   - **Libraries and technologies:** what you would use, and for each, why this one, what it gives over the alternative (another library, the standard library, or what the project already uses), and what it costs (a new dependency, infrastructure, a learning curve). Say so explicitly when an option needs nothing new.
   - **Advantages** and **drawbacks** for *this* project.
   - **When it is the right choice:** the conditions or thresholds under which it wins.
   - **Effort:** roughly which files or components it touches.
4. **Comparison:** a short table on only the criteria that actually distinguish the options (complexity, performance, reliability, security, fit with the architecture, testability).
5. **Recommendation with conditions:** "I would choose X because …; if … is expected, then Y". Check your recommendation for overengineering: prefer the simplest option that meets the requirements.
6. **Key concepts:** briefly explain the concepts the developer needs in order to make the choice, using examples from this project. Explain it at a level that helps them choose, not as a lecture.
7. **Hand the choice back:** ask which option the developer picks and why, and remind them to confirm it in their own words: `/collab:agree <which approach and why>`. The restatement is their comprehension check, so don't write it for them.

Size it to the task: for a small task, two options and a few lines each are enough.
