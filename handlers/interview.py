"""FSM-шаги интервью для обоих сценариев."""
from aiogram import Router, Bot, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

from fsm import Direct, Cascade
import config

router = Router()

# ─── keyboards ───────────────────────────────────────────────────────────────

def _auth_kb(prefix: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🔑 Пароль", callback_data=f"auth:{prefix}:password"),
        InlineKeyboardButton(text="🗝 SSH-ключ (файл)", callback_data=f"auth:{prefix}:key"),
    ]])


def _cert_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🌐 IP-сертификат", callback_data="cert:ip"),
            InlineKeyboardButton(text="🔗 Свой домен", callback_data="cert:domain"),
        ],
        [InlineKeyboardButton(text="❓ Что выбрать?", url=config.DOCS_IP_CERT_URL)],
    ])


def _se_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="➕ Добавить SE-сервер", callback_data="se:add"),
        InlineKeyboardButton(text="⏭ Пропустить", callback_data="se:skip"),
    ]])


def _confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🚀 Да, поехали!", callback_data="confirm:yes"),
        InlineKeyboardButton(text="❌ Отмена", callback_data="confirm:no"),
    ]])


# ─── helpers ─────────────────────────────────────────────────────────────────

async def _ask_port(msg: Message, state: FSMContext, next_state, label: str) -> None:
    await state.set_state(next_state)
    await msg.answer(f"Порт SSH [{label}] (Enter = 22):")


async def _ask_user(msg: Message, state: FSMContext, next_state, server: str) -> None:
    await state.set_state(next_state)
    await msg.answer(f"Пользователь для {server} (Enter = root):")


async def _ask_auth(msg: Message, state: FSMContext, next_state, prefix: str, server: str) -> None:
    await state.set_state(next_state)
    await msg.answer(f"Метод аутентификации для {server}:", reply_markup=_auth_kb(prefix))


def _parse_port(text: str) -> int:
    text = text.strip()
    if text in ("", "-"):
        return 22
    try:
        p = int(text)
        assert 1 <= p <= 65535
        return p
    except Exception:
        raise ValueError(f"Неверный порт: {text}")


def _parse_user(text: str) -> str:
    text = text.strip()
    return text if text and text != "-" else "root"


async def _build_confirm_text(data: dict) -> str:
    scenario = data.get("scenario", "direct")
    lines = [f"📋 <b>Проверь настройки:</b>\n", f"Сценарий: <b>{scenario}</b>"]
    if scenario == "direct":
        lines.append(f"Сервер: <code>{data.get('ssh_host')}:{data.get('ssh_port', 22)}</code>")
        lines.append(f"Пользователь: <code>{data.get('ssh_user', 'root')}</code>")
        lines.append(f"Аутентификация: {data.get('auth_type_main', '?')}")
    else:
        lines.append(f"RU-сервер: <code>{data.get('ru_ssh_host')}:{data.get('ru_ssh_port', 22)}</code>")
        lines.append(f"FI-сервер: <code>{data.get('fi_ssh_host')}:{data.get('fi_ssh_port', 22)}</code>")
        if data.get("se_ssh_host"):
            lines.append(f"SE-сервер: <code>{data.get('se_ssh_host')}:{data.get('se_ssh_port', 22)}</code>")
    cert = data.get("cert_type", "ip")
    if cert == "domain":
        lines.append(f"Домен: <code>{data.get('domain', '?')}</code>")
    else:
        lines.append("Сертификат: по IP (Let's Encrypt)")
    lines.append(f"Клиентов: {data.get('client_count', 1)}")
    lines.append("\nЗапустить деплой?")
    return "\n".join(lines)


# ─── DIRECT flow ─────────────────────────────────────────────────────────────

@router.message(Direct.ssh_host)
async def direct_ssh_host(msg: Message, state: FSMContext) -> None:
    host = msg.text.strip()
    await state.update_data(ssh_host=host)
    await state.set_state(Direct.ssh_port)
    await msg.answer(f"Хост: <code>{host}</code>\n\nПорт SSH (Enter = 22):", parse_mode="HTML")


