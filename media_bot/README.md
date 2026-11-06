# Media Bot — Telegram Video Downloader & Audio Extractor

A Telegram bot that downloads video from YouTube, Instagram, TikTok, Facebook, X/Twitter, and
Reddit (via `yt-dlp`), and extracts audio in MP3/WAV/M4A/FLAC/OPUS (via FFmpeg) — built to handle
multi-hour podcasts and multi-gigabyte files, not just short clips.

> **Status:** under active development. See `../IMPLEMENTATION_STATUS.md` at the repo root for
> what is actually built and verified so far. This README will be filled in phase by phase as the
> corresponding functionality lands — sections below are placeholders until then.

## Stack

Python 3.12, aiogram 3, yt-dlp, FFmpeg/ffprobe, Celery, Redis, PostgreSQL, SQLAlchemy (async),
Alembic, Docker Compose.

## Setup

_To be written in Phase 1 (environment/config) and Phase 7 (deployment)._

## Getting a Telegram bot token

Message [@BotFather](https://t.me/BotFather) on Telegram, send `/newbot`, follow the prompts, and
copy the token it gives you into your `.env` file as `TELEGRAM_BOT_TOKEN`. Never commit this
token — `.env` is git-ignored.

## Large files: Local Bot API Server

The standard Telegram Bot API caps uploads at 50MB and downloads at 20MB. For multi-GB podcasts
and videos, this project supports switching to a self-hosted Local Bot API Server (raises the
upload cap to 2000MB). See `IMPLEMENTATION_STATUS.md` / Phase 7 docs for setup once that phase
lands — it additionally requires a personal `api_id`/`api_hash` pair from
https://my.telegram.org/apps.

## Development

_To be written as each phase lands._
