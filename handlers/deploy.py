"""Оркестрация деплоя: подключение, запуск скриптов, стриминг прогресса."""
import asyncio
from typing import Optional

from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext

import db
from fsm import Direct, Cascade
from ssh import sandbox
from ssh.scripts import (
    install_xray, gen_reality_keys, configure_xray_direct,
    setup_caddy_ip, setup_caddy_domain, deploy_sub_server,
    install_3xui, install_zapret, install_adguard, setup_geo_files,
    minimal_exit_xray, install_goida_vpn,
    make_vless_link, generate_sub_token, generate_client_uuid,
)
import config

router = Router()


async def _edit(cb_msg, text: str) -> None:
    try:
        await cb_msg.edit_text(text, parse_mode="HTML")
    except Exception:
        pass


def _ssh_creds(data: dict, prefix: str) -> dict:
    """извлекает SSH credentials из FSM data по префиксу (main/ru/fi/se)."""
    host_key = f"{prefix}_ssh_host" if prefix != "main" else "ssh_host"
    port_key = f"{prefix}_ssh_port" if prefix != "main" else "ssh_port"
    user_key = f"{prefix}_ssh_user" if prefix != "main" else "ssh_user"
    pw_key = f"{prefix}_ssh_password" if prefix != "main" else "ssh_password"
    key_key = f"{prefix}_ssh_key_bytes" if prefix != "main" else "ssh_key_bytes"
    return {
        "host": data.get(host_key),
        "port": data.get(port_key, 22),
        "user": data.get(user_key, "root"),
        "password": data.get(pw_key),
        "private_key_bytes": data.get(key_key),
    }


async def _connect(creds: dict, label: str, progress_msg):
    await _edit(progress_msg, f"🔌 Подключаюсь к <b>{label}</b> (<code>{creds['host']}</code>)...")
    conn = await sandbox.connect(**creds)
    return conn


async def _run_checked(conn, script: str, progress_msg, step_label: str) -> str:
    """выполняет скрипт, бросает RuntimeError если exit code != 0."""
    stdout, stderr, rc = await sandbox.run(conn, script)
    if rc != 0:
        raise RuntimeError(f"{step_label} завершился с ошибкой:\n<code>{stderr[-800:]}</code>")
    return stdout


# ─── DIRECT deploy ───────────────────────────────────────────────────────────

async def _deploy_direct(cb: CallbackQuery, state: FSMContext, data: dict) -> None:
    user_id = cb.from_user.id
    creds = _ssh_creds(data, "main")
    host = creds["host"]
    cert_type = data.get("cert_type", "ip")
    domain = data.get("domain") or host
    sub_host = domain if cert_type == "domain" else host
    n_clients = data.get("client_count", 1)
    sni = "www.microsoft.com"  # дефолтный SNI для Reality

    progress_msg = await cb.message.edit_text("⏳ Начинаю деплой...", parse_mode="HTML")
    dep_id = await db.create_deployment(user_id, "direct", host)

    try:
        conn = await _connect(creds, "сервер", progress_msg)

        await _edit(progress_msg, "[1/5] 📦 Устанавливаю Xray-core...")
        await _run_checked(conn, install_xray(), progress_msg, "install_xray")

        await _edit(progress_msg, "[2/5] 🔑 Генерирую Reality-ключи...")
        keys_out = await _run_checked(conn, gen_reality_keys(), progress_msg, "gen_keys")
        pub_key = _parse_key(keys_out, "PUB")
        prv_key = _parse_key(keys_out, "PRV")
        short_id = _parse_key(keys_out, "SID")

        await _edit(progress_msg, "[3/5] ⚙️ Настраиваю конфиг Xray...")
        clients = [{"id": generate_client_uuid(), "flow": "xtls-rprx-vision"} for _ in range(n_clients)]
        await _run_checked(
            conn,
            configure_xray_direct(prv_key, pub_key, short_id, sni, clients),
            progress_msg, "configure_xray",
        )

        await _edit(progress_msg, "[4/5] 🔒 Настраиваю HTTPS (Caddy)...")
        caddy_script = setup_caddy_domain(domain) if cert_type == "domain" else setup_caddy_ip(host)
        await _run_checked(conn, caddy_script, progress_msg, "caddy")

        await _edit(progress_msg, "[5/5] ✅ Верифицирую...")
        checks = await _verify_direct(conn, host, 443)
        conn.close()

        vless_links = [
            make_vless_link(c["id"], sub_host, pub_key, short_id, sni, f"goida-{i+1}")
            for i, c in enumerate(clients)
        ]
        await db.finish_deployment(dep_id, success=True, vless_links=vless_links)
        await state.clear()
        await _send_direct_result(progress_msg, vless_links, checks)

    except Exception as e:
        await db.finish_deployment(dep_id, success=False, error_msg=str(e))
        await state.clear()
        await _edit(progress_msg, f"❌ Деплой завершился ошибкой:\n\n{e}")


