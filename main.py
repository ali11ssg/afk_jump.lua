import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from config import BOT_TOKEN, ADMIN_IDS
from data import init_db
from proxy import router as proxy_router, setup_proxy_tasks
from user import router as user_router
from ctools import router as ctools_router
from chk import router as chk_router
from start import router as start_router
from admin import router as admin_router
from pp_chk import router as pp_router
from admin_pp_extra import router as pp_extra_router

logging.basicConfig(
    level=logging.ERROR,
    format="%(asctime)s  [%(levelname)s]  %(name)s\n%(message)s\n",
)
logging.getLogger("aiogram").setLevel(logging.ERROR)
logging.getLogger("aiohttp").setLevel(logging.ERROR)
logging.getLogger("asyncio").setLevel(logging.ERROR)
log = logging.getLogger(__name__)

async def main():
    log.info("Starting bot...")
    await init_db()
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    dp.include_router(start_router)
    dp.include_router(proxy_router)
    dp.include_router(user_router)
    dp.include_router(ctools_router)
    dp.include_router(chk_router)
    dp.include_router(pp_extra_router)
    dp.include_router(admin_router)
    dp.include_router(pp_router)
    setup_proxy_tasks(bot)
    log.info("Bot is ready.")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Bot stopped.")
        sys.exit(0)