# Media Bot — Telegram Video Downloader & Audio Extractor

A Telegram bot that downloads video from YouTube, Instagram, TikTok, Facebook, X/Twitter, and
Reddit (via `yt-dlp`), and extracts audio in MP3/WAV/M4A/FLAC/OPUS (via FFmpeg) — built to handle
multi-hour podcasts and multi-gigabyte files, not just short clips, with background processing
(Celery) so the bot never blocks while a download/extraction runs.

> See `../IMPLEMENTATION_STATUS.md` at the repo root for what's actually been built and verified,
> phase by phase, with real numbers and real bugs found along the way.

## Stack

Python 3.12, aiogram 3, yt-dlp, FFmpeg/ffprobe, Celery, Redis, PostgreSQL, SQLAlchemy (async),
Alembic, Docker Compose.

## Getting a Telegram bot token

Message [@BotFather](https://t.me/BotFather) on Telegram, send `/newbot`, follow the prompts, and
copy the token it gives you into `.env` as `TELEGRAM_BOT_TOKEN`. Never commit this token — every
`.env*` file except `.env.example` is git-ignored.

## Local development (without Docker)

1. **Python 3.12** venv: `python3.12 -m venv .venv && source .venv/bin/activate && pip install -r requirements-dev.txt`
2. **FFmpeg**: `brew install ffmpeg` (macOS) or your distro's package. Required for the audio
   pipeline — yt-dlp also shells out to it for merging separate video+audio streams.
3. **Postgres + Redis**: either run them locally (e.g. `brew install postgresql@16 redis` +
   `brew services start postgresql@16 redis`) or just use Docker for only those two:
   `docker compose up -d postgres redis` (note: the default compose file doesn't publish their
   ports to the host — add `ports: ["5432:5432"]` / `["6379:6379"]` back temporarily if you want
   to run the app on the host against them, or run everything in Docker instead — see below).
4. Copy `.env.example` to `.env` and fill in `TELEGRAM_BOT_TOKEN`, `POSTGRES_PASSWORD`, and a
   `DATABASE_URL`/`REDIS_HOST` pointing at wherever Postgres/Redis actually are reachable
   (`localhost` for host-based dev).
5. `alembic upgrade head` to create the schema.
6. Run the bot: `python -m app.main`. Run a worker (separate terminal):
   `celery -A app.workers.celery_app worker -Q downloads,processing,maintenance --loglevel=INFO`.
   **On macOS**, Celery's default `prefork` pool needs billiard forced to use `fork` instead of
   the platform's `spawn` default — this is already handled automatically in
   `app/workers/celery_app.py`, so no extra flags are needed; if you ever see
   `ValueError: not enough values to unpack (expected 3, got 0)` on worker startup, that's this
   exact issue resurfacing (e.g. after a billiard upgrade changes its internals).

Run tests with `pytest` (runs `tests/unit` + `tests/integration` against a real local Postgres —
set `DATABASE_URL` accordingly first). The load test (`tests/load/`) is excluded by default; run
it explicitly with `pytest tests/load -v`.

## Docker deployment

The project uses **two separate env files**, not one:

- **`.env`** — for running the app directly on your host (local dev). Points at Postgres/Redis via
  `localhost`.
- **`.env.docker`** — for `docker compose`. Points at Postgres/Redis via their Compose service
  names (`postgres`, `redis`), since containers reach each other over the Compose network, not
  `localhost`. Copy `.env.example` to `.env.docker` and set `POSTGRES_HOST=postgres`,
  `REDIS_HOST=redis`, `STORAGE_ROOT=/storage` (absolute, matching the containers' filesystem) and
  the corresponding `DATABASE_URL`/`CELERY_BROKER_URL`/etc. `docker-compose.yml` already points
  every service's `env_file:` at `.env.docker`.

Bring the stack up:

```sh
docker compose up -d --build postgres redis bot celery-worker-download celery-worker-processing celery-beat
docker compose exec bot python -m alembic upgrade head   # first run / after a schema change
```

Note: `postgres`/`redis` deliberately don't publish ports to the host (only containers on the
Compose network need to reach them, and not exposing a DB port is better practice anyway) — so
this won't conflict with a Postgres/Redis you already have running locally for other work.

Check everything's healthy: `docker compose ps` (postgres/redis show `(healthy)`; the others show
`Up`). Tail logs with `docker compose logs -f <service>`.

To fully reset (fresh volumes, re-run migrations from scratch):

```sh
docker compose down -v
docker compose up -d --build postgres redis bot celery-worker-download celery-worker-processing celery-beat
docker compose exec bot python -m alembic upgrade head
```

### Scaling workers

