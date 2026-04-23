import os

BOT_TOKEN: str = os.environ["BOT_TOKEN"]
REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
POSTGRES_DSN: str = os.environ["POSTGRES_DSN"]

# владелец бота — всегда проходит канал-гейт
OWNER_ID: int = int(os.getenv("OWNER_ID", "294057781"))

# канал-гейт: пользователь обязан быть подписан перед использованием
# значение: @username или числовой ID канала (напр. -1001234567890)
# оставить пустым ("") — гейт отключён
REQUIRED_CHANNEL: str = os.getenv("REQUIRED_CHANNEL", "")

# версия goida-vpn, которую деплоим на серверы пользователей
GOIDA_VPN_TAG: str = os.getenv("GOIDA_VPN_TAG", "v1.0.0")
GOIDA_VPN_REPO: str = "https://github.com/bozhenkas/vpnmanager"

# Aeza — реф-ссылка на VPS-провайдера
AEZA_REF_URL: str = "https://aeza.net/?ref=GOIDA"  # заменить на реальный ref-код

# stubs — заменить URL после запуска docs-сайта
DOCS_DOMAIN_URL: str = "https://docs.goida.fun/domain"
DOCS_BUY_VPS_URL: str = f"https://docs.goida.fun/vps"  # контент будет включать Aeza ref
DOCS_IP_CERT_URL: str = "https://docs.goida.fun/ip-cert"

OPEN_SOURCE_NOTICE: str = (
    "\n\n"
    "ℹ️ vpndeployer — open source бот для развёртывания личного VPN.\n"
    "Исходный код: github.com/bozhenkas/vpndeployer\n"
    "Проверьте код сами — мы не храним ваши SSH данные после деплоя."
)

SUB_PORT = 9090
DEPLOY_PROGRESS_INTERVAL = 3