@router.message(Direct.ssh_port)
async def direct_ssh_port(msg: Message, state: FSMContext) -> None:
    try:
        port = _parse_port(msg.text)
    except ValueError as e:
        await msg.answer(str(e))
        return
    await state.update_data(ssh_port=port)
    await state.set_state(Direct.ssh_user)
    await msg.answer(f"Порт: <code>{port}</code>\n\nПользователь (Enter = root):", parse_mode="HTML")


@router.message(Direct.ssh_user)
async def direct_ssh_user(msg: Message, state: FSMContext) -> None:
    user = _parse_user(msg.text)
    await state.update_data(ssh_user=user)
    await state.set_state(Direct.ssh_auth_type)
    await msg.answer(f"Пользователь: <code>{user}</code>\n\nМетод входа:", parse_mode="HTML",
                     reply_markup=_auth_kb("main"))


@router.callback_query(Direct.ssh_auth_type, F.data.startswith("auth:main:"))
async def direct_auth_type(cb: CallbackQuery, state: FSMContext) -> None:
    method = cb.data.split(":")[2]
    await state.update_data(auth_type_main=method)
    await cb.answer()
    if method == "password":
        await state.set_state(Direct.ssh_password)
        await cb.message.edit_text("Введи пароль SSH:")
    else:
        await state.set_state(Direct.ssh_key)
        await cb.message.edit_text("Отправь файл с приватным SSH-ключом (.pem/.key):")


@router.message(Direct.ssh_password)
async def direct_ssh_password(msg: Message, state: FSMContext, bot: Bot) -> None:
    await state.update_data(ssh_password=msg.text.strip())
    await bot.delete_message(msg.chat.id, msg.message_id)  # удаляем пароль из чата
    await _ask_cert(msg, state, Direct.cert_type)


@router.message(Direct.ssh_key, F.document)
async def direct_ssh_key(msg: Message, state: FSMContext, bot: Bot) -> None:
    file = await bot.get_file(msg.document.file_id)
    key_bytes = await bot.download_file(file.file_path)
    await state.update_data(ssh_key_bytes=key_bytes.read())
    await _ask_cert(msg, state, Direct.cert_type)


@router.message(Direct.ssh_key)
async def direct_ssh_key_wrong(msg: Message) -> None:
    await msg.answer("Отправь файл с SSH-ключом (document), не текст.")


async def _ask_cert(msg: Message, state: FSMContext, next_state) -> None:
    await state.set_state(next_state)
    await msg.answer(
        "Как подключать клиентов к подписке?\n\n"
        "🌐 <b>IP-сертификат</b> — Let's Encrypt выдаст сертификат прямо на IP сервера\n"
        "🔗 <b>Свой домен</b> — укажи домен, направленный на сервер",
        parse_mode="HTML",
        reply_markup=_cert_kb(),
    )


@router.callback_query(Direct.cert_type, F.data.startswith("cert:"))
async def direct_cert_type(cb: CallbackQuery, state: FSMContext) -> None:
    cert = cb.data.split(":")[1]
    await state.update_data(cert_type=cert)
    await cb.answer()
    if cert == "domain":
        await state.set_state(Direct.domain)
        await cb.message.edit_text(
            f"Введи домен (например: vpn.example.com)\n\n"
            f"<a href='{config.DOCS_DOMAIN_URL}'>📖 Как настроить домен?</a>",
            parse_mode="HTML", disable_web_page_preview=True,
        )
    else:
        await state.set_state(Direct.client_count)
        await cb.message.edit_text("Сколько клиентов создать? (1–10, Enter = 1):")


@router.message(Direct.domain)
async def direct_domain(msg: Message, state: FSMContext) -> None:
    domain = msg.text.strip().lower().lstrip("https://").lstrip("http://").rstrip("/")
    await state.update_data(domain=domain)
    await state.set_state(Direct.client_count)
    await msg.answer(f"Домен: <code>{domain}</code>\n\nСколько клиентов создать? (1–10, Enter = 1):", parse_mode="HTML")


