from app.core.exceptions import FileTooLargeError, MediaBotError


def test_custom_user_message_shows_in_str_when_no_detail_given() -> None:
    # Real bug this guards against: str(exc)/the traceback previously
    # always showed the generic class-level default, even when a specific
    # user_message was passed, because self.user_message was updated
    # *after* super().__init__() already used the old value.
    exc = FileTooLargeError(user_message="The video is 823MB, over the 50MB limit.")
    assert str(exc) == "The video is 823MB, over the 50MB limit."
    assert exc.user_message == "The video is 823MB, over the 50MB limit."


def test_detail_takes_priority_over_default_for_str_when_no_user_message_given() -> None:
    exc = FileTooLargeError("yt-dlp exited 1: some technical stderr")
    assert str(exc) == "yt-dlp exited 1: some technical stderr"
    # .user_message still falls back to the safe, generic default for display.
    assert exc.user_message == "That file is too large for me to process."


def test_base_error_defaults_to_generic_message_with_no_args() -> None:
    exc = MediaBotError()
    assert str(exc) == "Something went wrong. Please try again later."
    assert exc.user_message == "Something went wrong. Please try again later."
