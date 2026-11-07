"""Decides when a progress update is worth sending as a Telegram message
edit, and renders the user-facing progress text.

Kept framework-agnostic (no aiogram/Bot references) specifically so it's
testable by feeding it a sequence of fake snapshots and asserting how many
times it says to actually send — Telegram rate-limits `editMessageText` per
chat, and `MessageNotModified` errors are wasted calls, so both guards
(text changed AND enough time elapsed) matter.
"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ProgressSnapshot:
    stage: str
    percent: float | None = None
    speed_text: str | None = None
    eta_text: str | None = None
    extra: str | None = None


def render_progress_text(snapshot: ProgressSnapshot, *, bar_width: int = 20) -> str:
    lines = [snapshot.stage]
    if snapshot.percent is not None:
        pct = min(100.0, max(0.0, snapshot.percent))
        filled = int(bar_width * pct / 100)
        bar = "█" * filled + "░" * (bar_width - filled)
        lines += ["", f"Progress: {pct:.0f}%", bar]
    if snapshot.speed_text:
        lines += ["", f"Speed: {snapshot.speed_text}"]
    if snapshot.eta_text:
        lines.append(f"Estimated time: {snapshot.eta_text}")
    if snapshot.extra:
        lines.append(snapshot.extra)
    return "\n".join(lines)


class ProgressMessageThrottler:
    def __init__(self, *, min_interval_seconds: float) -> None:
        self._min_interval_seconds = min_interval_seconds
        self._last_sent_text: str | None = None
        self._last_sent_at: float | None = None

    def should_send(self, text: str, *, now: float) -> bool:
        if text == self._last_sent_text:
            return False
        if self._last_sent_at is not None and (now - self._last_sent_at) < self._min_interval_seconds:
            return False
        return True

    def record_sent(self, text: str, *, now: float) -> None:
        self._last_sent_text = text
        self._last_sent_at = now
