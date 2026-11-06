import enum
import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, Index, SmallInteger, String, Text, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class TaskOperation(str, enum.Enum):
    download_video = "download_video"
    extract_audio = "extract_audio"
    probe_metadata = "probe_metadata"


class TaskStatus(str, enum.Enum):
    pending = "Pending"
    downloading = "Downloading"
    processing = "Processing"
    uploading = "Uploading"
    completed = "Completed"
    failed = "Failed"
    cancelled = "Cancelled"


ACTIVE_TASK_STATUSES = (
    TaskStatus.pending,
    TaskStatus.downloading,
    TaskStatus.processing,
    TaskStatus.uploading,
)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)
    username: Mapped[str | None] = mapped_column(String(255))
    first_name: Mapped[str | None] = mapped_column(String(255))
    last_name: Mapped[str | None] = mapped_column(String(255))
    language_code: Mapped[str | None] = mapped_column(String(10))
    is_blocked: Mapped[bool] = mapped_column(default=False, nullable=False)

    default_audio_format: Mapped[str] = mapped_column(String(10), default="mp3", nullable=False)
    default_audio_bitrate: Mapped[str] = mapped_column(String(10), default="192k", nullable=False)
    default_video_quality: Mapped[str] = mapped_column(
        String(20), default="best_under_limit", nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    tasks: Mapped[list["Task"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    download_history: Mapped[list["DownloadHistory"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class Task(Base):
    __tablename__ = "tasks"
    __table_args__ = (
        # Per-user admission-control lookup (task_service.py) and the
        # stale-task reconciliation scan (reconcile_stale_tasks) both only
        # ever care about the "currently active" subset of tasks, so both
        # indexes are partial to stay small as completed/failed tasks pile up.
        Index(
            "idx_tasks_user_active",
            "user_id",
            "status",
            postgresql_where=text(
                "status IN ('Pending', 'Downloading', 'Processing', 'Uploading')"
            ),
        ),
        Index(
            "idx_tasks_updated_at_active",
            "updated_at",
            postgresql_where=text("status IN ('Downloading', 'Processing', 'Uploading')"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    celery_task_id: Mapped[str | None] = mapped_column(String(255))
    operation: Mapped[TaskOperation] = mapped_column(
        Enum(TaskOperation, name="task_operation", native_enum=True), nullable=False
    )
    source_url: Mapped[str | None] = mapped_column(Text)
    source_file_id: Mapped[str | None] = mapped_column(String(255))
    platform: Mapped[str | None] = mapped_column(String(50))
    requested_format: Mapped[str | None] = mapped_column(String(20))
    requested_bitrate: Mapped[str | None] = mapped_column(String(10))

    status: Mapped[TaskStatus] = mapped_column(
        Enum(
            TaskStatus,
            name="task_status",
            native_enum=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        default=TaskStatus.pending,
        nullable=False,
        index=True,
    )
    progress_percent: Mapped[int] = mapped_column(SmallInteger, default=0, nullable=False)
    stage_detail: Mapped[str | None] = mapped_column(String(255))

    result_file_path: Mapped[str | None] = mapped_column(Text)
    result_file_size_bytes: Mapped[int | None] = mapped_column(BigInteger)

    error_message: Mapped[str | None] = mapped_column(Text)
    error_code: Mapped[str | None] = mapped_column(String(50))

    retry_count: Mapped[int] = mapped_column(SmallInteger, default=0, nullable=False)
    max_retries: Mapped[int] = mapped_column(SmallInteger, default=4, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped["User"] = relationship(back_populates="tasks")
    download_history: Mapped["DownloadHistory | None"] = relationship(
        back_populates="task", cascade="all, delete-orphan", uselist=False
    )


class DownloadHistory(Base):
    __tablename__ = "download_history"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, unique=True
    )

    title: Mapped[str | None] = mapped_column(String(500))
    platform: Mapped[str | None] = mapped_column(String(50))
    operation: Mapped[TaskOperation] = mapped_column(
        Enum(TaskOperation, name="task_operation", native_enum=True, create_type=False),
        nullable=False,
    )
    output_format: Mapped[str | None] = mapped_column(String(20))
    file_size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    duration_seconds: Mapped[int | None] = mapped_column(BigInteger)

    storage_path: Mapped[str | None] = mapped_column(Text)
    telegram_file_id: Mapped[str | None] = mapped_column(String(255))

    delivered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped["User"] = relationship(back_populates="download_history")
    task: Mapped["Task"] = relationship(back_populates="download_history")
