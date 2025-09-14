import logging
from telegram.ext import Application, CommandHandler, MessageHandler, filters
import requests
import re

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = '8074708047:AAGlpHMJY6_R3zTWsWXWCgHmbZHTDg-dVSg'
BACKEND_URL = "http://localhost:8000/complaint"

async def start(update, context):
    welcome_text = (
        "Привет! Я бот для приема жалоб в сфере ЖКХ.\n\n"
        "<b>СКОПИРУЙТЕ И ЗАПОЛНИТЕ ШАБЛОН:</b>\n\n"
        "<code>Адрес места происшествия: г. Москва, ул. Московская, 1\n"
        "Описание происшествия: Протекает крыша в 1 подъезде</code>"
    )
    await update.message.reply_text(welcome_text, parse_mode='HTML')

async def handle_message(update, context):
    user_text = update.message.text

    if is_complaint_valid(user_text):
        try:
            response = requests.post(BACKEND_URL, json={"text": user_text})

            if response.status_code == 200:
                await update.message.reply_text("Спасибо! Ваша жалоба принята и будет рассмотрена.")
                logger.info(f"Жалоба принята: {user_text}")
            else:
                await update.message.reply_text("Ошибка при обработке жалобы. Попробуйте ещё раз.")
                logger.error(f"Ошибка API: {response.status_code} - {response.text}")

        except Exception as e:
            await update.message.reply_text("Ошибка соединения с сервером. Попробуйте позже.")
            logger.error(f"Ошибка отправки: {str(e)}")
    else:
        error_message = (
            "Пожалуйста, заполните ОБА поля в шаблоне:\n\n"
            "<code>Адрес места происшествия: г. Москва, ул. Московская, 1\n"
            "Описание происшествия: Протекает крыша в 1 подъезде</code>"
        )
        await update.message.reply_text(error_message, parse_mode='HTML')
        logger.info(f"Невалидная жалоба: {user_text}")

def is_complaint_valid(text):
    has_address = re.search(r'Адрес[^:\n]*:\s*([^;\n]+)', text, re.IGNORECASE)
    has_description = re.search(r'Описание[^:\n]*:\s*([^;\n]+)', text, re.IGNORECASE)

    if has_address and has_description:
        address = has_address.group(1).strip()
        description = has_description.group(1).strip()

        invalid_values = ['', '.....', '......', '…', 'не указан']
        return (address not in invalid_values and description not in invalid_values)

    return False

def main():
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Бот запущен")
    application.run_polling()

if __name__ == '__main__':
    main()