import os
import time
import telebot
import requests
import psycopg2  # مكتبة الاتصال بقاعدة بيانات PostgreSQL (Supabase)
from telebot import types
from threading import Thread
from flask import Flask

# 1. إعدادات البوت وقاعدة البيانات
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL")
DATABASE_URL = os.getenv("DATABASE_URL")  # رابط الاتصال من Supabase

bot = telebot.TeleBot(TOKEN)

# دالة للاتصال بقاعدة البيانات وإنشاء الجداول لو لم تكن موجودة
def init_db():
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    # جدول المستخدمين والأرصدة والإحالات
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY,
            balance TEXT DEFAULT '0.0',
            referred_by BIGINT,
            referrals_count INTEGER DEFAULT 0,
            completed_tasks TEXT DEFAULT ''
        )
    ''')
    # جدول المهام التي يضيفها الأدمن
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tasks (
            id SERIAL PRIMARY KEY,
            description TEXT NOT NULL
        )
    ''')
    conn.commit()
    cursor.close()
    conn.close()

# دالة لجلب أو إنشاء بيانات مستخدم من قاعدة البيانات
def get_user_data(user_id):
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    cursor.execute("SELECT balance, referred_by, referrals_count, completed_tasks FROM users WHERE user_id = %s", (user_id,))
    row = cursor.fetchone()
    
    if not row:
        cursor.execute("INSERT INTO users (user_id) VALUES (%s)", (user_id,))
        conn.commit()
        data = {"balance": 0.0, "referred_by": None, "referrals_count": 0, "completed_tasks": []}
    else:
        tasks_list = [int(i) for i in row[3].split(",") if i] if row[3] else []
        data = {
            "balance": float(row[0]),
            "referred_by": row[1],
            "referrals_count": row[2],
            "completed_tasks": tasks_list
        }
    cursor.close()
    conn.close()
    return data

# دالة لتحديث بيانات المستخدم في قاعدة البيانات
def update_user_data(user_id, balance, referred_by, referrals_count, completed_tasks):
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    tasks_str = ",".join(map(str, completed_tasks))
    cursor.execute('''
        UPDATE users 
        SET balance = %s, referred_by = %s, referrals_count = %s, completed_tasks = %s 
        WHERE user_id = %s
    ''', (str(balance), referred_by, referrals_count, tasks_str, user_id))
    conn.commit()
    cursor.close()
    conn.close()

# 2. تصميم الأزرار التقليدية الرئيسية (Reply Keyboard)
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

# 3. معالجة أمر البدء /start ونظام الإحالة
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
                # التحقق من وجود حساب للمُحيل وجلب بياناته لتعديلها
                ref_data = get_user_data(referrer_id)
                ref_data["balance"] += 0.01
                ref_data["referrals_count"] += 1
                update_user_data(referrer_id, ref_data["balance"], ref_data["referred_by"], ref_data["referrals_count"], ref_data["completed_tasks"])
                
                user_data["referred_by"] = referrer_id
                update_user_data(user_id, user_data["balance"], user_data["referred_by"], user_data["referrals_count"], user_data["completed_tasks"])
                
                try:
                    bot.send_message(referrer_id, f"🎉 لديك إحالة جديدة! تم إضافة **0.01 TON** إلى رصيدك.", parse_mode="Markdown")
                except Exception:
                    pass
        except ValueError:
            pass

    welcome_text = "👋 أهلاً بك في بوت ربح TON مع حفظ البيانات التلقائي!\n\nاستخدم الأزرار التقليدية لتصفح البوت."
    bot.send_message(chat_id, welcome_text, reply_markup=main_keyboard())

