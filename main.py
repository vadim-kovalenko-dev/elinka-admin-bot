import logging
import telegram
from telegram import ReplyKeyboardRemove, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
    CallbackQueryHandler,
)

from database import Database
from dotenv import load_dotenv
import os
from datetime import datetime

# Инициализация логгера
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Загрузка переменных окружения
load_dotenv()

# Константы состояний
(
    Q_NAME, 
    Q_SUBSCRIPTION_DURATION,
    Q_FAVORITE_GENRE,
    Q_PURPOSE,
    Q_FEEDBACK,
    Q_CONFIDENTIALITY,
    STOPPING
) = range(7)

# Инициализация базы данных
db = Database()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начало диалога, проверка статуса пользователя."""
    user = update.message.from_user
    user_id = user.id
    
    # Проверяем статус пользователя
    status = db.get_user_status(user_id)
    logger.info(f"Пользователь {user_id} запросил /start, статус: {status}")
    
    if status == 'approved':
        keyboard = [[InlineKeyboardButton("Вступить в группу", url=os.getenv('GROUP_LINK'))]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "Вы уже допущены в закрытый чат Читуны Элинки. Нажмите кнопку ниже для вступления.",
            reply_markup=reply_markup
        )
        return ConversationHandler.END
    
    elif status == 'rejected':
        await update.message.reply_text(
            "❌ Ваша заявка отклонена администратором. Повторное прохождение теста невозможно."
        )
        logger.info(f"Пользователь {user_id} отклонён, доступ запрещён.")
        return ConversationHandler.END
    
    # Очищаем временные данные пользователя (ответы, введённые ранее)
    context.user_data.clear()
    
    if status == 'pending':
        # Проверяем, есть ли сохранённые ответы (пользователь завершил тест)
        if db.has_saved_responses(user_id):
            await update.message.reply_text(
                "⏳ Ваша заявка находится на рассмотрении администратора. Ожидайте решения."
            )
            logger.info(f"Пользователь {user_id} уже отправил заявку, ожидает модерации.")
            return ConversationHandler.END
        else:
            # Пользователь не завершил тест, можно начать заново
            logger.info(f"Пользователь {user_id} начинает тест заново (не завершённый ранее)")
            # Не удаляем данные из БД, так как их нет (или они не завершены)
    
    # Начинаем опрос
    await update.message.reply_text(
        "Привет, дорогой читающий пиздюк! Я рада, что ты хочешь попасть в мою фокус-группу читателей. "
        "Но мне нужно убедиться, что ты реален, а твои помыслы чисты.🥹\n\n"
        "Прошу ответить на несколько простых вопросов.👇\n\n"
        "Как тебя зовут?"
    )
    return Q_NAME

# Обработчики для каждого вопроса
async def question_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Сохраняет имя и задаёт следующий вопрос."""
    context.user_data['name'] = update.message.text
    await update.message.reply_text("Как давно ты подписан на меня?")
    return Q_SUBSCRIPTION_DURATION