@router.message(Direct.client_count)
async def direct_client_count(msg: Message, state: FSMContext) -> None:
    text = msg.text.strip()
    try:
        n = int(text) if text and text != "-" else 1
        assert 1 <= n <= 10
    except Exception:
        await msg.answer("Введи число от 1 до 10:")
        return
    await state.update_data(client_count=n)
    await state.set_state(Direct.confirm)
    data = await state.get_data()
    await msg.answer(await _build_confirm_text(data), parse_mode="HTML", reply_markup=_confirm_kb())


# ─── CASCADE flow ─────────────────────────────────────────────────────────────

@router.message(Cascade.ru_ssh_host)
async def cascade_ru_host(msg: Message, state: FSMContext) -> None:
    await state.update_data(ru_ssh_host=msg.text.strip())
    await state.set_state(Cascade.ru_ssh_port)
    await msg.answer("RU-сервер: порт SSH (Enter = 22):")


@router.message(Cascade.ru_ssh_port)
async def cascade_ru_port(msg: Message, state: FSMContext) -> None:
    try:
        port = _parse_port(msg.text)
    except ValueError as e:
        await msg.answer(str(e)); return
    await state.update_data(ru_ssh_port=port)
    await state.set_state(Cascade.ru_ssh_user)
    await msg.answer("RU-сервер: пользователь (Enter = root):")


@router.message(Cascade.ru_ssh_user)
async def cascade_ru_user(msg: Message, state: FSMContext) -> None:
    await state.update_data(ru_ssh_user=_parse_user(msg.text))
    await state.set_state(Cascade.ru_ssh_auth_type)
    await msg.answer("RU-сервер: метод аутентификации:", reply_markup=_auth_kb("ru"))


@router.callback_query(Cascade.ru_ssh_auth_type, F.data.startswith("auth:ru:"))
async def cascade_ru_auth(cb: CallbackQuery, state: FSMContext) -> None:
    method = cb.data.split(":")[2]
    await state.update_data(auth_type_ru=method)
    await cb.answer()
    if method == "password":
        await state.set_state(Cascade.ru_ssh_password)
        await cb.message.edit_text("RU-сервер: введи пароль SSH:")
    else:
        await state.set_state(Cascade.ru_ssh_key)
        await cb.message.edit_text("RU-сервер: отправь файл приватного SSH-ключа:")


@router.message(Cascade.ru_ssh_password)
async def cascade_ru_password(msg: Message, state: FSMContext, bot: Bot) -> None:
    await state.update_data(ru_ssh_password=msg.text.strip())
    await bot.delete_message(msg.chat.id, msg.message_id)
    await state.set_state(Cascade.fi_ssh_host)
    await msg.answer("✅ RU-сервер добавлен.\n\n<b>FI-сервер (выход)</b>\nВведи IP или hostname:", parse_mode="HTML")


@router.message(Cascade.ru_ssh_key, F.document)
async def cascade_ru_key(msg: Message, state: FSMContext, bot: Bot) -> None:
    file = await bot.get_file(msg.document.file_id)
    key_bytes = await bot.download_file(file.file_path)
    await state.update_data(ru_ssh_key_bytes=key_bytes.read())
    await state.set_state(Cascade.fi_ssh_host)
    await msg.answer("✅ RU-сервер добавлен.\n\n<b>FI-сервер (выход)</b>\nВведи IP или hostname:", parse_mode="HTML")


@router.message(Cascade.fi_ssh_host)
async def cascade_fi_host(msg: Message, state: FSMContext) -> None:
    await state.update_data(fi_ssh_host=msg.text.strip())
    await state.set_state(Cascade.fi_ssh_port)
    await msg.answer("FI-сервер: порт SSH (Enter = 22):")


@router.message(Cascade.fi_ssh_port)
async def cascade_fi_port(msg: Message, state: FSMContext) -> None:
    try:
        port = _parse_port(msg.text)
    except ValueError as e:
        await msg.answer(str(e)); return
    await state.update_data(fi_ssh_port=port)
    await state.set_state(Cascade.fi_ssh_user)
    await msg.answer("FI-сервер: пользователь (Enter = root):")


