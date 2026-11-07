# Tests

Three tiers, each with a different purpose and a different run command.

## `tests/unit/`

Pure logic, no network, no real subprocess calls, no database. Mocks the boundary (subprocess
calls, Redis, Telegram) where needed. Fast — the whole suite runs in well under a second.

```sh
pytest tests/unit -v
```

## `tests/integration/`

Real dependencies, no mocking of the thing actually being tested:

- `test_repositories.py`, `test_task_service.py` — real local Postgres (reads `DATABASE_URL`
  from your `.env`).
- `test_rate_limit_middleware.py` — real local Redis.
- `test_celery_tasks.py` — real yt-dlp, real ffmpeg, real Postgres. Only Telegram delivery
  (`Bot.send_video`/`send_audio`) is mocked, specifically so this suite never spams a real chat
  on every run. Needs network access (it probes/downloads a real short public YouTube video) and
  `ffmpeg`/`yt-dlp` on `PATH`.

```sh
pytest tests/integration -v
```

`pytest` with no path runs both of the above (configured via `testpaths` in `pyproject.toml`).

## `tests/load/`

Long-running, resource-measuring tests — not part of the default run (excluded via `testpaths`).
`test_audio_memory.py` generates synthetic audio on the fly (via `ffmpeg -f lavfi`, never
downloaded or checked in) to prove `audio_extractor` doesn't buffer its source in memory: it
measures the real ffmpeg subprocess's peak RSS for a 10-second clip vs. a 2-hour one and asserts
they're comparable. Takes ~30 seconds (most of it spent generating the 2-hour synthetic file).

```sh
pytest tests/load -v
```

## Running everything

```sh
pytest                 # tests/unit + tests/integration (the default)
pytest tests/load -v   # the load test, separately
```