async def question_subscription_duration(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Сохраняет срок подписки и задаёт следующий вопрос."""
    context.user_data['subscription_duration'] = update.message.text
    await update.message.reply_text("Какой твой любимый литературный жанр?")
    return Q_FAVORITE_GENRE

async def question_favorite_genre(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Сохраняет любимый жанр и задаёт следующий вопрос."""
    context.user_data['favorite_genre'] = update.message.text
    await update.message.reply_text("Зачем ты хочешь читать мои всратые тексты?")
    return Q_PURPOSE

async def question_purpose(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Сохраняет цель и задаёт следующий вопрос с inline-кнопками."""
    context.user_data['purpose'] = update.message.text
    
    keyboard = [
        [
            InlineKeyboardButton("Да", callback_data='feedback_Да'),
            InlineKeyboardButton("Иногда", callback_data='feedback_иногда'),
            InlineKeyboardButton("Нет", callback_data='feedback_нет')
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "Ты готов давать обратную связь на прочитанное?",
        reply_markup=reply_markup
    )
    return Q_FEEDBACK

async def question_feedback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает ответ по обратной связи через inline-кнопки."""
    query = update.callback_query
    await query.answer()
    
    # Извлекаем ответ из callback_data (формат: feedback_ответ)
    answer = query.data.split('_')[1]
    context.user_data['feedback'] = answer
    
    keyboard = [
        [
            InlineKeyboardButton("Да", callback_data='conf_Да'),
            InlineKeyboardButton("Нет", callback_data='conf_Нет')
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        text=f"Твой ответ: {answer}\n\n"
             "Ты готов соблюдать конфиденциальность и не разглашать прочитанное другим лицам?",
        reply_markup=reply_markup
    )
    return Q_CONFIDENTIALITY

async def question_confidentiality(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает ответ о конфиденциальности и завершает опрос."""
    query = update.callback_query
    await query.answer()
    
    answer = query.data.split('_')[1]
    context.user_data['confidentiality'] = answer
    user_id = query.from_user.id
    username = query.from_user.username
    
    # Сохраняем все ответы в базе данных
    db.save_user_response(user_id, username, context.user_data)
    
    # Отправляем ответы на модерацию админу
    admin_chat_id = os.getenv('ADMIN_CHAT_ID')
    response_text = (
        f"🔔 Новый кандидат!\n\n"
        f"👤 Имя: {context.user_data['name']}\n"
        f"🆔 ID: {user_id}\n"
        f"📅 Подписан: {context.user_data['subscription_duration']}\n"
        f"📚 Любимый жанр: {context.user_data['favorite_genre']}\n"
        f"🎯 Цель: {context.user_data['purpose']}\n"
        f"💬 Обратная связь: {context.user_data['feedback']}\n"
        f"🔐 Конфиденциальность: {context.user_data['confidentiality']}"
    )
    
    keyboard = [
        [
            InlineKeyboardButton("✅ Одобрить", callback_data=f'approve_{user_id}'),
            InlineKeyboardButton("❌ Отклонить", callback_data=f'reject_{user_id}')
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await context.bot.send_message(
        chat_id=admin_chat_id, 
        text=response_text, 
        reply_markup=reply_markup
    )
    
    await query.edit_message_text(
        text=f"Твой ответ: {answer}\n\n"
             "Спасибо, я изучу твои ответы в скором времени и добавлю в закрытый чат!"
    )
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отменяет диалог."""
    await update.message.reply_text(
        "Опрос отменён.", reply_markup=ReplyKeyboardRemove()
    )
    return ConversationHandler.END

# Обработчик ответов админа
async def handle_admin_decision(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    decision, user_id = query.data.split('_')
    user_id = int(user_id)
    admin_id = query.from_user.id
    
    logger.info(f"Админ {admin_id} принял решение {decision} для пользователя {user_id}")
    
    db.update_moderation_status(user_id, 'approved' if decision == 'approve' else 'rejected', admin_id)
    
    decision_text = "одобрен" if decision == 'approve' else "отклонён"
    await query.answer(f"Пользователь {decision_text}!")
    
    # Удаляем кнопки после выбора
    await query.edit_message_reply_markup(reply_markup=None)
    
    # Отправляем сообщение пользователю
    if decision == 'approve':
        keyboard = [[InlineKeyboardButton("Вступить в группу", url=os.getenv('GROUP_LINK'))]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await context.bot.send_message(
            chat_id=user_id,
            text="🎉 Поздравляю! Ваша заявка одобрена. Нажмите кнопку ниже, чтобы присоединиться к закрытому чату Читуны Элинки.",
            reply_markup=reply_markup
        )
        logger.info(f"Пользователь {user_id} одобрен, отправлено сообщение с кнопкой.")
    else:
        await context.bot.send_message(
            chat_id=user_id,
            text="😞 К сожалению, твоя заявка отклонена."
        )
        logger.info(f"Пользователь {user_id} отклонён, отправлено уведомление.")

# Админ-панель
async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /admin, показывает админ-панель."""
    admin_chat_id = os.getenv('ADMIN_CHAT_ID')
    if str(update.effective_user.id) != admin_chat_id:
        await update.message.reply_text("У вас нет доступа к админ-панели.")
        return
    
    keyboard = [
        [InlineKeyboardButton("📊 Статистика", callback_data='admin_stats')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "Админ-панель управления ботом. Выберите действие:",
        reply_markup=reply_markup
    )

async def handle_admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик колбэков админ-панели."""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    admin_chat_id = os.getenv('ADMIN_CHAT_ID')
    if str(query.from_user.id) != admin_chat_id:
        # Отправляем новое сообщение вместо редактирования, если нет доступа
        await query.message.reply_text("У вас нет доступа к админ-панели.")
        return
    
    try:
        if data == 'admin_startup_button' or data == 'admin_back':
            keyboard = [
                [InlineKeyboardButton("📊 Статистика", callback_data='admin_stats')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            try:
                await query.edit_message_text(
                    "Админ-панель управления ботом. Выберите действие:",
                    reply_markup=reply_markup
                )
            except telegram.error.BadRequest as e:
                # Игнорируем ошибку, если сообщение не изменилось
                if "Message is not modified" in str(e):
                    logger.warning(f"Сообщение не изменилось при возврате в главное меню: {e}")
                else:
                    raise
            logger.info(f"Админ {query.from_user.id} {'открыл админ-панель через кнопку' if data == 'admin_startup_button' else 'вернулся в главное меню'}")
        elif data == 'admin_stats':
            await show_stats(query)
            logger.info(f"Админ {query.from_user.id} запросил статистику")
    except Exception as e:
        logger.error(f"Ошибка в обработке админ-колбэка {data}: {e}")
        try:
            await query.answer(f"Ошибка: {str(e)[:50]}...", show_alert=True)
        except:
            pass

async def show_stats(query):
    """Показывает статистику по пользователям."""
    approved_count = db.get_approved_users_count()
    rejected_count = db.get_rejected_users_count()
    
    message_text = (
        "📊 Статистика пользователей:\n\n"
        f"✅ Одобрено: {approved_count}\n"
        f"❌ Отклонено: {rejected_count}"
    )
    
    keyboard = [
        [InlineKeyboardButton("↩️ Вернуться в главное меню", callback_data='admin_back')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(message_text, reply_markup=reply_markup)

async def send_admin_startup_message(application):
    """Отправляет сообщение админу при запуске бота."""
    admin_chat_id = os.getenv('ADMIN_CHAT_ID')
    if admin_chat_id:
        try:
            keyboard = [
                [InlineKeyboardButton("⚙️ Админ-панель", callback_data='admin_startup_button')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await application.bot.send_message(
                chat_id=admin_chat_id,
                text="✅ Бот запущен и готов к работе.",
                reply_markup=reply_markup
            )
        except Exception as e:
            logger.error(f"Не удалось отправить сообщение админу: {e}")

def main() -> None:
    application = Application.builder().token(os.getenv('TELEGRAM_TOKEN')).build()
    
    # Отправляем сообщение админу после запуска
    application.post_init = send_admin_startup_message
    
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            Q_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, question_name)],
            Q_SUBSCRIPTION_DURATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, question_subscription_duration)],
            Q_FAVORITE_GENRE: [MessageHandler(filters.TEXT & ~filters.COMMAND, question_favorite_genre)],
            Q_PURPOSE: [MessageHandler(filters.TEXT & ~filters.COMMAND, question_purpose)],
            Q_FEEDBACK: [CallbackQueryHandler(question_feedback, pattern='^feedback_')],
            Q_CONFIDENTIALITY: [CallbackQueryHandler(question_confidentiality, pattern='^conf_')],
        },
        fallbacks=[CommandHandler('cancel', cancel), CommandHandler('start', start)],
    )
    
    application.add_handler(conv_handler)
    application.add_handler(CallbackQueryHandler(handle_admin_decision, pattern='^(approve|reject)_'))
    application.add_handler(CommandHandler('admin', admin_command))
    application.add_handler(CallbackQueryHandler(handle_admin_callback, pattern='^admin_'))
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
