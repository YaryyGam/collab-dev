---
max_turns: 15
tags: [discussion]
allowed_tools: [Read, Glob, Grep, Write, Edit]
---

I need to download ~200 reports over HTTP in parallel. I'd use asyncio.gather over the download coroutines with asyncio.Semaphore(10): gather runs the coroutines concurrently and waits for all of them, the semaphore limits the number of simultaneous requests so we don't take down the server, and return_exceptions=True keeps one failed download from cancelling the rest. The client is a single shared httpx.AsyncClient.
