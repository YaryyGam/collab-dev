# Interaction examples

All examples are **real Claude responses** from test runs (manual and `claude plugin eval`, October 2026, Claude Code 2.1.295, `collaborative` mode). The responses are shortened (`…`) but not rewritten. The numbers match the scenarios from the spec and the `plugins/collab/evals/` directories.

---

## 11 · "Just write the code": with and without the plugin

> **Developer:** Create a slugify.py file with a slugify(title) function that turns an article title into a URL slug. Just write the code right away, there's nothing to discuss.

<table><tr><th>With the plugin</th><th>Without the plugin</th></tr><tr><td valign="top">

Writing files is blocked right now: the collab plugin is in the `discussing` stage until the approach is agreed. I won't work around the block. Options:

- **Skip the discussion for this task:** `/collab:skip [reason]`. After that I'll write the code right away, briefly explain decisions along the way and do a short review at the end.
- **Turn the mode off for the rest of the session:** `/collab:off [reason]`.
- **Agree quickly:** tell me in a sentence or two how you would build the slug and why. For example, with `unicodedata` + a regex, with `python-slugify`, or with manual transliteration of Cyrillic.

One thing depends on your answer: what to do with Cyrillic in titles…

</td><td valign="top">

Created `slugify.py` with a `slugify(title, max_length=80)` function. I haven't run it…

- **Cyrillic:** transliterates it to Latin…
- **Diacritics:** strips them…
- **Length:** truncates the slug to 80 characters…

</td></tr></table>

With the plugin, `slugify.py` was **not created**: the write was blocked by the hook, not by the model. Without the plugin, Claude made every decision for the developer.

---

## 01 · Simple task: brief, no lecture

> **Developer:** Rename the get_usr function to get_user in users.py and everywhere it's used.

> **Claude:** I looked at the project: it has only two files, and `get_usr` appears in three places: `users.py:1`, `app.py:1`, `app.py:4`…
>
> How to do this depends on the answer to one question: could anything **outside** this repository import `get_usr`, for example another service or a script? There are two options:
> 1. Simply rename the function in all three places.
> 2. Rename it and temporarily keep the old name as an alias so external code doesn't break.
>
> Which option would you choose and why? One sentence is enough. … If such a small task doesn't need a discussion, you can skip it with `/collab:skip [reason]`.

---

## 03 · The developer proposes an incorrect solution

> **Developer:** …I'd store passwords in the users table as is, in plain text, and compare strings with == on login. That's the fastest and easiest to debug.

> **Claude:**
> ## Solution rating: Incorrect
> The scheme works, but it has a serious security flaw…
> 1. **A database leak immediately exposes every password**… People reuse passwords…
> 2. **Comparing with `==` opens up a timing attack**…
>
> ## Reasoning rating
> - "**Fastest**": true, but the difference is 2–3 lines…
> - "**Easiest to debug, you can see everyone's password right away**": this is exactly the mistake. Neither the developer nor the admin needs to see users' passwords…
> - What's missing: a threat model…
>
> ## Alternative: a salted hash via a dedicated function
> ```
> on registration:
>     hash = argon2/bcrypt(password)     — the salt is generated and stored inside the hash string
> on login:
>     verify(entered_password, hash)     — constant-time comparison
>     if not found or no match — the same error "invalid login or password"
> ```
> …Another alternative under different conditions: **don't store passwords at all** (OAuth, magic link)…
>
> To propose a concrete implementation I need to know the **stack**… And how do you see the session after login: a cookie session or a token (JWT)? Why that one?

The solution rating ("Incorrect") and the reasoning rating are kept separate. Each of the developer's arguments is examined on its own.

---

## 04 · The solution is right, but the developer doesn't understand why

> **Developer:** …I'd do list(dict.fromkeys(emails)), I saw it on StackOverflow. But honestly, I don't understand why it works and why not just set().

> **Claude:**
> ## Why `list(dict.fromkeys(emails))` works
> 1. **Dictionary keys are unique**…
> 2. **A dictionary remembers insertion order.** Since Python 3.7 this is a language guarantee. And re-inserting an existing key **does not move** it…
> 3. **`list(d)` iterates over the keys** in exactly that order.
> ```
> emails = [b, a, b, c, a]
> dict: b → added; a → added; b → already there, skip; c → added; a → skip
> keys in order: [b, a, c]
> ```
> ## Why not `set()`
> …for strings the hash is also randomized on every Python run (`PYTHONHASHSEED`)… This kind of bug is especially nasty: it may not show up in tests.
>
> **Alternative**: an explicit loop with a `seen` set… lets you compare addresses **by a normalized key**… `dict.fromkeys` treats `Ivan@Mail.com` and `ivan@mail.com` as different addresses.
>
> - Where do the addresses come from, and should `Ivan@Mail.com` and `ivan@mail.com` count as the same address?

---

## 05 · The developer doesn't know how to solve it

> **Developer:** We need our HTTP API not to fall over when one client sends too many requests. I have no idea how this is done or where to start.

