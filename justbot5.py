
import logging
from datetime import datetime, timedelta
from telegram import (
    Update,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    filters,
    ContextTypes
)
from telegram.error import TelegramError

# ================== НАСТРОЙКИ ==================
TOKEN = "8664969857:AAEfxruCXnTehC-mNzud825qF1nggMTytuo"
CHANNEL_ID = "@fleamarketuser"                # Юзернейм канала
CHANNEL_LINK = "https://t.me/fleamarketuser"  # Ссылка на канал
BOT_USERNAME = "fleauserbot"               # Замените на реальный юзернейм бота (например, flea_user_bot)

# Состояния для ConversationHandler
(
    TYPING_USERNAME,
    TYPING_DESCRIPTION,
    TYPING_CONTACT
) = range(3)

# Включим логирование
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# ================== ХРАНЕНИЕ ДАННЫХ ==================
# В реальном проекте лучше использовать базу данных или Redis
user_post_data = {}       # временные данные поста (user_id -> dict)
last_post_times = {}      # время последнего поста (user_id -> timestamp)

# ================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==================
def get_main_keyboard():
    """Клавиатура главного меню."""
    keyboard = [[KeyboardButton("📝 Создать пост")]]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_post_inline_keyboard():
    """Инлайн-кнопки для поста в канале."""
    keyboard = [
        [InlineKeyboardButton("📢 Подписаться на канал", url=CHANNEL_LINK)],
        [InlineKeyboardButton("✍️ Сделать пост", url=f"https://t.me/{BOT_USERNAME}?start=create")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_subscribe_keyboard():
    """Клавиатура для неподписанных пользователей."""
    keyboard = [
        [InlineKeyboardButton("📢 Подписаться", url=CHANNEL_LINK)],
        [InlineKeyboardButton("🔄 Я подписался", callback_data="check_sub_after_sub")]
    ]
    return InlineKeyboardMarkup(keyboard)

async def check_subscription(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Проверяет, подписан ли пользователь на канал."""
    try:
        member = await context.bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        # Статусы, которые считаются подпиской
        return member.status in ("member", "administrator", "creator")
    except TelegramError as e:
        logger.error(f"Ошибка при проверке подписки для {user_id}: {e}")
        # Если не можем проверить (бот не админ или канал закрыт), пропускаем проверку
        # Можно также считать, что подписка не требуется, но лучше сообщить об ошибке
        return False

def can_create_post(user_id: int) -> tuple[bool, int]:
    """Проверяет, может ли пользователь создать пост (прошло ли 10 минут). Возвращает (можно, осталось_секунд)."""
    if user_id not in last_post_times:
        return True, 0
    last_time = last_post_times[user_id]
    now = datetime.now().timestamp()
    diff = now - last_time
    if diff >= 600:  # 10 минут = 600 секунд
        return True, 0
    else:
        return False, int(600 - diff)

# ================== ОБРАБОТЧИКИ ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /start. Приветствие и главное меню."""
    user = update.effective_user
    await update.message.reply_text(
        f"Привет, {user.first_name}!\n\n"
        "Я бот для размещения объявлений о продаже юзернеймов в канале "
        f"{CHANNEL_ID}.\n\n"
        "Нажми «Создать пост», чтобы начать.",
        reply_markup=get_main_keyboard()
    )

async def start_create(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Точка входа в создание поста (кнопка или команда /create)."""
    user_id = update.effective_user.id

    # 1. Проверка временного ограничения
    can_post, seconds_left = can_create_post(user_id)
    if not can_post:
        minutes_left = seconds_left // 60
        seconds = seconds_left % 60
        await update.message.reply_text(
            f"⏳ Вы уже создавали пост недавно.\n"
            f"Подождите ещё {minutes_left} мин {seconds} сек перед созданием нового.",
            reply_markup=get_main_keyboard()
        )
        return ConversationHandler.END

    # 2. Проверка подписки
    if not await check_subscription(user_id, context):
        await update.message.reply_text(
            "❌ Чтобы создать пост, нужно быть подписанным на канал.\n\n"
            "Подпишитесь и нажмите «Я подписался».",
            reply_markup=get_subscribe_keyboard()
        )
        return ConversationHandler.END

    # Всё хорошо – начинаем диалог
    await update.message.reply_text(
        "Давайте создадим пост.\n\n"
        "Введите **юзернейм**, который вы продаёте (например, @example или просто example):",
        parse_mode="Markdown"
    )
    return TYPING_USERNAME

async def check_subscription_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик нажатия на кнопку 'Я подписался'."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if await check_subscription(user_id, context):
        await query.edit_message_text(
            "✅ Подписка подтверждена! Нажмите «Создать пост» ещё раз, чтобы продолжить.",
            reply_markup=get_main_keyboard()
        )
    else:
        await query.edit_message_text(
            "❌ Подписка не найдена. Убедитесь, что вы нажали «Подписаться» и действительно вступили в канал.\n\n"
            "После подписки нажмите кнопку ниже:",
            reply_markup=get_subscribe_keyboard()
        )

async def receive_username(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получаем юзернейм для продажи."""
    user_id = update.effective_user.id
    username_for_sale = update.message.text.strip()

    if not username_for_sale:
        await update.message.reply_text("Пожалуйста, введите непустое значение.")
        return TYPING_USERNAME

    # Сохраняем во временном хранилище
    if user_id not in user_post_data:
        user_post_data[user_id] = {}
    user_post_data[user_id]['username_for_sale'] = username_for_sale

    await update.message.reply_text(
        "Отлично! Теперь напишите **информацию о юзернейме** (почему его стоит купить, особенности и т.д.):",
        parse_mode="Markdown"
    )
    return TYPING_DESCRIPTION

async def receive_description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получаем описание юзернейма."""
    user_id = update.effective_user.id
    description = update.message.text.strip()

    if not description:
        await update.message.reply_text("Описание не может быть пустым. Попробуйте ещё раз.")
        return TYPING_DESCRIPTION

    user_post_data[user_id]['description'] = description

    await update.message.reply_text(
        "Теперь укажите ваш **контакт для связи** (например, @username или ссылка на Telegram).\n"
        "Покупатели будут писать именно вам.",
        parse_mode="Markdown"
    )
    return TYPING_CONTACT

async def receive_contact(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получаем контакт продавца, публикуем пост в канал и завершаем диалог."""
    user_id = update.effective_user.id
    contact = update.message.text.strip()

    if not contact:
        await update.message.reply_text("Пожалуйста, укажите контакт.")
        return TYPING_CONTACT

    # Проверяем, что все данные собраны
    if user_id not in user_post_data or 'username_for_sale' not in user_post_data[user_id] or 'description' not in user_post_data[user_id]:
        await update.message.reply_text("Произошла ошибка. Начните заново с /start.")
        return ConversationHandler.END

    data = user_post_data.pop(user_id)  # извлекаем и удаляем временные данные
    username_for_sale = data['username_for_sale']
    description = data['description']

    # Формируем текст поста
    post_text = (
        f"📢 **Продаётся юзернейм:** {username_for_sale}\n\n"
        f"📝 **Описание:** {description}\n\n"
        f"📞 **Связь:** {contact}"
    )

    # Пытаемся отправить пост в канал
    try:
        await context.bot.send_message(
            chat_id=CHANNEL_ID,
            text=post_text,
            parse_mode="Markdown",
            reply_markup=get_post_inline_keyboard()
        )
        # Запоминаем время успешной публикации
        last_post_times[user_id] = datetime.now().timestamp()
        await update.message.reply_text(
            "✅ Ваш пост успешно опубликован в канале!\n\n"
            "Вернуться в главное меню — /start",
            reply_markup=get_main_keyboard()
        )
    except Exception as e:
        logger.error(f"Ошибка отправки в канал: {e}")
        await update.message.reply_text(
            "❌ Не удалось опубликовать пост. Попробуйте позже или свяжитесь с администратором.",
            reply_markup=get_main_keyboard()
        )

    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отмена диалога."""
    user_id = update.effective_user.id
    if user_id in user_post_data:
        del user_post_data[user_id]
    await update.message.reply_text(
        "Действие отменено. Возвращайтесь, когда будете готовы создать пост.",
        reply_markup=get_main_keyboard()
    )
    return ConversationHandler.END

async def handle_unknown(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка сообщений вне диалога."""
    await update.message.reply_text(
        "Используйте /start для начала работы.",
        reply_markup=get_main_keyboard()
    )

# ================== ЗАПУСК БОТА ==================
def main() -> None:
    # Создаём Application
    application = Application.builder().token(TOKEN).build()

    # Диалог создания поста
    conv_handler = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("^(📝 Создать пост)$"), start_create),
            CommandHandler("create", start_create)
        ],
        states={
            TYPING_USERNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_username)],
            TYPING_DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_description)],
            TYPING_CONTACT: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_contact)],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            MessageHandler(filters.COMMAND, cancel)  # любая команда прерывает диалог
        ],
        name="create_post_conversation",
        persistent=False,
    )

    application.add_handler(conv_handler)
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(check_subscription_callback, pattern="^check_sub_after_sub$"))
    # Обработчик для любых других сообщений вне диалога
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_unknown))

    # Запускаем бота
    application.run_polling()

if __name__ == "__main__":
    main()
