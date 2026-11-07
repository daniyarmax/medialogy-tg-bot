from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message

from app.bot.keyboards.main_menu import BTN_MY_DOWNLOADS
from app.database.models import TaskStatus

router = Router(name="status")


@router.message(Command("status"))
async def cmd_status(message: Message, task_repo, user_repo) -> None:
    user = await user_repo.get_by_telegram_id(message.from_user.id)
    if user is None:
        await message.answer("You don't have any tasks yet.")
        return

    active = await task_repo.list_active_for_user(user.id)
    if not active:
        await message.answer("You have no active tasks right now.")
        return

    lines = ["<b>Your active tasks:</b>"]
    for task in active:
        label = task.requested_format or task.operation.value
        lines.append(f"• <code>{task.id}</code> — {task.operation.value} ({label}) — {task.status.value}")
    await message.answer("\n".join(lines))


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, task_repo, user_repo) -> None:
    user = await user_repo.get_by_telegram_id(message.from_user.id)
    if user is None:
        await message.answer("You don't have anything to cancel.")
        return

    active = await task_repo.list_active_for_user(user.id)
    if not active:
        await message.answer("You don't have any active tasks to cancel.")
        return

    most_recent = active[0]
    await task_repo.set_status(most_recent.id, TaskStatus.cancelled)
    await message.answer(f"Cancelled task <code>{most_recent.id}</code>.")


@router.message(F.text == BTN_MY_DOWNLOADS)
async def my_downloads(message: Message, history_repo, user_repo) -> None:
    user = await user_repo.get_by_telegram_id(message.from_user.id)
    if user is None:
        await message.answer("You haven't downloaded anything yet.")
        return

    entries = await history_repo.list_for_user(user.id, limit=10)
    if not entries:
        await message.answer("You haven't downloaded anything yet.")
        return

    lines = ["<b>Your recent downloads:</b>"]
    for entry in entries:
        lines.append(f"• {entry.title or 'Untitled'} ({entry.output_format or entry.operation.value})")
    await message.answer("\n".join(lines))
