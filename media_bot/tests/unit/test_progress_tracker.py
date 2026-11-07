from app.bot.progress_tracker import ProgressMessageThrottler, ProgressSnapshot, render_progress_text


def test_render_progress_text_includes_bar_and_percent() -> None:
    text = render_progress_text(ProgressSnapshot(stage="Downloading", percent=45.0), bar_width=20)
    assert "Progress: 45%" in text
    assert "█" in text and "░" in text


def test_render_progress_text_omits_bar_when_percent_unknown() -> None:
    text = render_progress_text(ProgressSnapshot(stage="Downloading"))
    assert "Progress:" not in text
    assert text == "Downloading"


def test_render_progress_text_includes_speed_and_eta() -> None:
    text = render_progress_text(
        ProgressSnapshot(stage="Downloading", percent=10, speed_text="4.2 MB/s", eta_text="02:35")
    )
    assert "Speed: 4.2 MB/s" in text
    assert "Estimated time: 02:35" in text


def test_throttler_sends_first_update_always() -> None:
    throttler = ProgressMessageThrottler(min_interval_seconds=3.0)
    assert throttler.should_send("10%", now=0.0) is True


def test_throttler_suppresses_duplicate_text_even_after_interval() -> None:
    throttler = ProgressMessageThrottler(min_interval_seconds=1.0)
    throttler.record_sent("10%", now=0.0)
    assert throttler.should_send("10%", now=10.0) is False


def test_throttler_suppresses_changed_text_within_interval() -> None:
    throttler = ProgressMessageThrottler(min_interval_seconds=3.0)
    throttler.record_sent("10%", now=0.0)
    assert throttler.should_send("20%", now=1.0) is False


def test_throttler_allows_changed_text_after_interval_elapses() -> None:
    throttler = ProgressMessageThrottler(min_interval_seconds=3.0)
    throttler.record_sent("10%", now=0.0)
    assert throttler.should_send("20%", now=3.5) is True


def test_throttler_sequence_only_sends_expected_number_of_times() -> None:
    throttler = ProgressMessageThrottler(min_interval_seconds=3.0)
    sent_count = 0
    # Simulate updates arriving every 1s for 10s, with text changing every tick.
    for t in range(0, 10):
        text = f"{t * 10}%"
        if throttler.should_send(text, now=float(t)):
            throttler.record_sent(text, now=float(t))
            sent_count += 1
    # With a 3s min interval over 10 ticks (0..9), sends happen at 0,3,6,9 -> 4 sends.
    assert sent_count == 4
