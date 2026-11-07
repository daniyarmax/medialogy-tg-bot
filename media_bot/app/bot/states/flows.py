from aiogram.fsm.state import State, StatesGroup


class DownloadFlow(StatesGroup):
    waiting_for_url = State()
    choosing_quality = State()


class AudioFlow(StatesGroup):
    waiting_for_source = State()  # URL text, or a sent video/audio file
    choosing_format = State()
    choosing_bitrate = State()
