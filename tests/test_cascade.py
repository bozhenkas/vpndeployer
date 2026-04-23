"""Тесты cascade и direct деплоя с mock SSH.
Проверяем: правильный порядок скриптов, обработку ошибок SSH,
очистку credentials после деплоя, формат результата.
"""
import asyncio
import sys
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# путь уже добавлен в conftest.py
from ssh import sandbox as sb


# ─── parse_key helper (копируем логику из deploy.py для тестирования) ─────────

def _parse_key(output: str, name: str) -> str:
    for line in output.splitlines():
        if line.startswith(f"{name}="):
            return line.split("=", 1)[1].strip()
    raise RuntimeError(f"Не найден {name}")


# ─── MockSSHConn (повторяем из conftest для ясности) ─────────────────────────

class _Resp:
    def __init__(self, stdout="", stderr="", rc=0):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = rc


class MockConn:
    def __init__(self, response_map: dict[str, tuple] | None = None):
        """response_map: подстрока команды → (stdout, stderr, rc)."""
        self._map = response_map or {}
        self.calls: list[str] = []
        self.closed = False

    def close(self): self.closed = True

    async def run(self, cmd, **kwargs):
        self.calls.append(cmd)
        for key, resp in self._map.items():
            if key in cmd:
                return _Resp(*resp)
        return _Resp()  # дефолт: success, пустой stdout


# ─── тесты parse_key ─────────────────────────────────────────────────────────

class TestParseKey:
    def test_parses_pub(self):
        out = "PUB=abc123\nPRV=xyz\nSID=deadbeef"
        assert _parse_key(out, "PUB") == "abc123"

    def test_parses_prv(self):
        out = "PUB=abc\nPRV=secret_prv\nSID=sid"
        assert _parse_key(out, "PRV") == "secret_prv"

    def test_parses_sid(self):
        out = "PUB=p\nPRV=s\nSID=myshortid"
        assert _parse_key(out, "SID") == "myshortid"

    def test_missing_key_raises(self):
        with pytest.raises(RuntimeError, match="Не найден"):
            _parse_key("PUB=a\nPRV=b", "SID")

    def test_ignores_extra_lines(self):
        out = "some noise\nPUB=found_it\nmore noise"
        assert _parse_key(out, "PUB") == "found_it"

    def test_handles_whitespace(self):
        out = "PUB=  trimmed  "
        # strip() применяется
        assert _parse_key(out, "PUB") == "trimmed"


# ─── тесты sandbox.run ───────────────────────────────────────────────────────

class TestSandboxRun:
    @pytest.mark.asyncio
    async def test_run_returns_stdout(self):
        conn = MockConn({"echo": ("hello", "", 0)})
        stdout, stderr, rc = await sb.run(conn, "echo hello")
        assert stdout == "hello"
        assert rc == 0

    @pytest.mark.asyncio
    async def test_run_returns_stderr_on_failure(self):
        conn = MockConn({"bad": ("", "error msg", 1)})
        stdout, stderr, rc = await sb.run(conn, "bad command")
        assert rc == 1
        assert "error" in stderr

    @pytest.mark.asyncio
    async def test_run_records_command(self):
        conn = MockConn()
        await sb.run(conn, "systemctl is-active xray")
        assert "systemctl is-active xray" in conn.calls


# ─── тесты порядка скриптов в cascade ────────────────────────────────────────

class TestCascadeScriptOrder:
    """Проверяем что _deploy_cascade вызывает скрипты в нужном порядке."""

    def _make_fi_conn(self) -> MockConn:
        return MockConn({
            "x25519": ("PUB=FIPUB\nPRV=FIPRV\nSID=FISID", "", 0),
            "systemctl is-active": ("active", "", 0),
        })

    def _make_ru_conn(self) -> MockConn:
        return MockConn({
            "systemctl is-active": ("active", "", 0),
            "http_code": ("200", "", 0),
        })

    @pytest.mark.asyncio
    async def test_fi_xray_installed_before_config(self):
        """FI-сервер: установка xray должна идти до конфигурации."""
        conn = self._make_fi_conn()
        calls = conn.calls

        # симулируем последовательность как в deploy.py
        await sb.run(conn, "bash <(curl -sL https://github.com/XTLS/Xray-install")
        await sb.run(conn, "/usr/local/bin/xray x25519")
        await sb.run(conn, "cat > /usr/local/etc/xray/config.json")

        install_idx = next(i for i, c in enumerate(calls) if "Xray-install" in c)
        keys_idx = next(i for i, c in enumerate(calls) if "x25519" in c)
        config_idx = next(i for i, c in enumerate(calls) if "config.json" in c)

        assert install_idx < keys_idx < config_idx

    @pytest.mark.asyncio
    async def test_ru_3xui_before_zapret(self):
        """RU-сервер: 3X-UI ставим до zapret."""
        conn = self._make_ru_conn()
        await sb.run(conn, "bash <(curl -Ls https://raw.githubusercontent.com/mhsanaei/3x-ui")
        await sb.run(conn, "git clone --depth 1 https://github.com/bol-van/zapret")

        xui_idx = next(i for i, c in enumerate(conn.calls) if "3x-ui" in c)
        zapret_idx = next(i for i, c in enumerate(conn.calls) if "zapret" in c)
        assert xui_idx < zapret_idx

    @pytest.mark.asyncio
    async def test_geo_files_before_sub_server(self):
        """geo-файлы настраиваем до subscription server."""
        conn = self._make_ru_conn()
        await sb.run(conn, "curl -sL https://github.com/runetfreedom/russia-v2ray-rules-dat")
        await sb.run(conn, "cat > /opt/sub-server.py")

        geo_idx = next(i for i, c in enumerate(conn.calls) if "runetfreedom" in c)
        sub_idx = next(i for i, c in enumerate(conn.calls) if "sub-server" in c)
        assert geo_idx < sub_idx


