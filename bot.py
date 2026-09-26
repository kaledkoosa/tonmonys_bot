import os
import time
import sqlite3
import random
import telebot
import requests
from telebot import types
from threading import Thread
from flask import Flask

# 1. إعدادات البيئة الأساسية
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL")

# إعدادات القنوات (استبدلها بالمعرفات الخاصة بك أو ضعها في متغيرات البيئة)
REQUIRED_CHANNEL = "@T_ONo"   # يوزر قناة الاشتراك الإجباري للبوت
PAYMENT_CHANNEL = "@T_ONo"   # يوزر قناة إثباتات السحب التلقائية

bot = telebot.TeleBot(TOKEN)
DB_FILE = "ton_bot_pro.db"

# الكابتشا والمستخدمين قيد التحقق في الذاكرة المؤقتة
captcha_data = {}

# دالة إنشاء قاعدة البيانات والميزات المتقدمة
def init_pro_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    # جدول المستخدمين المطور
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            balance REAL DEFAULT 0.0,
            referred_by INTEGER,
            referrals_count INTEGER DEFAULT 0,
            completed_tasks TEXT DEFAULT '',
            is_verified INTEGER DEFAULT 0
        )
    ''')
    # جدول المهام (سواء وضعها الأدمن أو المستخدمون)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            creator_id INTEGER,
            channel_username TEXT NOT NULL,
            description TEXT NOT NULL,
            reward REAL DEFAULT 0.003,
            budget REAL DEFAULT 0.0
        )
    ''')
    conn.commit()
    conn.close()

def get_user_data(user_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT balance, referred_by, referrals_count, completed_tasks, is_verified FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if not row:
        cursor.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))
        conn.commit()
        data = {"balance": 0.0, "referred_by": None, "referrals_count": 0, "completed_tasks": [], "is_verified": 0}
    else:
        tasks_list = [int(i) for i in row[3].split(",") if i] if row[3] else []
        data = {"balance": row[0], "referred_by": row[1], "referrals_count": row[2], "completed_tasks": tasks_list, "is_verified": row[4]}
    conn.close()
    return data

def update_user_data(user_id, balance, referred_by, referrals_count, completed_tasks, is_verified=1):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    tasks_str = ",".join(map(str, completed_tasks))
    cursor.execute('''
        UPDATE users 
        SET balance = ?, referred_by = ?, referrals_count = ?, completed_tasks = ?, is_verified = ? 
        WHERE user_id = ?
    ''', (balance, referred_by, referrals_count, tasks_str, is_verified, user_id))
    conn.commit()
    conn.close()

# دالة التحقق من الاشتراك الإجباري في القناة
def check_subscription(user_id):
    try:
        member = bot.get_chat_member(REQUIRED_CHANNEL, user_id)
        if member.status in ['member', 'administrator', 'creator']:
            return True
    except Exception:
        pass
    return False

# تصميم لوحات المفاتيح التقليدية
def main_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton("📋 المهام المتاحة"), types.KeyboardButton("➕ وضع مهمة خاصة"))
    markup.add(types.KeyboardButton("👥 نظام الإحالة"), types.KeyboardButton("💰 الرصيد والسحب"))
    return markup

def admin_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton("➕ إضافة مهمة كأدمن"), types.KeyboardButton("🔙 القائمة الرئيسية"))
    return markup

# أمر التشغيل الأولي ونظام الإحالة والكابتشا
@bot.message_handler(commands=['start'])
def start_command(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    user_data = get_user_data(user_id)
    
    # 1. فحص الاشتراك الإجباري أولاً
    if not check_subscription(user_id):
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("📢 اشترك في القناة هنا", url=f"https://t.me{REQUIRED_CHANNEL.replace('@','') Hospice'}"))
        markup.add(types.InlineKeyboardButton("🔄 تم الاشتراك (تأكيد)", callback_data="check_sub_again"))
        bot.send_message(chat_id, f"❌ عذراً! يجب عليك الاشتراك في قناة البوت الرسمية أولاً لتتمكن من استخدامه:\n{REQUIRED_CHANNEL}", reply_markup=markup)
        return

    # 2. فحص نظام الكابتشا ومنع البوتات الوهمية
    if user_data["is_verified"] == 0:
        num1, num2 = random.randint(1, 9), random.randint(1, 9)
        correct_ans = num1 + num2
        captcha_data[user_id] = {"ans": correct_ans, "msg": message.text}
        
        markup = types.InlineKeyboardMarkup()
        options = list(set([correct_ans, correct_ans+2, correct_ans-1, random.randint(2, 18)]))
        random.shuffle(options)
        
        row_btns = [types.InlineKeyboardButton(str(opt), callback_data=f"captcha_{opt}") for opt in options]
        markup.add(*row_btns)
        bot.send_message(chat_id, f"🤖 اختبار الأمان لحمايتنا من الحسابات الوهمية:\n\nكم ناتج عملية: **{num1} + {num2} = ؟**", parse_mode="Markdown", reply_markup=markup)
        return

    # توثيق الإحالة بعد اجتياز الأمان والاشتراك
    text_split = message.text.split()
    if len(text_split) > 1 and user_data["referred_by"] is None:
        try:
            referrer_id = int(text_split[1])
            if referrer_id != user_id:
                ref_data = get_user_data(referrer_id)
                ref_data["balance"] += 0.01
                ref_data["referrals_count"] += 1
                update_user_data(referrer_id, ref_data["balance"], ref_data["referred_by"], ref_data["referrals_count"], ref_data["completed_tasks"], ref_data["is_verified"])
                
                user_data["referred_by"] = referrer_id
                update_user_data(user_id, user_data["balance"], user_data["referred_by"], user_data["referrals_count"], user_data["completed_tasks"], 1)
                
                try:
                    bot.send_message(referrer_id, f"🎉 إحالة حقيقية ناجحة! تم إضافة **0.01 TON** لرصيدك.", parse_mode="Markdown")
                except Exception:
                    pass
        except ValueError:
            pass

    bot.send_message(chat_id, "👋 أهلاً بك في النسخة الاحترافية لبوت TON!\nجميع المهام تُفحص تلقائياً ويمكنك الآن الإعلان عن قناتك.", reply_markup=main_keyboard())

