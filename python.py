import logging
import threading
from flask import Flask, render_template, request, jsonify
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

# --- CONFIGURATION ---
TOKEN = "9217823582:AAFVDA1nkGwPJ86BKP1PzbcoekWZS507NoM"
WEBAPP_URL = "https://YOUR-NGROK-URL.ngrok-free.app"  # Replace with your active ngrok HTTPS URL

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# Mock database
users_db = {}

# ==========================================
# FLASK WEB APP & API ROUTES
# ==========================================
app = Flask(__name__)

@app.route('/')
def index():
    stake = request.args.get('stake', '10')
    user_id = request.args.get('user_id', '12345')
    if user_id not in users_db:
        users_db[user_id] = {"balance": 0.0, "name": "Player"}
    return render_template('index.html', stake=stake, balance=users_db[user_id]["balance"])

@app.route('/bonus')
def bonus():
    return render_template('bonus.html')

@app.route('/api/balance', methods=['GET'])
def get_balance():
    user_id = request.args.get('user_id', '12345')
    balance = users_db.get(user_id, {}).get("balance", 0.0)
    return jsonify({"balance": balance})

def run_flask():
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)


# ==========================================
# TELEGRAM BOT HANDLERS & SAFE SENDER
# ==========================================

async def safe_reply(update: Update, text: str, reply_markup=None):
    """Helper function to retry sending messages if network connection drops."""
    for attempt in range(3):
        try:
            if update.message:
                return await update.message.reply_text(text, reply_markup=reply_markup)
            elif update.callback_query and update.callback_query.message:
                return await update.callback_query.message.reply_text(text, reply_markup=reply_markup)
            break
        except Exception as e:
            logger.warning(f"Connection attempt {attempt + 1} failed: {e}")
            if attempt == 2:
                logger.error("Failed to send message after 3 attempts due to network error.")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    user_id = user.id
    
    if user_id not in users_db:
        users_db[user_id] = {
            "name": user.first_name,
            "balance": 0.0,
            "registered": True
        }
    
    welcome_text = (
        f"👋 ሰላም (Hello) {user.first_name}!\n\n"
        f"👤 User: {user.first_name}\n"
        f"💰 Balance: {users_db[user_id]['balance']} ETB\n\n"
        "Choose an option below or use the menu commands:"
    )
    
    keyboard = [
        [InlineKeyboardButton("🎮 PLAY | 10 ብር", web_app=WebAppInfo(url=f"{WEBAPP_URL}/?user_id={user_id}&stake=10"))],
        [InlineKeyboardButton("SuperBingo | 50 ብር", web_app=WebAppInfo(url=f"{WEBAPP_URL}/?user_id={user_id}&stake=50"))],
        [InlineKeyboardButton("⚽ GoodBingo Bonus", web_app=WebAppInfo(url=f"{WEBAPP_URL}/bonus"))],
        [InlineKeyboardButton("💳 My Balance", callback_data="balance"),
         InlineKeyboardButton("📥 Deposit", callback_data="deposit")],
        [InlineKeyboardButton("📤 Withdraw", callback_data="withdraw"),
         InlineKeyboardButton("📜 History", callback_data="history")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await safe_reply(update, welcome_text, reply_markup=reply_markup)

async def register(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    user_id = user.id
    if user_id not in users_db:
        users_db[user_id] = {"name": user.first_name, "balance": 0.0, "registered": True}
    else:
        users_db[user_id]["registered"] = True
    await safe_reply(update, "✅ Registration successful! Welcome to GoodBingo.")

async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    bal = users_db.get(user_id, {}).get("balance", 0.0)
    await safe_reply(update, f"💰 ሒሳብ ሓሪ (Available Balance): {bal} ETB")

async def deposit_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [
        [InlineKeyboardButton("CBE BIRR", callback_data="dep_cbe")],
        [InlineKeyboardButton("TELE BIRR", callback_data="dep_tele")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await safe_reply(update, "📥 **ማዕከል ማገዣ ይምረጡ (Select Deposit Method):**", reply_markup=reply_markup)

async def withdraw_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await safe_reply(update, "📤 **ወጣሁ (Withdraw Funds)**\nእባክዎ ማውጣት የሚፈልጉትን መጠን ያስገቡ (Enter amount to withdraw):")

async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await safe_reply(update, "📜 **የክፍያ ታሪክ (Transaction History):**\nምንም ታሪክ የለም። (No recent transactions.)")

async def instructions_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    rules = (
        "📖 **የልዩነት ህጎች (Game Rules)**\n\n"
        "ቢንጎን ለመጫወት በአግድም፣ በቁሙ ወይም በሰያፍ ካርዶች ቁጥር ሙሉ ማሟላት።\n\n"
        "B I N G O\n"
        "☑ - ☑ - ☑ - ☑ - ☑ (አግድም)\n"
        "↓   ↓   ↓   ↓   ↓ (ቁሙ)\n"
    )
    await safe_reply(update, rules)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    if query.data == "balance":
        bal = users_db.get(user_id, {}).get("balance", 0.0)
        await safe_reply(update, f"💰 Balance: {bal} ETB")
    elif query.data == "deposit":
        keyboard = [
            [InlineKeyboardButton("CBE BIRR", callback_data="dep_cbe")],
            [InlineKeyboardButton("TELE BIRR", callback_data="dep_tele")]
        ]
        await safe_reply(update, "📥 **ማዕከል ማገዣ ይምረጡ (Select Deposit Method):**", reply_markup=InlineKeyboardMarkup(keyboard))
    elif query.data == "withdraw":
        await safe_reply(update, "📤 Enter amount to withdraw:")
    elif query.data == "history":
        await safe_reply(update, "📜 No transactions found.")
    elif query.data.startswith("dep_"):
        bank = query.data.split("_")[1].upper()
        await safe_reply(update, f"🏦 Please send deposit amount for {bank} to account: `1000123456789` and send receipt.")

def main():
    # Start Flask server in background thread
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    print("🌐 Flask Web Server started on http://127.0.0.1:5000")

    # Start Telegram Bot with extended timeouts and pool timeouts
    application = (
        ApplicationBuilder()
        .token(TOKEN)
        .connect_timeout(30.0)
        .read_timeout(30.0)
        .write_timeout(30.0)
        .pool_timeout(30.0)
        .build()
    )
    
    # Register all command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("register", register))
    application.add_handler(CommandHandler("balance", balance_command))
    application.add_handler(CommandHandler("deposit", deposit_command))
    application.add_handler(CommandHandler("withdraw", withdraw_command))
    application.add_handler(CommandHandler("history", history_command))
    application.add_handler(CommandHandler("instructions", instructions_command))
    application.add_handler(CallbackQueryHandler(button_handler))
    
    print("🤖 TrustBingo Telegram Bot is polling...")
    application.run_polling()

if __name__ == "__main__":
    main()