@router.message(Cascade.fi_ssh_user)
async def cascade_fi_user(msg: Message, state: FSMContext) -> None:
    await state.update_data(fi_ssh_user=_parse_user(msg.text))
    await state.set_state(Cascade.fi_ssh_auth_type)
    await msg.answer("FI-сервер: метод аутентификации:", reply_markup=_auth_kb("fi"))


@router.callback_query(Cascade.fi_ssh_auth_type, F.data.startswith("auth:fi:"))
async def cascade_fi_auth(cb: CallbackQuery, state: FSMContext) -> None:
    method = cb.data.split(":")[2]
    await state.update_data(auth_type_fi=method)
    await cb.answer()
    if method == "password":
        await state.set_state(Cascade.fi_ssh_password)
        await cb.message.edit_text("FI-сервер: введи пароль SSH:")
    else:
        await state.set_state(Cascade.fi_ssh_key)
        await cb.message.edit_text("FI-сервер: отправь файл приватного SSH-ключа:")


@router.message(Cascade.fi_ssh_password)
async def cascade_fi_password(msg: Message, state: FSMContext, bot: Bot) -> None:
    await state.update_data(fi_ssh_password=msg.text.strip())
    await bot.delete_message(msg.chat.id, msg.message_id)
    await state.set_state(Cascade.se_ask)
    await msg.answer("✅ FI-сервер добавлен.\n\nДобавить SE-сервер?", reply_markup=_se_kb())


@router.message(Cascade.fi_ssh_key, F.document)
async def cascade_fi_key(msg: Message, state: FSMContext, bot: Bot) -> None:
    file = await bot.get_file(msg.document.file_id)
    key_bytes = await bot.download_file(file.file_path)
    await state.update_data(fi_ssh_key_bytes=key_bytes.read())
    await state.set_state(Cascade.se_ask)
    await msg.answer("✅ FI-сервер добавлен.\n\nДобавить SE-сервер?", reply_markup=_se_kb())


@router.callback_query(Cascade.se_ask, F.data.startswith("se:"))
async def cascade_se_ask(cb: CallbackQuery, state: FSMContext) -> None:
    choice = cb.data.split(":")[1]
    await cb.answer()
    if choice == "skip":
        await state.set_state(Cascade.cert_type)
        await cb.message.edit_text(
            "Как подключать клиентов к подписке?",
            reply_markup=_cert_kb(),
        )
    else:
        await state.set_state(Cascade.se_ssh_host)
        await cb.message.edit_text("<b>SE-сервер (выход)</b>\nВведи IP или hostname:", parse_mode="HTML")


@router.message(Cascade.se_ssh_host)
async def cascade_se_host(msg: Message, state: FSMContext) -> None:
    await state.update_data(se_ssh_host=msg.text.strip())
    await state.set_state(Cascade.se_ssh_port)
    await msg.answer("SE-сервер: порт SSH (Enter = 22):")


@router.message(Cascade.se_ssh_port)
async def cascade_se_port(msg: Message, state: FSMContext) -> None:
    try:
        port = _parse_port(msg.text)
    except ValueError as e:
        await msg.answer(str(e)); return
    await state.update_data(se_ssh_port=port)
    await state.set_state(Cascade.se_ssh_user)
    await msg.answer("SE-сервер: пользователь (Enter = root):")


@router.message(Cascade.se_ssh_user)
async def cascade_se_user(msg: Message, state: FSMContext) -> None:
    await state.update_data(se_ssh_user=_parse_user(msg.text))
    await state.set_state(Cascade.se_ssh_auth_type)
    await msg.answer("SE-сервер: метод аутентификации:", reply_markup=_auth_kb("se"))


@router.callback_query(Cascade.se_ssh_auth_type, F.data.startswith("auth:se:"))
async def cascade_se_auth(cb: CallbackQuery, state: FSMContext) -> None:
    method = cb.data.split(":")[2]
    await state.update_data(auth_type_se=method)
    await cb.answer()
    if method == "password":
        await state.set_state(Cascade.se_ssh_password)
        await cb.message.edit_text("SE-сервер: введи пароль SSH:")
    else:
        await state.set_state(Cascade.se_ssh_key)
        await cb.message.edit_text("SE-сервер: отправь файл приватного SSH-ключа:")


