"""pytest fixtures и sys.path для запуска тестов из deployer-bot/."""
import sys
import os

# добавляем корень проекта в path чтобы импортировать ssh.scripts и т.д.
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest


# ── mock FSM state ────────────────────────────────────────────────────────────

class _MockFSMState:
    """минимальный stub для aiogram FSMContext."""
    def __init__(self, data: dict | None = None):
        self._data = data or {}
        self._state = None
        self.cleared = False

    async def get_data(self): return dict(self._data)
    async def update_data(self, **kwargs): self._data.update(kwargs)
    async def set_state(self, state): self._state = state
    async def get_state(self): return self._state
    async def clear(self): self.cleared = True; self._data = {}


class _MockMessage:
    """stub для aiogram Message."""
    def __init__(self):
        self._text = ""
        self.edits: list[str] = []

    async def edit_text(self, text, **kwargs):
        self._text = text
        self.edits.append(text)


class _MockCallback:
    """stub для aiogram CallbackQuery."""
    def __init__(self, data: dict | None = None):
        self.from_user = type("U", (), {"id": 42})()
        self.message = _MockMessage()
        self._data: dict = data or {}

    async def answer(self, *args, **kwargs): pass


@pytest.fixture
def mock_state():
    return _MockFSMState()


@pytest.fixture
def mock_cb():
    return _MockCallback()


# ── SSH mock ──────────────────────────────────────────────────────────────────

class MockSSHConn:
    """stub asyncssh-соединения: run() возвращает заранее заданные ответы."""
    def __init__(self, responses: list[tuple[str, str, int]] | None = None):
        # responses — стек ответов в порядке вызовов run()
        self._responses = list(responses or [])
        self._default = ("", "", 0)
        self.commands: list[str] = []  # история вызовов
        self.closed = False

    def close(self): self.closed = True

    async def run(self, cmd, **kwargs):
        self.commands.append(cmd)
        resp = self._responses.pop(0) if self._responses else self._default
        # возвращаем объект с атрибутами stdout/stderr/returncode
        return type("R", (), {
            "stdout": resp[0],
            "stderr": resp[1],
            "returncode": resp[2],
        })()


@pytest.fixture
def mock_conn():
    return MockSSHConn()
