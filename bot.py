import os
import time
import sqlite3
import telebot
import requests
from telebot import types
from threading import Thread
from flask import Flask

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL")

bot = telebot.TeleBot(TOKEN)
DB_FILE = "ton_bot_database.db"

def init_local_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            balance REAL DEFAULT 0.0,
            referred_by INTEGER,
            referrals_count INTEGER DEFAULT 0,
            completed_tasks TEXT DEFAULT ''
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            description TEXT NOT NULL
        )
    ''')
    conn.commit()
    conn.close()

def get_user_data(user_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT balance, referred_by, referrals_count, completed_tasks FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    
    if not row:
        cursor.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))
        conn.commit()
        data = {"balance": 0.0, "referred_by": None, "referrals_count": 0, "completed_tasks": []}
    else:
        tasks_list = [int(i) for i in row[3].split(",") if i] if row[3] else []
        data = {
            "balance": row[0],
            "referred_by": row[1],
            "referrals_count": row[2],
            "completed_tasks": tasks_list
        }
    conn.close()
    return data

def update_user_data(user_id, balance, referred_by, referrals_count, completed_tasks):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    tasks_str = ",".join(map(str, completed_tasks))
    cursor.execute('''
        UPDATE users 
        SET balance = ?, referred_by = ?, referrals_count = ?, completed_tasks = ? 
        WHERE user_id = ?
    ''', (balance, referred_by, referrals_count, tasks_str, user_id))
    conn.commit()
    conn.close()

def main_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    btn_tasks = types.KeyboardButton("📋 المهام")
    btn_ref = types.KeyboardButton("👥 نظام الإحالة")
    btn_wallet = types.KeyboardButton("💰 الرصيد والسحب")
    markup.add(btn_tasks, btn_ref)
    markup.add(btn_wallet)
    return markup

def admin_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    btn_add_task = types.KeyboardButton("➕ إضافة مهمة")
    btn_main = types.KeyboardButton("🔙 القائمة الرئيسية")
    markup.add(btn_add_task, btn_main)
    return markup

@bot.message_handler(commands=['start'])
def start_command(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    user_data = get_user_data(user_id)
    
    text_split = message.text.split()
    if len(text_split) > 1 and user_data["referred_by"] is None:
        try:
            referrer_id = int(text_split[1])
            if referrer_id != user_id:
                ref_data = get_user_data(referrer_id)
                ref_data["balance"] += 0.01
                ref_data["referrals_count"] += 1
                update_user_data(referrer_id, ref_data["balance"], ref_data["referred_by"], ref_data["referrals_count"], ref_data["completed_tasks"])
                
                user_data["referred_by"] = referrer_id
                update_user_data(user_id, user_data["balance"], user_data["referred_by"], user_data["referrals_count"], user_data["completed_tasks"])
                
                try:
                    bot.send_message(referrer_id, f"🎉 إحالة ناجحة! تم إضافة **0.01 TON** لرصيدك.", parse_mode="Markdown")
                except Exception:
                    pass
        except ValueError:
            pass

    welcome_text = "👋 أهلاً بك في بوت ربح TON المحدث!\n\nاستخدم الأزرار التقليدية بالأسفل لجمع الأرباح."
    bot.send_message(chat_id, welcome_text, reply_markup=main_keyboard())

@bot.message_handler(content_types=['text'])
def handle_text(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    user_data = get_user_data(user_id)

    if message.text == "🔙 القائمة الرئيسية":
        bot.send_message(chat_id, "تمت العودة للقائمة الرئيسية", reply_markup=main_keyboard())

    elif message.text == "👥 نظام الإحالة":
        bot_username = bot.get_me().username
        ref_link = f"https://t.me{bot_username}?start={user_id}"
        ref_text = f"👥 **نظام الإحالة المدمج:**\n\n💰 ربح كل إحالة: **0.01 TON**\n📊 عدد إحالاتك الحالية: `{user_data['referrals_count']}`\n\n🔗 رابط الإحالة الخاص بك (اضغط عليه للنسخ):\n`{ref_link}`"
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔗 مشاركة رابط الإحالة", url=f"https://t.meshare/url?url={ref_link}&text=اشترك%20في%20البوت%20واجمع%20عملة%20TON%20مجاناً!"))
        bot.send_message(chat_id, ref_text, parse_mode="Markdown", reply_markup=markup)

    elif message.text == "💰 الرصيد والسحب":
        wallet_text = f"💰 **رصيدك الحالي:** `{user_data['balance']:.3f} TON`\n\n📥 اضغط على الزر بالأسفل لطلب سحب أرباحك وتنبيه الأدمن."
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("➡️ طلب سحب الأرباح", callback_data="request_withdraw"))
        bot.send_message(chat_id, wallet_text, parse_mode="Markdown", reply_markup=markup)

    elif message.text == "📋 المهام":
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT id, description FROM tasks")
        all_tasks = cursor.fetchall()
        conn.close()

        available_tasks = [t for t in all_tasks if t[0] not in user_data["completed_tasks"]]
        
        if not available_tasks:
            bot.send_message(chat_id, "❌ لا توجد مهام جديدة متاحة حالياً.")
            return
        
        bot.send_message(chat_id, "📋 **المهام المتاحة حالياً:**")
        for task_id, description in available_tasks:
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("✅ إكمال المهمة وتأكيدها", callback_data=f"complete_task_{task_id}"))
            bot.send_message(chat_id, f"🔹 {description}\n💰 المكافأة: **0.003 TON**", parse_mode="Markdown", reply_markup=markup)

    elif message.text == "/admin" and user_id == ADMIN_ID:
        bot.send_message(chat_id, "🔧 أهلاً بك في لوحة تحكم الأدمن المدمجة.", reply_markup=admin_keyboard())

    elif message.text == "➕ إضافة مهمة" and user_id == ADMIN_ID:
        msg = bot.send_message(chat_id, "أرسل وصف المهمة لحفظها تلقائياً في قاعدة البيانات:")
        bot.register_next_step_handler(msg, save_task)

def save_task(message):
    if message.text:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO tasks (description) VALUES (?)", (message.text,))
        conn.commit()
        conn.close()
        bot.send_message(message.chat.id, "✅ تم حفظ المهمة بنجاح وعرضها للمستخدمين!", reply_markup=admin_keyboard())

@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    user_id = call.from_user.id
    user_data = get_user_data(user_id)

    if call.data == "request_withdraw":
        if user_data["balance"] <= 0:
            bot.answer_callback_query(call.id, "❌ رصيدك الحالي 0 لا يمكن سحبه.", show_alert=True)
        else:
            bot.send_message(call.message.chat.id, f"📩 أرسل عنوان محفظة TON ومبلغ السحب المُراد للأدمن.\nرصيدك المتوفر: {user_data['balance']:.3f} TON")
            bot.answer_callback_query(call.id)

    elif call.data.startswith("complete_task_"):
        task_id = int(call.data.split("_")[2])
        if task_id not in user_data["completed_tasks"]:
            user_data["completed_tasks"].append(task_id)
            user_data["balance"] += 0.003
            update_user_data(user_id, user_data["balance"], user_data["referred_by"], user_data["referrals_count"], user_data["completed_tasks"])
            bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text="🎉 تم بنجاح! تم إضافة **0.003 TON** إلى رصيدك المحلي.")
            bot.answer_callback_query(call.id, "تم تحديث الرصيد!")
        else:
            bot.answer_callback_query(call.id, "لقد قمت بهذه المهمة مسبقاً!", show_alert=True)

flask_app = Flask('')

@flask_app.route('/')
def home():
    return "<h1>Local DB Bot is running!</h1>", 200

def run_flask_server():
    port = int(os.environ.get("PORT", 8080))
    flask_app.run(host='0.0.0.0', port=port)

def keep_alive_ping():
    time.sleep(60)
    while True:
        if RENDER_URL:
            try:
                requests.get(RENDER_URL)
            except Exception:
                pass
        time.sleep(600)

if __name__ == "__main__":
    init_local_db()
    
    flask_thread = Thread(target=run_flask_server)
    flask_thread.daemon = True
    flask_thread.start()
    
    ping_thread = Thread(target=keep_alive_ping)
    ping_thread.daemon = True
    ping_thread.start()
    
    print("Telegram Bot with Local DB is running seamlessly...")
    bot.infinity_polling()