`celery-worker-download` and `celery-worker-processing` are separate services precisely so a
long transcode can't starve a quick download (or vice versa) — bump `--concurrency` in their
`command:` in `docker-compose.yml`, or run multiple replicas of either with
`docker compose up -d --scale celery-worker-download=3` (remove the fixed container name if you
do this often).

## Large files: Local Bot API Server

The **Standard Bot API** (`api.telegram.org`, the default) caps uploads at **50MB** and downloads
at **20MB**. For multi-GB podcasts and videos, switch to a self-hosted **Local Bot API Server**,
which raises the upload cap to **2000MB** (with downloads effectively unlimited, and a hard 4000MB
ceiling on any single request regardless of mode).

1. Get your own `api_id`/`api_hash` from <https://my.telegram.org/apps> (log in with a personal
   Telegram account — this is separate from, and unrelated to, your bot token).
2. In `.env.docker`, set `TELEGRAM_API_MODE=local`, `LOCAL_BOT_API_ID=<api_id>`,
   `LOCAL_BOT_API_HASH=<api_hash>`.
3. Start the local API server alongside everything else:
   `docker compose --profile local-api up -d --build`
4. Restart the bot/worker services so they pick up the new `TELEGRAM_API_MODE`:
   `docker compose restart bot celery-worker-download celery-worker-processing`

This mode shares a Docker volume between the local API server and the bot/workers, so large files
can be handed off by local path instead of re-uploaded over loopback HTTP.

> **Not yet live-verified** in this project (needs your own `my.telegram.org` credentials) — the
> code path is implemented and the Standard-API path has been extensively live-tested, but switch
> carefully and watch the logs the first time you use `local` mode.

## Limits

All configurable via `.env`/`.env.docker`:

| Variable | Default | What it governs |
|---|---|---|
| `MAX_FILE_SIZE_MB` | 1900 | Download size ceiling (kept under the Local API's 2000MB cap) |
| `MAX_DURATION_SECONDS` | 18000 (5h) | Longest video/audio accepted |
| `MAX_PROCESSING_TIME_SECONDS` | 3600 (1h) | Wall-clock timeout per download/extraction |
| `MAX_CONCURRENT_TASKS_PER_USER` | 2 | Per-user admission-control limit |
| `MIN_FREE_DISK_MB` | 2048 | Disk-space floor checked before starting work |
| `PROGRESS_POLL_INTERVAL_SECONDS` | 2.5 | How often the bot polls Redis for progress |
| `MIN_EDIT_INTERVAL_SECONDS` | 3 | Minimum gap between progress-message edits |

The effective upload ceiling also depends on `TELEGRAM_API_MODE` (50MB cloud / 2000MB local) —
whichever is smaller between that and `MAX_FILE_SIZE_MB` wins.

## Backup & restore

```sh
./scripts/backup_db.sh                          # writes backups/media_bot_<timestamp>.dump
./scripts/restore_db.sh backups/media_bot_...dump  # prompts for confirmation before restoring
```

Both read `DATABASE_URL` from `.env` (or `.env.docker` if you're targeting the containerized DB —
copy whichever one is relevant to `.env` first, or point `DATABASE_URL` at `localhost` if
Postgres's port happens to be published). `backups/` is git-ignored.

To manually trigger the stale-task reconciliation sweep (normally run automatically by Celery
Beat every 5 minutes) — useful right after restarting a worker:

```sh
python -m scripts.reconcile_tasks
```

## Troubleshooting

- **`docker compose up` hangs or can't connect to the daemon** — Docker Desktop itself isn't
  running or is stuck. Quit it from the menu-bar icon and relaunch; wait for the icon to stop
  animating before retrying.
- **`celery-beat` crash-loops with `Permission denied: 'celerybeat-schedule'`** — you're running
  an older worker image built before `/app` was chowned to the non-root `appuser`; rebuild with
  `docker compose build --no-cache celery-beat`.
- **`ValueError: not enough values to unpack (expected 3, got 0)` from a Celery worker on macOS**
  — billiard defaulted to `spawn` instead of `fork`; see the local-dev section above. Already
  handled in `celery_app.py`, but worth knowing if you ever see it again after a dependency bump.
- **A video downloads but Telegram shows it as audio-only / black screen** — almost certainly a
  VP9-in-MP4 compatibility issue with the Telegram client. The quality picker already prefers
  H.264 and should avoid this; if you see it again, check which `vcodec` the selected format
  actually used.
- **yt-dlp suddenly can't extract a popular site at all** — yt-dlp needs frequent updates to
  track upstream platform changes; bump the pin in `requirements.txt`/`pyproject.toml`.
