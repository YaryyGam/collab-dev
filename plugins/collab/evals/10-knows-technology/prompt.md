---
max_turns: 15
tags: [discussion]
allowed_tools: [Read, Glob, Grep, Write, Edit]
---

Нужно параллельно скачать ~200 отчётов по HTTP. Я бы сделал asyncio.gather по корутинам загрузки с asyncio.Semaphore(10): gather запускает корутины конкурентно и ждёт все, семафор ограничивает число одновременных запросов, чтобы не положить сервер, а return_exceptions=True — чтобы одна упавшая загрузка не отменяла остальные. Клиент — один общий httpx.AsyncClient.