def _parse_key(output: str, name: str) -> str:
    for line in output.splitlines():
        if line.startswith(f"{name}="):
            return line.split("=", 1)[1].strip()
    raise RuntimeError(f"Не удалось извлечь {name} из вывода скрипта")


async def _verify_direct(conn, host: str, port: int) -> list[tuple[str, bool]]:
    checks = []
    _, _, rc = await sandbox.run(conn, "systemctl is-active xray")
    checks.append(("xray service", rc == 0))
    ok = await sandbox.tcp_check(host, port)
    checks.append((f"port {port}", ok))
    return checks


async def _send_direct_result(progress_msg, vless_links: list[str], checks: list) -> None:
    check_lines = "\n".join(
        f"{'✅' if ok else '❌'} {name}" for name, ok in checks
    )
    links_text = "\n\n".join(f"<code>{link}</code>" for link in vless_links)
    text = (
        f"🎉 <b>Деплой завершён!</b>\n\n"
        f"<b>Верификация:</b>\n{check_lines}\n\n"
        f"<b>Ваши VLESS-ссылки:</b>\n\n{links_text}\n\n"
        f"Добавь в Hiddify, v2rayN или NekoBox 👆"
    )
    await progress_msg.edit_text(text, parse_mode="HTML")


# ─── CASCADE deploy ──────────────────────────────────────────────────────────