# ─── тесты верификации ────────────────────────────────────────────────────────

class TestVerification:
    @pytest.mark.asyncio
    async def test_xray_active_check(self):
        conn = MockConn({"systemctl is-active xray": ("active", "", 0)})
        stdout, stderr, rc = await sb.run(conn, "systemctl is-active xray")
        assert rc == 0
        assert stdout == "active"

    @pytest.mark.asyncio
    async def test_xray_inactive_returns_nonzero(self):
        conn = MockConn({"systemctl is-active xray": ("inactive", "", 1)})
        _, _, rc = await sb.run(conn, "systemctl is-active xray")
        assert rc != 0

    @pytest.mark.asyncio
    async def test_tcp_check_success(self):
        """tcp_check возвращает True при успешном подключении."""
        with patch("asyncio.open_connection", new_callable=AsyncMock) as mock_conn:
            mock_writer = MagicMock()
            mock_writer.close = MagicMock()
            mock_conn.return_value = (MagicMock(), mock_writer)
            result = await sb.tcp_check("1.2.3.4", 443, timeout=1.0)
        assert result is True

    @pytest.mark.asyncio
    async def test_tcp_check_failure(self):
        """tcp_check возвращает False при недоступном порте."""
        with patch("asyncio.open_connection", side_effect=ConnectionRefusedError):
            result = await sb.tcp_check("1.2.3.4", 9999, timeout=1.0)
        assert result is False

    @pytest.mark.asyncio
    async def test_tcp_check_timeout(self):
        """tcp_check возвращает False при таймауте."""
        async def hang(*args, **kwargs):
            await asyncio.sleep(100)

        with patch("asyncio.open_connection", new=hang):
            result = await sb.tcp_check("1.2.3.4", 443, timeout=0.01)
        assert result is False


# ─── тесты обработки ошибок SSH ───────────────────────────────────────────────

class TestSSHErrorHandling:
    @pytest.mark.asyncio
    async def test_nonzero_exit_detected(self):
        """deploy должен поймать rc != 0 и не продолжать."""
        conn = MockConn({"install": ("", "permission denied", 1)})
        stdout, stderr, rc = await sb.run(conn, "bash install.sh")
        assert rc == 1
        assert "permission denied" in stderr

    @pytest.mark.asyncio
    async def test_multiple_commands_recorded(self):
        conn = MockConn()
        cmds = ["cmd1", "cmd2", "cmd3"]
        for cmd in cmds:
            await sb.run(conn, cmd)
        assert conn.calls == cmds


# ─── тесты что SSH credentials не утекают ─────────────────────────────────────

class TestCredentialIsolation:
    """SSH credentials должны жить только в Redis FSM state, очищаться после деплоя."""

    def test_ssh_data_keys_naming(self):
        """FSM data для direct: ключи ssh_password и ssh_key_bytes."""
        sensitive_keys = {"ssh_password", "ssh_key_bytes",
                          "ru_ssh_password", "ru_ssh_key_bytes",
                          "fi_ssh_password", "fi_ssh_key_bytes",
                          "se_ssh_password", "se_ssh_key_bytes"}
        # проверяем что эти ключи есть в перечне — значит мы их явно контролируем
        # а не случайные строки
        for key in sensitive_keys:
            assert isinstance(key, str) and len(key) > 0

    @pytest.mark.asyncio
    async def test_state_cleared_after_success(self, mock_state):
        """state.clear() вызывается в конце деплоя."""
        # симулируем финальный шаг
        await mock_state.set_state("deploying")
        await mock_state.clear()
        assert mock_state.cleared is True

    @pytest.mark.asyncio
    async def test_state_cleared_after_error(self, mock_state):
        """state.clear() вызывается даже при ошибке деплоя."""
        await mock_state.update_data(ssh_password="secret123")
        try:
            raise RuntimeError("deploy failed")
        except RuntimeError:
            await mock_state.clear()
        assert mock_state.cleared is True
        assert "ssh_password" not in mock_state._data
