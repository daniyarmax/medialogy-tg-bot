"""Shared test doubles for mocking subprocess-based yt-dlp/ffmpeg calls so
unit tests never touch the network or spawn real external processes.
"""


class FakeStreamReader:
    def __init__(self, lines: list[bytes]) -> None:
        self._lines = list(lines)

    def __aiter__(self) -> "FakeStreamReader":
        return self

    async def __anext__(self) -> bytes:
        if not self._lines:
            raise StopAsyncIteration
        return self._lines.pop(0)

    async def read(self) -> bytes:
        remaining = b"".join(self._lines)
        self._lines = []
        return remaining


class FakeProcess:
    """Stands in for `asyncio.subprocess.Process` in unit tests."""

    def __init__(
        self,
        *,
        stdout_lines: list[bytes] | None = None,
        stderr: bytes = b"",
        returncode: int = 0,
        communicate_result: tuple[bytes, bytes] | None = None,
    ) -> None:
        self.stdout = FakeStreamReader(stdout_lines or [])
        self.stderr = FakeStreamReader([stderr] if stderr else [])
        self.returncode = returncode
        self._communicate_result = communicate_result or (b"", stderr)
        self.killed = False

    async def wait(self) -> int:
        return self.returncode

    async def communicate(self) -> tuple[bytes, bytes]:
        return self._communicate_result

    def kill(self) -> None:
        self.killed = True


def make_subprocess_exec_stub(fake_process: FakeProcess):
    async def _fake_create_subprocess_exec(*args, **kwargs) -> FakeProcess:
        return fake_process

    return _fake_create_subprocess_exec
