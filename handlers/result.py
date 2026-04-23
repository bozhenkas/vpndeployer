"""Вспомогательные команды после деплоя."""
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

import db

router = Router()


@router.message(Command("deployments"))
async def cmd_deployments(msg: Message, state: FSMContext) -> None:
    rows = await db.get_user_deployments(msg.from_user.id)
    if not rows:
        await msg.answer("У тебя пока нет деплойментов. Напиши /start чтобы начать.")
        return

    lines = ["<b>Твои деплойменты:</b>\n"]
    for r in rows:
        icon = {"success": "✅", "failed": "❌", "deploying": "⏳"}.get(r["status"], "❓")
        ts = r["created_at"].strftime("%d.%m %H:%M") if r["created_at"] else "—"
        lines.append(f"{icon} <b>{r['scenario']}</b> · {r['main_ip']} · {ts}")
        if r["sub_url"]:
            lines.append(f"   <code>{r['sub_url']}</code>")
        if r["vless_links"]:
            for link in r["vless_links"]:
                lines.append(f"   <code>{link}</code>")
        if r["error_msg"] and r["status"] == "failed":
            lines.append(f"   ⚠️ {r['error_msg'][:120]}")
        lines.append("")

    await msg.answer("\n".join(lines), parse_mode="HTML")
