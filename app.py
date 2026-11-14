import logging
import os
from pathlib import Path

from dotenv import load_dotenv

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    WebAppInfo,
    BotCommand,
)

from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from db import SessionLocal, Player, PaymentRequest
from config import CURRENCY


# ==========================================
# CONFIGURATION
# ==========================================

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env", override=True)

TOKEN = os.getenv("BOT_TOKEN", "").strip()
WEBAPP_URL = os.getenv("WEBAPP_URL", "").strip().rstrip("/")

if not TOKEN:
    raise RuntimeError("BOT_TOKEN is missing from .env")

if not WEBAPP_URL.startswith("https://"):
    raise RuntimeError("WEBAPP_URL must be an HTTPS address")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger("TrustBINGO")

AMOUNT, DETAILS = range(2)


# ==========================================
# TELEGRAM COMMAND MENU
# ==========================================

async def setup_bot_commands(application):
    commands = [
        BotCommand("start", "Start TrustBINGO"),
        BotCommand("register", "Register player"),
        BotCommand("balance", "Check balance"),
        BotCommand("deposit", "Deposit money"),
        BotCommand("withdraw", "Withdraw money"),
        BotCommand("history", "Transaction history"),
        BotCommand("instructions", "Game instructions"),
        BotCommand("cancel", "Cancel current request"),
    ]

    await application.bot.set_my_commands(commands)
    logger.info("Telegram command menu updated successfully.")


# ==========================================
# DATABASE FUNCTIONS
# ==========================================

def get_or_create_player(user):
    with SessionLocal() as db:
        player = (
            db.query(Player)
            .filter_by(telegram_id=str(user.id))
            .first()
        )

        if player is None:
            player = Player(
                telegram_id=str(user.id),
                username=user.username or "",
                full_name=user.full_name or user.first_name or "",
                balance=0,
            )

            db.add(player)
            db.commit()
            db.refresh(player)

        else:
            player.username = user.username or ""
            player.full_name = user.full_name or user.first_name or ""
            db.commit()

        return {
            "id": player.id,
            "balance": player.balance,
            "name": player.full_name,
        }


def get_player_balance(telegram_id):
    with SessionLocal() as db:
        player = (
            db.query(Player)
            .filter_by(telegram_id=str(telegram_id))
            .first()
        )

        return player.balance if player else 0


def create_payment_request(
    telegram_id,
    amount,
    reference,
    request_type,
):
    with SessionLocal() as db:
        player = (
            db.query(Player)
            .filter_by(telegram_id=str(telegram_id))
            .first()
        )

        if not player:
            raise ValueError("Player is not registered.")

        if amount <= 0:
            raise ValueError("Amount must be greater than zero.")

        if request_type == "withdrawal" and player.balance < amount:
            raise ValueError("Insufficient balance.")

        payment = PaymentRequest(
            player_id=player.id,
            amount=amount,
            reference=reference,
            status="pending",
            request_type=request_type,
        )

        db.add(payment)
        db.commit()

        return payment.id


# ==========================================
# MAIN MENU
# ==========================================

def main_menu():
    keyboard = [
        [
            InlineKeyboardButton(
                "🎮 CHOOSE ROOM",
                callback_data="choose_room",
            )
        ],
        [
            InlineKeyboardButton(
                "🎁 GoodBingo Bonus",
                web_app=WebAppInfo(url=f"{WEBAPP_URL}/bonus"),
            )
        ],
        [
            InlineKeyboardButton(
                "💰 My Balance",
                callback_data="balance",
            ),
            InlineKeyboardButton(
                "📥 Deposit",
                callback_data="deposit",
            ),
        ],
        [
            InlineKeyboardButton(
                "📤 Withdraw",
                callback_data="withdraw",
            ),
            InlineKeyboardButton(
                "📜 History",
                callback_data="history",
            ),
        ],
        [
            InlineKeyboardButton(
                "📖 Instructions",
                callback_data="instructions",
            )
        ],
    ]

    return InlineKeyboardMarkup(keyboard)


# ==========================================
# ROOM SELECTION MENU
# ==========================================

def room_menu(user_id):
    good_bingo_url = f"{WEBAPP_URL}/?stake=10&user_id={user_id}"
    super_bingo_url = f"{WEBAPP_URL}/?stake=50&user_id={user_id}"

    keyboard = [
        [
            InlineKeyboardButton(
                "🟢 GoodBingo | 10 ETB",
                web_app=WebAppInfo(url=good_bingo_url),
            )
        ],
        [
            InlineKeyboardButton(
                "🏆 SuperBingo | 50 ETB",
                web_app=WebAppInfo(url=super_bingo_url),
            )
        ],
        [
            InlineKeyboardButton(
                "⬅️ Back to Main Menu",
                callback_data="main_menu",
            )
        ],
    ]

    return InlineKeyboardMarkup(keyboard)


# ==========================================
# START COMMAND
# ==========================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    player = get_or_create_player(user)

    message = (
        f"👋 ሰላም {user.first_name}!\n\n"
        f"👤 Player: {player['name']}\n"
        f"💰 Balance: {player['balance']} {CURRENCY}\n\n"
        "Welcome to TrustBINGO!\n\n"
        "🎮 Click CHOOSE ROOM to select your game."
    )

    await update.effective_message.reply_text(
        message,
        reply_markup=main_menu(),
    )


