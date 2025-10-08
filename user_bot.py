# user_bot.py

import logging
from telegram import Update, ReplyKeyboardRemove, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import ContextTypes, Application, CommandHandler, MessageHandler, filters
from datetime import datetime
import pytz
import aiohttp
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

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        user_id = update.effective_user.id
        first_name = update.effective_user.first_name or "Пользователь"
        username = update.effective_user.username or "нет username"

        logger.info(f"Пользователь {user_id} ({username}) нажал /start")

        if not is_working_time():
            await update.message.reply_text(
                "❌ Система отметки работает только в учебное время:\n"
                "Понедельник-Пятница с 8:00 до 20:00",
                reply_markup=ReplyKeyboardRemove()
            )
            return

        if user_id not in location_attempts:
            location_attempts[user_id] = 0

        if location_attempts[user_id] >= 3:
            await update.message.reply_text(
                "❌ Слишком много попыток. Обратитесь к преподавателю.",
                reply_markup=ReplyKeyboardRemove()
            )
            return

        existing_fio = None
        if user_id in user_data and 'fio' in user_data[user_id]:
            existing_fio = user_data[user_id]['fio']

        keyboard = [[
            KeyboardButton("📍 Отправить геолокацию", request_location=True)
        ]]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)

        await update.message.reply_text(
            f"Привет, {first_name}! 👋\n"
            "Для отметки о посещении нужна твоя геолокация.\n\n"
            "📍 Нажми кнопку ниже, чтобы поделиться местоположением\n"
            "✅ Отметка возможна только в учебном кабинете",
            reply_markup=reply_markup
        )

        user_data[user_id] = {
            'state': 'awaiting_location',
            'first_name': first_name,
            'fio': existing_fio
        }

        logger.info(f"Пользователь {user_id} ожидает отправки геолокации (fio сохранён: {existing_fio})")

    except Exception as e:
        logger.error(f"Ошибка в обработке /start: {e}")
        await update.message.reply_text("Произошла ошибка. Попробуйте еще раз.")

async def handle_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        user_id = update.effective_user.id
        username = update.effective_user.username or "нет username"

        if user_id not in user_data or user_data[user_id].get('state') != 'awaiting_location':
            await update.message.reply_text(
                "Сначала нажми /start для начала процесса отметки",
                reply_markup=ReplyKeyboardRemove()
            )
            return

        user_lat = update.message.location.latitude
        user_lon = update.message.location.longitude
        distance_km = calculate_distance(CLASSROOM_LAT, CLASSROOM_LON, user_lat, user_lon)
        distance_meters = distance_km * 1000

        logger.info(f"Пользователь {user_id} отправил геолокацию: {distance_meters:.0f}м от кабинета")

        if distance_meters > ALLOWED_RADIUS * 1000:
            location_attempts[user_id] = location_attempts.get(user_id, 0) + 1
            attempts_left = 3 - location_attempts[user_id]
            await update.message.reply_text(
                f"❌ Вы находитесь вне учебного корпуса!\n"
                f"📏 Расстояние от кабинета: {distance_meters:.0f} метров\n"
                f"✅ Требуется: within {ALLOWED_RADIUS * 1000:.0f} метров\n\n"
                f"🔢 Осталось попыток: {attempts_left}",
                reply_markup=ReplyKeyboardRemove()
            )
            logger.warning(f"Попытка отметиться издалека: {username} ({distance_meters:.0f}м)")
            return

        location_attempts[user_id] = 0

        if user_id in user_data and 'fio' in user_data[user_id] and user_data[user_id]['fio']:
            fio = user_data[user_id]['fio']
            await send_alert_to_admin(fio, username, user_id, distance_meters, is_new=False)
            await update.message.reply_text(
                f"✅ {fio}, ваше присутствие отмечено!\n"
                f"📏 В радиусе: {distance_meters:.0f} метров",
                reply_markup=ReplyKeyboardRemove()
            )
            logger.info(f"Повторное посещение: {fio} ({distance_meters:.0f}м)")
        else:
            await update.message.reply_text(
                "📍 Геолокация подтверждена! Вы в учебном корпусе.\n\n"
                "Теперь введи свои ФИО (например: Иванов Иван Иванович):",
                reply_markup=ReplyKeyboardRemove()
            )
            user_data[user_id] = {'state': 'awaiting_fio', 'location_verified': True}
            logger.info(f"Геолокация подтверждена для {user_id}, ожидание ФИО")

    except Exception as e:
        logger.error(f"Ошибка обработки геолокации: {e}")
        await update.message.reply_text("Ошибка обработки геолокации. Попробуйте еще раз.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        user_id = update.effective_user.id
        username = update.effective_user.username or "нет username"
        user_info = user_data.get(user_id, {})

        if user_info.get('state') == 'awaiting_fio' and user_info.get('location_verified'):
            fio = update.message.text.strip()
            if len(fio) < 2:
                await update.message.reply_text("Пожалуйста, введите настоящие ФИО (например: Иванов Иван Иванович)")
                return

            user_data[user_id] = {'fio': fio, 'state': 'registered', 'location_verified': True}
            await send_alert_to_admin(fio, username, user_id, 5, is_new=True)
            await update.message.reply_text(
                f"🎉 Спасибо, {fio}! Регистрация прошла успешно!\n\n"
                "Теперь при следующем посещении просто отсканируй QR-код снова - "
                "система автоматически определит твое местоположение и отметит присутствие!",
                reply_markup=ReplyKeyboardRemove()
            )
            logger.info(f"Новый пользователь зарегистрирован: {fio}")

        else:
            await update.message.reply_text(
                "Для отметки отсканируй QR-код и следуй инструкциям 📱\n"
                "Если ты уже регистрировался, просто нажми /start",
                reply_markup=ReplyKeyboardRemove()
            )

    except Exception as e:
        logger.error(f"Ошибка обработки сообщения: {e}")
        await update.message.reply_text("Произошла ошибка. Попробуйте еще раз.")

def main():
    """Основная функция для запуска бота"""
    print("✅ User бот запущен!")
    print("📍 Координаты:", CLASSROOM_LAT, CLASSROOM_LON)
    print("📏 Разрешенный радиус:", ALLOWED_RADIUS * 1000, "метров")
    print("⏰ Работает: Пн-Пт, круглосуточно")
    
    try:
        application = Application.builder().token(USER_BOT_TOKEN).build()
        
        application.add_handler(CommandHandler("start", start))
        application.add_handler(MessageHandler(filters.LOCATION, handle_location))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        
        print("🔄 Бот запускается...")
        application.run_polling()
    except Exception as e:
        logger.error(f"Ошибка запуска бота: {e}")
        print(f"❌ Ошибка запуска бота: {e}")

if __name__ == '__main__':
    main()
