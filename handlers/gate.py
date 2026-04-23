"""Канал-гейт: пользователь должен быть подписан на REQUIRED_CHANNEL."""
from aiogram import BaseMiddleware, Bot
from aiogram.types import TelegramObject, Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from typing import Any, Awaitable, Callable

import config


async def _is_member(bot: Bot, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(config.REQUIRED_CHANNEL, user_id)
        return member.status not in ("left", "kicked", "banned", "restricted")
    except Exception:
        return False


def _gate_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Подписаться на канал", url=f"https://t.me/{config.REQUIRED_CHANNEL.lstrip('@')}")],
        [InlineKeyboardButton(text="🔄 Проверить подписку", callback_data="gate:recheck")],
    ])


_GATE_TEXT = (
    "🔒 Для использования бота необходимо подписаться на наш канал.\n\n"
    "После подписки нажми <b>Проверить подписку</b>."
)


class ChannelGateMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        bot: Bot = data["bot"]

        # определяем user_id и объект для ответа
        if isinstance(event, Message):
            user_id = event.from_user.id
            reply = event
        elif isinstance(event, CallbackQuery):
            user_id = event.from_user.id
            # recheck callback пропускаем в handler — он сам ответит
            if event.data == "gate:recheck":
                return await handler(event, data)
            reply = event.message
        else:
            return await handler(event, data)

        if not await _is_member(bot, user_id):
            if isinstance(event, Message):
                await event.answer(_GATE_TEXT, reply_markup=_gate_kb(), parse_mode="HTML")
            elif isinstance(event, CallbackQuery):
                await event.answer("Сначала подпишись на канал!", show_alert=True)
            return  # блокируем

        return await handler(event, data)


# ── recheck handler (регистрируется в main роутере) ──────────────────────────

from aiogram import Router, F
from aiogram.types import CallbackQuery as CQ

gate_router = Router()


@gate_router.callback_query(F.data == "gate:recheck")
async def gate_recheck(cb: CQ, bot: Bot) -> None:
    if await _is_member(bot, cb.from_user.id):
        await cb.answer("✅ Подписка подтверждена! Напиши /start", show_alert=True)
        await cb.message.delete()
    else:
        await cb.answer("❌ Ты ещё не подписан на канал.", show_alert=True)