# معالجة الضغط على الأزرار والنوافذ التفاعلية
@bot.message_handler(content_types=['text'])
def handle_text(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    user_data = get_user_data(user_id)

    if not check_subscription(user_id) or user_data["is_verified"] == 0:
        bot.send_message(chat_id, "⚠️ يرجى إكمال متطلبات التحقق أو الاشتراك عبر إرسال /start أولاً.")
        return

    if message.text == "🔙 القائمة الرئيسية":
        bot.send_message(chat_id, "تمت العودة للقائمة الرئيسية", reply_markup=main_keyboard())

    elif message.text == "👥 نظام الإحالة":
        bot_username = bot.get_me().username
        ref_link_direct = f"tg://resolve?domain={bot_username}&start={user_id}"
        ref_text = f"👥 **نظام الإحالة التلقائي والآمن:**\n\n💰 مكافأة الإحالة الموثوقة: **0.01 TON**\n📊 عدد إحالاتك الحقيقية: `{user_data['referrals_count']}`\n\n🔗 رابط دعوة الأصدقاء المباشر:\n`{ref_link_direct}`"
        
        share_url = f"tg://msg_url?url={ref_link_direct}&text=ادخل%20واجمع%20عملة%20TON%20مجاناً%20مع%20إثباتات%20سحب!"
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔗 مشاركة فورية داخل تليجرام", url=share_url))
        bot.send_message(chat_id, ref_text, parse_mode="Markdown", reply_markup=markup)

    elif message.text == "💰 الرصيد والسحب":
        wallet_text = f"💰 **محفظتك الرقمية داخل البوت:**\n\n📊 الرصيد المتوفر: `{user_data['balance']:.3f} TON`"
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("📥 طلب سحب فوري", callback_data="payout_request"))
        bot.send_message(chat_id, wallet_text, parse_mode="Markdown", reply_markup=markup)

    elif message.text == "📋 المهام المتاحة":
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT id, channel_username, description, reward FROM tasks WHERE budget >= reward")
        all_tasks = cursor.fetchall()
        conn.close()

        available_tasks = [t for t in all_tasks if t[0] not in user_data["completed_tasks"]]
        if not available_tasks:
            bot.send_message(chat_id, "❌ لا توجد مهام مدفوعة متاحة حالياً.")
            return

        bot.send_message(chat_id, "📋 **المهام المتوفرة (فحص تلقائي فوري):**")
        for t_id, ch_user, desc, reward in available_tasks:
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("📢 فتح القناة للانضمام", url=f"https://t.me{ch_user.replace('@','') }"))
            markup.add(types.InlineKeyboardButton("🤖 تحقق وتأكيد تلقائي", callback_data=f"verify_task_{t_id}"))
            bot.send_message(chat_id, f"🔹 **المهمة:** {desc}\n💰 الجائزة: **{reward} TON**", parse_mode="Markdown", reply_markup=markup)

    # ميزة المستخدمين: وضع مهمة خاصة لترويج قنواتهم
    elif message.text == "➕ وضع مهمة خاصة":
        msg = bot.send_message(chat_id, "⚙️ **قسم إعلانات الأعضاء:**\n\nأرسل يوزر قناتك التي تريد ترويجها مع علامة @ (مثال: @my_channel):\n*ملاحظة: تكلفة كل مشترك هي 0.003 TON يتم خصمها من رصيدك الحالي.*", parse_mode="Markdown")
        bot.register_next_step_handler(msg, user_add_task_step1)

    # لوحة تحكم الإدارة للأدمن
    elif message.text == "/admin" and user_id == ADMIN_ID:
        bot.send_message(chat_id, "🔧 أهلاً بك في لوحة تحكم الإدارة العليا.", reply_markup=admin_keyboard())

    elif message.text == "➕ إضافة مهمة كأدمن" and user_id == ADMIN_ID:
        msg = bot.send_message(chat_id, "أرسل يوزر القناة المستهدفة للمهمة الإدارية (مثال: @admin_channel):")