# 4. معالجة الأزرار التقليدية
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
        ref_text = (
            f"👥 **نظام الإحالة الخاص بك:**\n\n"
            f"💰 ربح كل إحالة: **0.01 TON**\n"
            f"📊 عدد إحالاتك: `{user_data['referrals_count']}`\n\n"
            f"🔗 رابط الإحالة الخاص بك:\n`{ref_link}`"
        )
        bot.send_message(chat_id, ref_text, parse_mode="Markdown")

    elif message.text == "💰 الرصيد والسحب":
        wallet_text = (
            f"💰 **رصيدك الحالي المخزن:** `{user_data['balance']:.3f} TON`\n\n"
            f"📥 للسحب الفوري اضغط على الزر أدناه لإبلاغ الأدمن."
        )
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("➡️ طلب سحب الأرباح", callback_data="request_withdraw"))
        bot.send_message(chat_id, wallet_text, parse_mode="Markdown", reply_markup=markup)

    elif message.text == "📋 المهام":
        # جلب المهام من قاعدة البيانات السحابية
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        cursor.execute("SELECT id, description FROM tasks")
        all_tasks = cursor.fetchall()
        cursor.close()
        conn.close()

        available_tasks = [t for t in all_tasks if t[0] not in user_data["completed_tasks"]]
        
        if not available_tasks:
            bot.send_message(chat_id, "❌ لا توجد مهام جديدة حالياً.")
            return
        
        bot.send_message(chat_id, "📋 **المهام المتاحة حالياً:**")
        for task_id, description in available_tasks:
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("✅ إكمال المهمة", callback_data=f"complete_task_{task_id}"))
            bot.send_message(chat_id, f"🔹 {description}\n💰 المكافأة: **0.003 TON**", parse_mode="Markdown", reply_markup=markup)

    elif message.text == "/admin" and user_id == ADMIN_ID:
        bot.send_message(chat_id, "🔧 لوحة تحكم الأدمن وقاعدة البيانات.", reply_markup=admin_keyboard())

    elif message.text == "➕ إضافة مهمة" and user_id == ADMIN_ID:
        msg = bot.send_message(chat_id, "أرسل وصف المهمة لحفظها في السيرفر:")
        bot.register_next_step_handler(msg, save_task)

def save_task(message):
    if message.text:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO tasks (description) VALUES (%s)", (message.text,))
        conn.commit()
        cursor.close()
        conn.close()
        bot.send_message(message.chat.id, "✅ تم حفظ المهمة بنجاح داخل قاعدة البيانات السحابية!", reply_markup=admin_keyboard())

# 5. معالجة عمليات الضغط والتأكيد
@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    user_id = call.from_user.id
    user_data = get_user_data(user_id)

    if call.data == "request_withdraw":
        if user_data["balance"] <= 0:
            bot.answer_callback_query(call.id, "❌ رصيدك الحالي 0.", show_alert=True)
        else:
            bot.send_message(call.message.chat.id, f"📩 أرسل عنوان محفظتك ومبلغ السحب للأدمن الحالي.\nرصيدك: {user_data['balance']:.3f} TON")
            bot.answer_callback_query(call.id)

    elif call.data.startswith("complete_task_"):
        task_id = int(call.data.split("_")[2])
        if task_id not in user_data["completed_tasks"]:
            user_data["completed_tasks"].append(task_id)
            user_data["balance"] += 0.003
            update_user_data(user_id, user_data["balance"], user_data["referred_by"], user_data["referrals_count"], user_data["completed_tasks"])
            bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text="🎉 تم الحفظ! تم إضافة **0.003 TON**")
            bot.answer_callback_query(call.id, "تم تحديث رصيدك بنجاح!")
        else:
            bot.answer_callback_query(call.id, "قمت بهذه المهمة مسبقاً!", show_alert=True)

# خادم الويب وKeep-Alive الوهمي
flask_app = Flask('')

@flask_app.route('/')
def home():
    return "<h1>Database Bot is Active!</h1>", 200

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
    # إنشاء وتأكيد الجداول قبل تشغيل البوت
    init_db()
    
    flask_thread = Thread(target=run_flask_server)
    flask_thread.daemon = True
    flask_thread.start()
    
    ping_thread = Thread(target=keep_alive_ping)
    ping_thread.daemon = True
    ping_thread.start()
    
    print("Telegram Bot with Database is running...")
    bot.infinity_polling()
