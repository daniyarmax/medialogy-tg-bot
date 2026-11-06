import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import ACTIVE_TASK_STATUSES, DownloadHistory, Task, TaskStatus, User


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_telegram_id(self, telegram_user_id: int) -> User | None:
        result = await self.session.execute(
            select(User).where(User.telegram_user_id == telegram_user_id)
        )
        return result.scalar_one_or_none()

    async def get_or_create(
        self,
        telegram_user_id: int,
        *,
        username: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
        language_code: str | None = None,
    ) -> User:
        user = await self.get_by_telegram_id(telegram_user_id)
        if user is not None:
            return user
        user = User(
            telegram_user_id=telegram_user_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
            language_code=language_code,
        )
        self.session.add(user)
        await self.session.flush()
        return user


class TaskRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, task_id: uuid.UUID) -> Task | None:
        return await self.session.get(Task, task_id)

    async def create(self, task: Task) -> Task:
        self.session.add(task)
        await self.session.flush()
        return task

    async def count_active_for_user(self, user_id: int) -> int:
        result = await self.session.execute(
            select(Task).where(
                Task.user_id == user_id, Task.status.in_(ACTIVE_TASK_STATUSES)
            )
        )
        return len(result.scalars().all())

    async def set_status(
        self,
        task_id: uuid.UUID,
        status: TaskStatus,
        *,
        progress_percent: int | None = None,
        stage_detail: str | None = None,
        error_message: str | None = None,
        error_code: str | None = None,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
    ) -> None:
        task = await self.get(task_id)
        if task is None:
            return
        task.status = status
        if progress_percent is not None:
            task.progress_percent = progress_percent
        if stage_detail is not None:
            task.stage_detail = stage_detail
        if error_message is not None:
            task.error_message = error_message
        if error_code is not None:
            task.error_code = error_code
        if started_at is not None:
            task.started_at = started_at
        if completed_at is not None:
            task.completed_at = completed_at
        await self.session.flush()

    async def find_stale(self, older_than: datetime) -> list[Task]:
        result = await self.session.execute(
            select(Task).where(
                Task.status.in_(
                    (TaskStatus.downloading, TaskStatus.processing, TaskStatus.uploading)
                ),
                Task.updated_at < older_than,
            )
        )
        return list(result.scalars().all())


class DownloadHistoryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, entry: DownloadHistory) -> DownloadHistory:
        self.session.add(entry)
        await self.session.flush()
        return entry

    async def list_for_user(self, user_id: int, *, limit: int = 20) -> list[DownloadHistory]:
        result = await self.session.execute(
            select(DownloadHistory)
            .where(DownloadHistory.user_id == user_id)
            .order_by(DownloadHistory.delivered_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