@router.message(Cascade.se_ssh_password)
async def cascade_se_password(msg: Message, state: FSMContext, bot: Bot) -> None:
    await state.update_data(se_ssh_password=msg.text.strip())
    await bot.delete_message(msg.chat.id, msg.message_id)
    await state.set_state(Cascade.cert_type)
    await msg.answer("✅ SE-сервер добавлен.\n\nКак подключать клиентов к подписке?",
                     reply_markup=_cert_kb())


@router.message(Cascade.se_ssh_key, F.document)
async def cascade_se_key(msg: Message, state: FSMContext, bot: Bot) -> None:
    file = await bot.get_file(msg.document.file_id)
    key_bytes = await bot.download_file(file.file_path)
    await state.update_data(se_ssh_key_bytes=key_bytes.read())
    await state.set_state(Cascade.cert_type)
    await msg.answer("✅ SE-сервер добавлен.\n\nКак подключать клиентов к подписке?",
                     reply_markup=_cert_kb())


@router.callback_query(Cascade.cert_type, F.data.startswith("cert:"))
async def cascade_cert_type(cb: CallbackQuery, state: FSMContext) -> None:
    cert = cb.data.split(":")[1]
    await state.update_data(cert_type=cert)
    await cb.answer()
    if cert == "domain":
        await state.set_state(Cascade.domain)
        await cb.message.edit_text(
            f"Введи домен (например: vpn.example.com)\n\n"
            f"<a href='{config.DOCS_DOMAIN_URL}'>📖 Как настроить домен?</a>",
            parse_mode="HTML", disable_web_page_preview=True,
        )
    else:
        await state.set_state(Cascade.client_count)
        await cb.message.edit_text("Сколько клиентов создать? (1–10, Enter = 1):")


@router.message(Cascade.domain)
async def cascade_domain(msg: Message, state: FSMContext) -> None:
    domain = msg.text.strip().lower().lstrip("https://").lstrip("http://").rstrip("/")
    await state.update_data(domain=domain)
    await state.set_state(Cascade.client_count)
    await msg.answer(f"Домен: <code>{domain}</code>\n\nСколько клиентов создать? (1–10, Enter = 1):", parse_mode="HTML")


@router.message(Cascade.client_count)
async def cascade_client_count(msg: Message, state: FSMContext) -> None:
    text = msg.text.strip()
    try:
        n = int(text) if text and text != "-" else 1
        assert 1 <= n <= 10
    except Exception:
        await msg.answer("Введи число от 1 до 10:")
        return
    await state.update_data(client_count=n)
    await state.set_state(Cascade.vpn_bot_token)
    await msg.answer(
        "🤖 Введи токен Telegram-бота для управления кластером.\n\n"
        "Создай бота через @BotFather → /newbot → скопируй токен.\n"
        "Этот бот будет установлен на твой RU-сервер.",
        parse_mode="HTML",
    )


@router.message(Cascade.vpn_bot_token)
async def cascade_vpn_bot_token(msg: Message, state: FSMContext, bot: Bot) -> None:
    token = msg.text.strip()
    # базовая валидация токена: DIGITS:ALPHANUMERIC
    if ":" not in token or len(token) < 30:
        await msg.answer("Похоже, токен неверный. Он выглядит как: 123456789:ABCdef...")
        return
    await state.update_data(vpn_bot_token=token)
    await bot.delete_message(msg.chat.id, msg.message_id)  # убираем токен из чата
    await state.set_state(Cascade.confirm)
    data = await state.get_data()
    await msg.answer(await _build_confirm_text(data), parse_mode="HTML", reply_markup=_confirm_kb())


# ─── confirm ─────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "confirm:no")
async def confirm_cancel(cb: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await cb.answer("Отменено.")
    await cb.message.edit_text("❌ Деплой отменён. Напиши /start чтобы начать заново.")