# ==========================================
# REGISTER COMMAND
# ==========================================

async def register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    get_or_create_player(update.effective_user)

    await update.effective_message.reply_text(
        "✅ Registration successful!\n"
        "Welcome to TrustBINGO."
    )


# ==========================================
# BALANCE COMMAND
# ==========================================

async def balance_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    player = get_or_create_player(update.effective_user)

    await update.effective_message.reply_text(
        f"💰 Your balance: {player['balance']} {CURRENCY}"
    )


# ==========================================
# DEPOSIT CONVERSATION
# ==========================================

async def start_deposit(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if update.callback_query:
        await update.callback_query.answer()
        message = update.callback_query.message
    else:
        message = update.effective_message

    get_or_create_player(update.effective_user)
    context.user_data["request_type"] = "deposit"

    await message.reply_text(
        "📥 DEPOSIT REQUEST\n\n"
        "Select your payment method:\n"
        "1. CBE Birr\n"
        "2. Telebirr\n\n"
        "Then enter the amount in ETB:"
    )

    return AMOUNT


# ==========================================
# WITHDRAW CONVERSATION
# ==========================================

async def start_withdraw(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if update.callback_query:
        await update.callback_query.answer()
        message = update.callback_query.message
    else:
        message = update.effective_message

    get_or_create_player(update.effective_user)
    context.user_data["request_type"] = "withdrawal"

    await message.reply_text(
        "📤 WITHDRAWAL REQUEST\n\n"
        "Enter the amount you want to withdraw in ETB:"
    )

    return AMOUNT


# ==========================================
# RECEIVE AMOUNT
# ==========================================

async def receive_amount(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    try:
        amount = int(update.message.text.strip())
        if amount <= 0:
            raise ValueError
    except (ValueError, TypeError):
        await update.message.reply_text(
            "❌ Invalid amount.\n"
            "Please enter a positive whole number."
        )
        return AMOUNT

    request_type = context.user_data.get("request_type")

    if request_type == "withdrawal":
        balance = get_player_balance(update.effective_user.id)
        if amount > balance:
            await update.message.reply_text(
                f"❌ Insufficient balance.\n"
                f"Your balance is {balance} {CURRENCY}."
            )
            return AMOUNT

    context.user_data["amount"] = amount

    if request_type == "deposit":
        await update.message.reply_text(
            "🏦 Enter your payment method and transaction reference.\n\n"
            "Example: CBE Birr - Transaction reference 123456"
        )
    else:
        await update.message.reply_text(
            "📱 Enter your Telebirr/CBE account name and phone number "
            "for the withdrawal."
        )

    return DETAILS


# ==========================================
# RECEIVE PAYMENT DETAILS
# ==========================================

async def receive_details(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    details = update.message.text.strip()

    if len(details) < 3 or len(details) > 120:
        await update.message.reply_text(
            "Please enter valid details (3 to 120 characters)."
        )
        return DETAILS

    amount = context.user_data["amount"]
    request_type = context.user_data["request_type"]

    try:
        request_id = create_payment_request(
            telegram_id=update.effective_user.id,
            amount=amount,
            reference=details,
            request_type=request_type,
        )

        if request_type == "deposit":
            response = (
                "✅ DEPOSIT REQUEST SUBMITTED\n\n"
                f"Request ID: #{request_id}\n"
                f"Amount: {amount} {CURRENCY}\n"
                "Status: Pending admin approval.\n\n"
                "Please wait for the administrator to verify your payment."
            )
        else:
            response = (
                "✅ WITHDRAWAL REQUEST SUBMITTED\n\n"
                f"Request ID: #{request_id}\n"
                f"Amount: {amount} {CURRENCY}\n"
                "Status: Pending admin approval.\n\n"
                "Your balance has not yet been deducted."
            )

        await update.message.reply_text(
            response,
            reply_markup=main_menu(),
        )

    except ValueError as error:
        await update.message.reply_text(f"❌ {error}")

    except Exception:
        logger.exception("Payment request creation failed.")
        await update.message.reply_text(
            "❌ Could not submit your request. Please try again later."
        )

    context.user_data.pop("amount", None)
    context.user_data.pop("request_type", None)

    return ConversationHandler.END


# ==========================================
# CANCEL REQUEST
# ==========================================

async def cancel_request(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    context.user_data.pop("amount", None)
    context.user_data.pop("request_type", None)

    if update.callback_query:
        await update.callback_query.answer()
        message = update.callback_query.message
    else:
        message = update.effective_message

    await message.reply_text(
        "❌ Your current request has been cancelled.\n\n"
        "No new transaction request was submitted.\n\n"
        "You can continue using TrustBINGO.",
        reply_markup=main_menu(),
    )

    return ConversationHandler.END


# ==========================================
# TRANSACTION HISTORY
# ==========================================

async def history_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    user = update.effective_user

    with SessionLocal() as db:
        player = (
            db.query(Player)
            .filter_by(telegram_id=str(user.id))
            .first()
        )

        if not player:
            message = "No transaction history found."
        else:
            requests = (
                db.query(PaymentRequest)
                .filter_by(player_id=player.id)
                .order_by(PaymentRequest.id.desc())
                .limit(10)
                .all()
            )

            if not requests:
                message = "📜 No transaction history found."
            else:
                lines = ["📜 YOUR TRANSACTION HISTORY\n"]

                for item in requests:
                    request_type = getattr(item, "request_type", "deposit")
                    lines.append(
                        f"#{item.id} | {request_type.upper()}\n"
                        f"Amount: {item.amount} {CURRENCY}\n"
                        f"Status: {item.status.upper()}\n"
                    )

                message = "\n".join(lines)

    await update.effective_message.reply_text(message)


# ==========================================
# GAME RULES - AMHARIC
# ==========================================

GAME_RULES = """
<b>🎯 የጨዋታ ህጎች (Game Rules)</b>

━━━━━━━━━━━━━━━━━━

ጨዋታውን ለማሸነፍ በተፈለገበት
አንድ መስመር ወይም አራቱን
ኮርነሮች ቀድሞ ማግኘት።

<pre>
  B  I  N  G  O
+-----+----+-----+
|✅ ✅ ✅ ✅ ✅|  &lt;- መስመር
+                +
|                |
+                +
|                |
+                +
|                |
+-----+----+-----+

  B  I  N  G  O
+-----+----+-----+
|✅           ✅|  &lt;- 4 ኮርነሮች
+                +
|                |
+                +
|                |
+                +
|                |
+                +
|✅           ✅|
+-----+----+-----+
</pre>

💰 ከአንድ በላይ አሸናፊ ካለ
ደራሽ ገንዘቡን ይከፋፈላሉ።
"""


# ==========================================
# INSTRUCTIONS COMMAND
# ==========================================

async def instructions_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    await update.effective_message.reply_text(
        GAME_RULES,
        parse_mode="HTML",
    )


# ==========================================
# CALLBACK BUTTON HANDLER
# ==========================================

async def button_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id

    if query.data == "choose_room":
        await query.edit_message_text(
            "🎮 CHOOSE YOUR BINGO ROOM\n\n"
            "Select the room you want to enter:\n\n"
            "🟢 GoodBingo: 10 ETB\n"
            "🏆 SuperBingo: 50 ETB",
            reply_markup=room_menu(user_id),
        )

    elif query.data == "main_menu":
        player = get_or_create_player(query.from_user)

        await query.edit_message_text(
            f"👋 Welcome back, {player['name']}!\n"
            f"💰 Balance: {player['balance']} {CURRENCY}\n\n"
            "Choose an option below.",
            reply_markup=main_menu(),
        )

    elif query.data == "balance":
        balance = get_player_balance(user_id)
        await query.message.reply_text(
            f"💰 Your balance: {balance} {CURRENCY}"
        )

    elif query.data == "history":
        await history_command(update, context)

    elif query.data == "instructions":
        await instructions_command(update, context)


# ==========================================
# ERROR HANDLER
# ==========================================

async def error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE,
):
    logger.error("Telegram bot error", exc_info=context.error)


# ==========================================
# MAIN APPLICATION
# ==========================================

def main():
    application = (
        ApplicationBuilder()
        .token(TOKEN)
        .connect_timeout(30)
        .read_timeout(30)
        .write_timeout(30)
        .pool_timeout(30)
        .post_init(setup_bot_commands)
        .build()
    )

    # DEPOSIT CONVERSATION
    deposit_conversation = ConversationHandler(
        entry_points=[
            CommandHandler("deposit", start_deposit),
            CallbackQueryHandler(start_deposit, pattern="^deposit$"),
        ],
        states={
            AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_amount)],
            DETAILS: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_details)],
        },
        fallbacks=[CommandHandler("cancel", cancel_request)],
        allow_reentry=True,
    )

    # WITHDRAW CONVERSATION
    withdraw_conversation = ConversationHandler(
        entry_points=[
            CommandHandler("withdraw", start_withdraw),
            CallbackQueryHandler(start_withdraw, pattern="^withdraw$"),
        ],
        states={
            AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_amount)],
            DETAILS: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_details)],
        },
        fallbacks=[CommandHandler("cancel", cancel_request)],
        allow_reentry=True,
    )

    # REGISTER COMMAND HANDLERS
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("register", register))
    application.add_handler(CommandHandler("balance", balance_command))
    application.add_handler(CommandHandler("history", history_command))
    application.add_handler(CommandHandler("instructions", instructions_command))

    # CONVERSATION HANDLERS
    application.add_handler(deposit_conversation)
    application.add_handler(withdraw_conversation)

    # STANDALONE CANCEL HANDLER
    application.add_handler(CommandHandler("cancel", cancel_request))

    # INLINE BUTTON HANDLER
    application.add_handler(CallbackQueryHandler(button_handler))

    # ERROR HANDLER
    application.add_error_handler(error_handler)

    logger.info("TrustBINGO Telegram Bot is starting...")
    application.run_polling()


if __name__ == "__main__":
    main()