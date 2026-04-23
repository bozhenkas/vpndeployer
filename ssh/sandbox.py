import asyncio
import asyncssh
from typing import Optional


async def connect(
    host: str,
    port: int,
    user: str,
    password: Optional[str] = None,
    private_key_bytes: Optional[bytes] = None,
    timeout: int = 15,
) -> asyncssh.SSHClientConnection:
    kwargs: dict = dict(
        host=host,
        port=port,
        username=user,
        known_hosts=None,
        connect_timeout=timeout,
    )
    if private_key_bytes:
        key = asyncssh.import_private_key(private_key_bytes)
        kwargs["client_keys"] = [key]
        kwargs["password"] = None
    else:
        kwargs["password"] = password
        kwargs["client_keys"] = []

    return await asyncssh.connect(**kwargs)


async def run(conn: asyncssh.SSHClientConnection, cmd: str) -> tuple[str, str, int]:
    result = await conn.run(cmd, check=False)
    return (result.stdout or ""), (result.stderr or ""), result.returncode


async def upload(conn: asyncssh.SSHClientConnection, data: bytes, remote_path: str) -> None:
    async with conn.start_sftp_client() as sftp:
        async with await sftp.open(remote_path, "wb") as f:
            await f.write(data)


async def tcp_check(host: str, port: int, timeout: float = 5.0) -> bool:
    try:
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), timeout=timeout
        )
        writer.close()
        return True
    except Exception:
        return False
