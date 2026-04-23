from aiogram import Router
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.fsm.context import FSMContext

from fsm import Direct, Cascade
import config

router = Router()

_SCENARIO_KB = InlineKeyboardMarkup(inline_keyboard=[
    [
        InlineKeyboardButton(text="🔵 Direct (1 сервер)", callback_data="scenario:direct"),
        InlineKeyboardButton(text="🔴 Cascade (RU+Exit)", callback_data="scenario:cascade"),
    ],
    [InlineKeyboardButton(text="🖥 Купить VPS (Aeza)", url=config.AEZA_REF_URL)],
])

_WELCOME = (
    "👋 Привет! Я <b>@vpndeployerbot</b> — разверну твой личный VPN-кластер за несколько минут.\n\n"
    "Выбери сценарий:\n\n"
    "🔵 <b>Direct</b> — один зарубежный VPS, простая Reality-подписка\n"
    "🔴 <b>Cascade</b> — RU-сервер как точка входа + FI/SE серверы выхода,\n"
    "   умная маршрутизация, zapret, 3X-UI\n\n"
    "Нет VPS? Купи у проверенного хостера 👇"
    + config.OPEN_SOURCE_NOTICE
)


@router.message(CommandStart())
async def cmd_start(msg: Message, state: FSMContext) -> None:
    await state.clear()
    await msg.answer(_WELCOME, reply_markup=_SCENARIO_KB, parse_mode="HTML",
                     disable_web_page_preview=True)


@router.message(Command("info"))
async def cmd_info(msg: Message) -> None:
    await msg.answer(
        "ℹ️ <b>goida-deployer</b> — open source бот для развёртывания личного VPN.\n\n"
        f"Исходный код: github.com/bozhenkas/goida-deployer\n"
        f"Устанавливает: <a href='{config.GOIDA_VPN_REPO}'>{config.GOIDA_VPN_REPO}</a> "
        f"(тег <code>{config.GOIDA_VPN_TAG}</code>)\n\n"
        "Мы не храним ваши SSH данные после деплоя — проверьте код сами.",
        parse_mode="HTML",
        disable_web_page_preview=True,
    )


@router.callback_query(lambda c: c.data and c.data.startswith("scenario:"))
async def pick_scenario(cb: CallbackQuery, state: FSMContext) -> None:
    scenario = cb.data.split(":")[1]
    await cb.answer()
    await state.update_data(scenario=scenario)

    if scenario == "direct":
        await state.set_state(Direct.ssh_host)
        await cb.message.edit_text(
            "🔵 <b>Direct</b>\n\nШаг 1/5 — Введи <b>IP или hostname</b> твоего сервера:",
            parse_mode="HTML",
        )
    else:
        await state.set_state(Cascade.ru_ssh_host)
        await cb.message.edit_text(
            "🔴 <b>Cascade</b>\n\nШаг 1 — <b>RU-сервер (точка входа)</b>\n\nВведи IP или hostname:",
            parse_mode="HTML",
        )
