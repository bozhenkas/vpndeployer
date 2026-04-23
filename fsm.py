from aiogram.fsm.state import State, StatesGroup


class Direct(StatesGroup):
    ssh_host = State()
    ssh_port = State()
    ssh_user = State()
    ssh_auth_type = State()   # callback: password | key
    ssh_password = State()
    ssh_key = State()         # file upload
    cert_type = State()       # callback: ip | domain
    domain = State()
    client_count = State()
    confirm = State()
    deploying = State()


class Cascade(StatesGroup):
    # RU entry
    ru_ssh_host = State()
    ru_ssh_port = State()
    ru_ssh_user = State()
    ru_ssh_auth_type = State()
    ru_ssh_password = State()
    ru_ssh_key = State()
    # FI exit
    fi_ssh_host = State()
    fi_ssh_port = State()
    fi_ssh_user = State()
    fi_ssh_auth_type = State()
    fi_ssh_password = State()
    fi_ssh_key = State()
    # SE exit (optional)
    se_ask = State()          # callback: add | skip
    se_ssh_host = State()
    se_ssh_port = State()
    se_ssh_user = State()
    se_ssh_auth_type = State()
    se_ssh_password = State()
    se_ssh_key = State()
    # общее
    cert_type = State()
    domain = State()
    client_count = State()
    vpn_bot_token = State()   # токен Telegram-бота для установки на RU-ноде
    confirm = State()
    deploying = State()
