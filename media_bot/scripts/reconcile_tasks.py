#!/usr/bin/env python
"""Manual entry point for the stale-task reconciliation sweep - the same
logic Celery Beat runs automatically every 5 minutes
(`tasks.reconcile_stale_tasks`), exposed here for an operator to run
by hand (e.g. right after restarting a worker, to immediately re-queue
anything that was stuck rather than waiting for the next scheduled tick).

Usage: python -m scripts.reconcile_tasks   (from the project root)
"""

import asyncio

from app.workers.tasks import reconcile_stale_tasks_async


async def main() -> None:
    result = await reconcile_stale_tasks_async()
    print(f"Re-queued: {result['reenqueued']}, failed (retries exhausted): {result['failed']}")


if __name__ == "__main__":
    asyncio.run(main())
