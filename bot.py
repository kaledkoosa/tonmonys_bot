import os
import time
import telebot
import requests
from telebot import types
from threading import Thread
from flask import Flask

# 1. إعدادات البوت والبيانات الأساسية
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))  # آيدي الأدمن الخاص بك
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL") # سيتم جلبه تلقائياً من ريندر لمنع النوم

bot = telebot.TeleBot(TOKEN)

# قواعد بيانات مؤقتة في الذاكرة (تتصفّر عند إعادة تشغيل السيرفر)
users_db = {} 
tasks_db = []  # قائمة المهام المتاحة

def get_user_data(user_id):
    if user_id not in users_db:
        users_db[user_id] = {
            "balance": 0.0,
            "referred_by": None,
            "referrals_count": 0,
            "completed_tasks": []
        }
    return users_db[user_id]

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
    
    # التحقق من وجود رابط إحالة
    text_split = message.text.split()
    if len(text_split) > 1 and user_data["referred_by"] is None:
        referrer_id_str = text_split[1]
        try:
            referrer_id = int(referrer_id_str)
            if referrer_id != user_id:
                # تفعيل نظام الإحالة (0.01 تون للمُحيل)
                user_data["referred_by"] = referrer_id
                ref_data = get_user_data(referrer_id)
                ref_data["balance"] += 0.01
                ref_data["referrals_count"] += 1
                
                # إشعار الشخص الذي قام بالدعوة
                try:
                    bot.send_message(referrer_id, f"🎉 لديك إحالة جديدة! تم إضافة **0.01 TON** إلى رصيدك.", parse_mode="Markdown")
                except Exception:
                    pass
        except ValueError:
            pass

    welcome_text = "👋 أهلاً بك في بوت ربح TON الرسمي!\n\nاستخدم الأزرار التقليدية أدناه لتنفيذ المهام أو دعوة الأصدقاء وجمع الأرباح."
    bot.send_message(chat_id, welcome_text, reply_markup=main_keyboard())

# 4. معالجة الأزرار التقليدية ولوحة التحكم
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
            f"🔗 رابط الإحالة الخاص بك (انسخه وانشره):\n`{ref_link}`"
        )
        bot.send_message(chat_id, ref_text, parse_mode="Markdown")

    elif message.text == "💰 الرصيد والسحب":
        wallet_text = (
            f"💰 **رصيدك الحالي:** `{user_data['balance']:.3f} TON`\n\n"
            f"📥 عند الضغط على الزر بالأسفل، سيُطلب منك إرسال تفاصيل السحب للأدمن."
        )
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("➡️ طلب سحب الأرباح", callback_data="request_withdraw"))
        bot.send_message(chat_id, wallet_text, parse_mode="Markdown", reply_markup=markup)

    elif message.text == "📋 المهام":
        # تصفية المهام التي لم يقم المستخدم بإنجازها بعد
        available_tasks = [idx for idx, _ in enumerate(tasks_db) if idx not in user_data["completed_tasks"]]
        
        if not available_tasks:
            bot.send_message(chat_id, "❌ لا توجد مهام جديدة متاحة حالياً. تفقد البوت لاحقاً!")
            return
        
        bot.send_message(chat_id, "📋 **المهام المتاحة حالياً:**")
        for idx in available_tasks:
            task = tasks_db[idx]
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("✅ إكمال المهمة وتأكيدها", callback_data=f"complete_task_{idx}"))
            bot.send_message(chat_id, f"🔹 {task['description']}\n💰 المكافأة: **0.003 TON**", parse_mode="Markdown", reply_markup=markup)

    # أوامر الأدمن المحمية
    elif message.text == "/admin" and user_id == ADMIN_ID:
        bot.send_message(chat_id, "🔧 أهلاً بك في لوحة تحكم الأدمن التقليدية.", reply_markup=admin_keyboard())

    elif message.text == "➕ إضافة مهمة" and user_id == ADMIN_ID:
        msg = bot.send_message(chat_id, "أرسل وصف المهمة الجديدة الآن (مثال: اشترك في قناة @my_channel وصوّر الشاشة للتحقق):")
        bot.register_next_step_handler(msg, save_task)

def save_task(message):
    if message.text:
        tasks_db.append({"description": message.text})
        bot.send_message(message.chat.id, "✅ تم إضافة المهمة بنجاح بقيمة **0.003 TON** لكافة المستخدمين!", reply_markup=admin_keyboard())

# 5. معالجة العمليات الخلفية (أزرار السحب والتأكيد المضمنة)
@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    user_id = call.from_user.id
    user_data = get_user_data(user_id)

    if call.data == "request_withdraw":
        if user_data["balance"] <= 0:
            bot.answer_callback_query(call.id, "❌ رصيدك الحالي 0، لا يوجد ما تسحبه.", show_alert=True)
        else:
            bot.send_message(call.message.chat.id, f"📩 يرجى إرسال رسالة نصية تحتوي على:\n1. عنوان محفظة TON الخاصة بك.\n2. المبلغ المطلوب سحبه (رصيدك الحالي: {user_data['balance']:.3f} TON).\n\nالأدمن سيقوم بمراجعة طلبك وإرسال العملات يدويًا.")
            bot.answer_callback_query(call.id)

    elif call.data.startswith("complete_task_"):
        task_idx = int(call.data.split("_")[2])
        if task_idx not in user_data["completed_tasks"]:
            # إضافة المكافأة (0.003 تون للمهمة)
            user_data["completed_tasks"].append(task_idx)
            user_data["balance"] += 0.003
            bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text="🎉 تم التحقق وإكمال المهمة بنجاح!\n💰 تم إضافة **0.003 TON** إلى محفظتك داخل البوت.")
            bot.answer_callback_query(call.id, "تمت إضافة المكافأة!")
        else:
            bot.answer_callback_query(call.id, "لقد قمت بهذه المهمة مسبقاً!", show_alert=True)

# 6. إعداد سيرفر الويب الوهمي لتجاوز قيود الخطة المجانية في Render
flask_app = Flask('')

@flask_app.route('/')
def home():
    return "<h1>Bot is Online and Active!</h1>", 200

def run_flask_server():
    port = int(os.environ.get("PORT", 8080))
    flask_app.run(host='0.0.0.0', port=port)

# 7. آلية بث النبضات الذاتية (Ping) لمنع استضافة Render المجانية من النوم
def keep_alive_ping():
    # ننتظر دقيقة حتى يقلع السيرفر لأول مرة
    time.sleep(60)
    while True:
        if RENDER_URL:
            try:
                # إرسال طلب إلى رابط السيرفر لإبقائه نشطاً
                requests.get(RENDER_URL)
                print("Ping sent successfully, keeping the bot awake!")
            except Exception as e:
                print(f"Ping failed: {e}")
        # تكرار العملية كل 10 دقائق (Render ينام بعد 15 دقيقة خمول)
        time.sleep(600)

# التشغيل المتوازي
if __name__ == "__main__":
    # تشغيل سيرفر الويب في خلفية منفصلة
    flask_thread = Thread(target=run_flask_server)
    flask_thread.daemon = True
    flask_thread.start()
    
    # تشغيل ميزة منع النوم في خلفية منفصلة
    ping_thread = Thread(target=keep_alive_ping)
    ping_thread.daemon = True
    ping_thread.start()
    
    # تشغيل البوت الأساسي ليتلقى الرسائل بلا توقف
    print("Telegram Bot is running smoothly...")
    bot.infinity_polling()