> **Claude:** …This is called **rate limiting**.
>
> A bar with a bouncer: "no more than 5 drinks per hour for anyone." The sixth order is refused, but the bar keeps serving everyone else.
> ```
> a request arrives:
>     figure out which client it's from
>     look at how many requests this client has made "recently"
>     if the limit is exceeded — immediately respond 429 Too Many Requests, do no work
>     otherwise — count the request and handle it as usual
> ```
> ## Questions that will shape the implementation
> …(how to identify the client, one server or several, what limits)…

No ready-made code: the concept is explained with an everyday analogy and pseudocode, followed by guiding questions.

---

## 10 · The developer already knows the technology

> **Developer:** …asyncio.gather over the download coroutines with asyncio.Semaphore(10): gather runs the coroutines concurrently and waits for all of them, the semaphore limits the number of simultaneous requests… and return_exceptions=True so that one failed download doesn't cancel the rest.

> **Claude:**
> ## Solution rating: Good
> …One correction to the reasoning and a couple of details that are easy to get wrong.
>
> **Correction about `return_exceptions`.** Without this flag `gather` **does not cancel** the other coroutines. It raises the first exception immediately, while the other tasks keep running in the background unsupervised… Your conclusion is right: the flag is needed. But the reason is different… Cancelling on the first error is, on the contrary, what `asyncio.TaskGroup` does.
>
> **What's easy to get wrong:**
> 1. **Where to acquire the semaphore.** `async with sem:` must be inside the download coroutine…
> 2. **Why `httpx.Limits(max_connections=10)` alone won't do**… they hit the `pool` timeout… `PoolTimeout`…
>
> ## Alternative: a worker pool with `asyncio.Queue`
> …**When it's better:** with tens of thousands of URLs or a streaming source. For 200 it's unnecessary complexity, so I recommend your option.

The basics (coroutines, the event loop, what a semaphore is) are not explained again. Instead, an inaccuracy in the reasoning is found: the solution is right, but one of its justifications is wrong. This shows that the solution and the reasoning are rated separately.

---

## 09 · Works, but scales poorly

> **Developer:** …~300,000 users… I'd load everyone into a list and compare each one with every other using two nested loops.

> **Claude:**
> ## Solution rating: Suboptimal
> The result will be correct, but speed is limited by the data volume:
> - It takes n·(n−1)/2 ≈ **4.5·10¹⁰ comparisons** for 300,000 records.
> - In Python that's **hours**…
> - Growth is quadratic. With 600,000 users the time grows 4×, not 2×…
>
> **"Definitely works": only for exact string matches.** `Ivan@Mail.ru` and `ivan@mail.ru ` will be considered different…
>
> **1. Grouping by key (hash table): O(n)**… **2. Delegate to the DB: `GROUP BY`**…
>
> Nested loops are only suitable for a one-off run on a small sample.
>
> 3. Which option do you choose and why? How do you think a dictionary finds duplicates without comparing every pair?

---

## Implementation after agreement: summary check, card, final review

> **Developer:** `/collab:agree move the email check from api.py and cli.py into a new validators.py module… take the behavior from api.py`

Claude first **checked the summary** against the code and found a significant gap (scenario 06, a run with an incomplete summary):

> The summary matches the code… But it doesn't account for two things, and it's better to decide them before writing.
>
> **1. A bug in `api.py` will carry over to the CLI.** In `api.py:6` the address is checked before `.lower()`, and the TLD part of the regex `[a-z]{2,}` allows only lowercase letters. So `user@example.COM` is currently rejected by the API… The CLI currently accepts such an address, and after the move it will start rejecting it.
> - **(a)** Move it as is… **(b)** Add `re.IGNORECASE` right away…

A card for the new function **before the write** (scenario 06, another run):

> #### 🧩 `is_valid_email(email) -> bool` · validators.py · new
>
> **Why:** a single source of truth for the "does this look like an email" rule, so the two copies no longer diverge.
>
> **Parameters**
> | Parameter | Type | Comes from | Purpose |
> |---|---|---|---|
> | `email` | `str` | from `api.register` (already after `strip()`) or from `argv` in the CLI | the string to check |
>
> **Returns:** `True` or `False`. The function raises no exceptions: what to do with an invalid address is up to the calling code…
>
> **Uses**
> | Function / construct | What it does here | Why this one |
> |---|---|---|
> | `re.match` + the same regex as in `api.py` | checks the string against the pattern | `re.match`, not `fullmatch`, so the behavior matches the API byte for byte |
>
> **Alternative:** also move `strip()`/`lower()` into the function. I didn't: that's normalization, not validation…

A final review with honest verification (manual run, pagination):

> ### Verification
> - **Tests were not run:** running `pytest` required permission and was not done. To check, run `python3 -m pytest -q` in the project directory.
> - **What's missing:** type checks… the total number of users (`total`) in the response…
>
> **Comprehension question.** If a user is added or deleted while a client is paging through with `offset`, what will the client see, and why does a cursor protect against that?

> ⚠️ Not everything is perfect: in some runs Claude wrote several files in a row and explained them only after the whole batch, and sometimes skipped the "in plain words" pseudocode. See [ACCEPTANCE.md](ACCEPTANCE.md) and [LIMITATIONS.md](LIMITATIONS.md) #14.