async def _deploy_cascade(cb: CallbackQuery, state: FSMContext, data: dict) -> None:
    user_id = cb.from_user.id
    ru_creds = _ssh_creds(data, "ru")
    fi_creds = _ssh_creds(data, "fi")
    se_creds = _ssh_creds(data, "se") if data.get("se_ssh_host") else None
    cert_type = data.get("cert_type", "ip")
    domain = data.get("domain")
    main_host = ru_creds["host"]
    sub_host = domain if cert_type == "domain" else main_host
    n_clients = data.get("client_count", 1)
    sni = "www.microsoft.com"

    progress_msg = await cb.message.edit_text("⏳ Начинаю деплой cascade-кластера...", parse_mode="HTML")
    dep_id = await db.create_deployment(user_id, "cascade", main_host)

    try:
        # 1. exit nodes
        await _edit(progress_msg, "[1/7] 🌍 Настраиваю FI-сервер...")
        fi_conn = await _connect(fi_creds, "FI", progress_msg)
        fi_stdout = await _run_checked(fi_conn, install_xray(), progress_msg, "fi_xray")
        fi_keys_raw = await _run_checked(fi_conn, gen_reality_keys(), progress_msg, "fi_keys")
        fi_pub = _parse_key(fi_keys_raw, "PUB")
        fi_prv = _parse_key(fi_keys_raw, "PRV")
        fi_sid = _parse_key(fi_keys_raw, "SID")
        fi_out = await _run_checked(
            fi_conn, minimal_exit_xray(fi_prv, fi_pub, fi_sid, sni), progress_msg, "fi_cfg"
        )
        fi_conn.close()

        se_pub = se_prv = se_sid = se_client_id = None
        if se_creds:
            await _edit(progress_msg, "[2/7] 🌍 Настраиваю SE-сервер...")
            se_conn = await _connect(se_creds, "SE", progress_msg)
            await _run_checked(se_conn, install_xray(), progress_msg, "se_xray")
            se_keys_raw = await _run_checked(se_conn, gen_reality_keys(), progress_msg, "se_keys")
            se_pub = _parse_key(se_keys_raw, "PUB")
            se_prv = _parse_key(se_keys_raw, "PRV")
            se_sid = _parse_key(se_keys_raw, "SID")
            await _run_checked(
                se_conn, minimal_exit_xray(se_prv, se_pub, se_sid, sni), progress_msg, "se_cfg"
            )
            se_conn.close()

        # 2. RU entry
        await _edit(progress_msg, "[3/7] 🇷🇺 Устанавливаю 3X-UI на RU-сервер...")
        ru_conn = await _connect(ru_creds, "RU", progress_msg)
        await _run_checked(ru_conn, install_3xui(), progress_msg, "3xui")

        await _edit(progress_msg, "[4/7] 🛡 Устанавливаю zapret и AdGuard...")
        await _run_checked(ru_conn, install_zapret(), progress_msg, "zapret")
        await _run_checked(ru_conn, install_adguard(), progress_msg, "adguard")

        await _edit(progress_msg, "[5/7] 🗺 Настраиваю geo-файлы и routing...")
        await _run_checked(ru_conn, setup_geo_files(), progress_msg, "geo")

        await _edit(progress_msg, "[6/7] 🤖 Устанавливаю goida-vpn и настраиваю HTTPS...")
        # vpn_bot_token берём из FSM data (пользователь вводит в интервью)
        vpn_bot_token = data.get("vpn_bot_token", "PLACEHOLDER")
        await _run_checked(
            ru_conn,
            install_goida_vpn(config.GOIDA_VPN_REPO, config.GOIDA_VPN_TAG, vpn_bot_token, cb.from_user.id),
            progress_msg, "goida_vpn",
        )
        sub_token = generate_sub_token()
        caddy_script = setup_caddy_domain(domain) if cert_type == "domain" else setup_caddy_ip(main_host)
        await _run_checked(ru_conn, caddy_script, progress_msg, "caddy")
        await _run_checked(ru_conn, deploy_sub_server(sub_token), progress_msg, "sub_server")

        await _edit(progress_msg, "[7/7] ✅ Верифицирую кластер...")
        checks = await _verify_cascade(ru_conn, main_host)
        ru_conn.close()

        sub_url = f"https://{sub_host}:{config.SUB_PORT}/subscribe/{sub_token}"
        await db.finish_deployment(dep_id, success=True, sub_url=sub_url)
        await state.clear()
        await _send_cascade_result(progress_msg, sub_url, checks)

    except Exception as e:
        await db.finish_deployment(dep_id, success=False, error_msg=str(e))
        await state.clear()
        await _edit(progress_msg, f"❌ Деплой завершился ошибкой:\n\n{e}")


async def _verify_cascade(conn, host: str) -> list[tuple[str, bool]]:
    checks = []
    _, _, rc = await sandbox.run(conn, "systemctl is-active xray")
    checks.append(("xray service", rc == 0))
    ok = await sandbox.tcp_check(host, 443)
    checks.append(("port 443", ok))
    # 3X-UI API — базовый health check
    _, out, rc = await sandbox.run(
        conn,
        "curl -sk -o /dev/null -w '%{http_code}' https://127.0.0.1:25565/penis/login"
    )
    checks.append(("3X-UI panel", out.strip() in ("200", "302")))
    return checks


async def _send_cascade_result(progress_msg, sub_url: str, checks: list) -> None:
    check_lines = "\n".join(
        f"{'✅' if ok else '❌'} {name}" for name, ok in checks
    )
    text = (
        f"🎉 <b>Cascade-кластер готов!</b>\n\n"
        f"<b>Верификация:</b>\n{check_lines}\n\n"
        f"<b>URL подписки:</b>\n<code>{sub_url}</code>\n\n"
        f"Добавь URL в Hiddify, v2rayN или NekoBox → Subscribe 👆"
    )
    await progress_msg.edit_text(text, parse_mode="HTML")


# ─── confirm:yes router ──────────────────────────────────────────────────────

@router.callback_query(F.data == "confirm:yes")
async def handle_confirm(cb: CallbackQuery, state: FSMContext) -> None:
    await cb.answer()
    data = await state.get_data()
    scenario = data.get("scenario", "direct")

    current_state = await state.get_state()
    # устанавливаем deploying чтобы заблокировать повторный confirm
    if scenario == "direct":
        await state.set_state(Direct.deploying)
        asyncio.create_task(_deploy_direct(cb, state, data))
    else:
        await state.set_state(Cascade.deploying)
        asyncio.create_task(_deploy_cascade(cb, state, data))
