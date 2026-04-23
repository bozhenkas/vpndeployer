import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

import config
import db
from handlers import start, interview, deploy, result
from handlers.gate import ChannelGateMiddleware, gate_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


async def main() -> None:
    await db.init(config.POSTGRES_DSN)

    storage = RedisStorage.from_url(config.REDIS_URL)
    bot = Bot(
        token=config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=storage)

    # канал-гейт применяется ко всем message и callback_query
    dp.message.middleware(ChannelGateMiddleware())
    dp.callback_query.middleware(ChannelGateMiddleware())

    dp.include_router(gate_router)   # recheck callback
    dp.include_router(start.router)
    dp.include_router(interview.router)
    dp.include_router(deploy.router)
    dp.include_router(result.router)

    log.info("deployer-bot started (channel gate: %s)", config.REQUIRED_CHANNEL)
    await dp.start_polling(bot, allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    asyncio.run(main())
