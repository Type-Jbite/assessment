# user_bot.py

import logging
from telegram import Update, ReplyKeyboardRemove, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import ContextTypes
from datetime import datetime
import pytz
import aiohttp  # ← ЗАМЕНИЛИ requests НА aiohttp
import json
import asyncio

# === КОНФИГУРАЦИЯ ===
USER_BOT_TOKEN = "8491896072:AAEXBmlsdjFKKinRB-rCbH-ZcFfOktay5_o"
ADMIN_CHAT_ID = "-1002729661400"

# === ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ===
user_data = {}
location_attempts = {}

# === ИМПОРТ ИЗ SHARED.PY ===
from shared import (
    CLASSROOM_LAT, CLASSROOM_LON, ALLOWED_RADIUS,
    calculate_distance
)

# === ЛОГИРОВАНИЕ ===
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def is_working_time():
    now = datetime.now()
    if now.weekday() >= 5:
        return False
    return True

async def send_alert_to_admin(fio: str, username: str, user_id: int, distance: float, is_new: bool = False):
    moscow_tz = pytz.timezone('Europe/Moscow')
    time_now = datetime.now(moscow_tz).strftime("%d.%m.%Y в %H:%M:%S")
    emoji = "🎉" if is_new else "✅"
    status = "Новая регистрация!" if is_new else "Повторное посещение"
    message_text = f"{emoji} <b>{status}</b>\n\n" \
                   f"<b>Ученик:</b> {fio}\n" \
                   f"<b>Время:</b> {time_now}\n" \
                   f"<b>Расстояние от кабинета:</b> {distance:.0f} м\n" \
                   f"<b>Username:</b> @{username if username else 'не указан'}\n" \
                   f"<b>User ID:</b> <code>{user_id}</code>\n\n" \
                   f"<b>Координаты:</b> {CLASSROOM_LAT}, {CLASSROOM_LON}"
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"https://api.telegram.org/bot{USER_BOT_TOKEN}/sendMessage",
                json={
                    "chat_id": ADMIN_CHAT_ID,
                    "text": message_text,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True
                },
                timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                if response.status == 200:
                    logger.info(f"Уведомление отправлено в чат: {fio} ({distance}м)")
                else:
                    text = await response.text()
                    logger.error(f"Ошибка отправки: {response.status} - {text}")
    except Exception as e:
        logger.error(f"Ошибка отправки уведомления в чат: {e}")

# ... остальной код остается таким же ...

if __name__ == '__main__':
    print("✅ User бот запущен!")
    print("📍 Координаты:", CLASSROOM_LAT, CLASSROOM_LON)
    print("📏 Разрешенный радиус:", ALLOWED_RADIUS * 1000, "метров")
    print("⏰ Работает: Пн-Пт, круглосуточно")

    import asyncio
    from telegram.ext import Application, CommandHandler, MessageHandler, filters

    async def main():
        """Основная асинхронная функция"""
        application = Application.builder().token(USER_BOT_TOKEN).build()
        
        application.add_handler(CommandHandler("start", start))
        application.add_handler(MessageHandler(filters.LOCATION, handle_location))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        
        print("🔄 Бот запускается...")
        await application.run_polling()

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 User бот остановлен")
