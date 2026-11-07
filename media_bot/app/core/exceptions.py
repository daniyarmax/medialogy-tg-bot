class MediaBotError(Exception):
    """Base for all expected application errors.

    `user_message` is what gets shown in Telegram; the exception's own
    str()/traceback is what goes to logs. Handlers must never leak the
    latter to a chat.
    """

    user_message: str = "Something went wrong. Please try again later."

    def __init__(self, detail: str | None = None, *, user_message: str | None = None) -> None:
        if user_message is not None:
            self.user_message = user_message
        # Set self.user_message *before* this, since str(exc)/the traceback
        # falls back to it when no technical `detail` is given - otherwise
        # a custom user_message passed via kwarg never shows up in logs,
        # only the generic class-level default does.
        super().__init__(detail or self.user_message)


class UnsupportedPlatformError(MediaBotError):
    user_message = "This link isn't from a platform I support yet."


class SourceValidationError(MediaBotError):
    user_message = "That link doesn't look safe or valid. Please send a direct public link."


class FileTooLargeError(MediaBotError):
    user_message = "That file is too large for me to process."


class DurationExceededError(MediaBotError):
    user_message = "That video/audio is too long for me to process."


class ProcessingTimeoutError(MediaBotError):
    user_message = "Processing took too long and was stopped. Please try a shorter file."


class DiskSpaceError(MediaBotError):
    user_message = "I'm low on storage right now — please try again in a bit."


class DownloadFailedError(MediaBotError):
    user_message = "I couldn't download that. The link may be private, deleted, or unavailable."


class NetworkTimeoutError(DownloadFailedError):
    user_message = "The download timed out. Please try again."


class FFmpegError(MediaBotError):
    user_message = "I couldn't process that media file."


class TaskCancelledError(MediaBotError):
    user_message = "Cancelled."


class RateLimitExceededError(MediaBotError):
    user_message = "You're sending requests too fast. Please slow down a bit."
