import os
import re
import json
import html
import base64
import time
import threading
import http.server
import socketserver
import telebot
from telebot import types
from datetime import datetime

# =========================================================
# ⚙️ CONFIG
# =========================================================

BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()  # Render Environment-এ আপনি সেট করবেন
ADMIN_ID = int(os.environ.get("ADMIN_ID", "8246715371"))
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "@TC_BRAND_LEADER")
BOT_USERNAME = os.environ.get("BOT_USERNAME", "@kawsarpredtionbot")

PORT = int(os.environ.get("PORT", "8080"))

# Force Join: নির্দিষ্ট channel-এ join বাধ্যতামূলক
FORCE_SUB_CHAT = os.environ.get("FORCE_SUB_CHAT", "@TC_COMMIUNITY")
FORCE_SUB_URL  = os.environ.get("FORCE_SUB_URL", "https://t.me/TC_COMMIUNITY")

USERS_FILE = "users.json"

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN সেট করা হয়নি!")

# =========================================================
# 🤖 TELEGRAM BOT
# =========================================================

telebot.apihelper.READ_TIMEOUT = 180
telebot.apihelper.CONNECT_TIMEOUT = 60

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML", threaded=True)

# =========================================================
# 🔤 CUSTOM ALPHABET (MAHDE style)
# =========================================================

STD_B64 = (
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "abcdefghijklmnopqrstuvwxyz"
    "0123456789+/"
)

CUSTOM_ALPHABET = [
    "👿", "🔥", "🥵", "💀", "❌", "🔒", "⚡", "🎯",
    "%", "+", "=", "-", "&", "^", "_", "~",
    "k", "d", "j", "i", "h", "o", "b", "f",
    "q", "w", "r", "t", "y", "u", "p", "a",
    "s", "g", "l", "z", "x", "c", "v", "n",
    "m", "3", "9", "8", "4", "7", "2", "5",
    "6", "0", "1", "£", "€", "¥", "₹", "§",
    "π", "θ", "λ", "μ", "Ω", "∞", "≠", "÷"
]

CUSTOM_TO_B64 = {
    CUSTOM_ALPHABET[i]: STD_B64[i]
    for i in range(64)
}
CUSTOM_TO_B64["•"] = "="

# =========================================================
# 👥 USER DATABASE
# =========================================================

def load_users():
    if not os.path.exists(USERS_FILE):
        return {}
    try:
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_users(data):
    try:
        with open(USERS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("User DB Error:", e)

def register_user(user):
    try:
        data = load_users()
        uid = str(user.id)
        if uid not in data:
            data[uid] = {
                "id": user.id,
                "first_name": user.first_name or "",
                "last_name": user.last_name or "",
                "username": user.username or "N/A",
                "joined_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            save_users(data)
    except Exception as e:
        print("Register Error:", e)

def get_user_count():
    return len(load_users())

# =========================================================
# 📢 FORCE JOIN
# =========================================================

def is_subscribed(user_id):
    if not FORCE_SUB_CHAT or FORCE_SUB_CHAT == "@YOUR_CHANNEL":
        return True
    if ADMIN_ID and user_id == ADMIN_ID:
        return True
    try:
        member = bot.get_chat_member(FORCE_SUB_CHAT, user_id)
        return member.status in ["creator", "administrator", "member", "restricted"]
    except Exception as e:
        print("Subscription check:", e)
        return False

def force_join_keyboard():
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(types.InlineKeyboardButton("📢 JOIN CHANNEL", url=FORCE_SUB_URL))
    markup.add(types.InlineKeyboardButton("✅ CHECK & UNLOCK", callback_data="check_join"))
    return markup

def send_lock_message(chat_id):
    bot.send_message(
        chat_id,
        "🔒 <b>ACCESS LOCKED</b>\n\n"
        "Unlock Bot ব্যবহার করার আগে আমাদের official channel-এ join করুন।\n\n"
        "1️⃣ JOIN CHANNEL চাপুন\n"
        "2️⃣ Join করার পরে CHECK & UNLOCK চাপুন\n\n"
        "⚡ তারপর আপনার encrypted HTML file পাঠান।",
        reply_markup=force_join_keyboard()
    )

def access_allowed(message):
    uid = message.from_user.id
    register_user(message.from_user)
    if ADMIN_ID and uid == ADMIN_ID:
        return True
    if not is_subscribed(uid):
        send_lock_message(message.chat.id)
        return False
    return True

# =========================================================
# 🔓 OUTER XOR DECODER
# =========================================================

def decode_outer_layer(encrypted_html):
    data_match = re.search(
        r'const\s+_0xdata\s*=\s*("(?:\\.|[^"\\])*")\s*;',
        encrypted_html,
        re.DOTALL
    )
    seed_match = re.search(
        r'const\s+_0xseed\s*=\s*(\d+)\s*;',
        encrypted_html
    )

    if not data_match:
        raise ValueError("_0xdata পাওয়া যায়নি। এটি MAHDE-style encrypted file নয়।")
    if not seed_match:
        raise ValueError("_0xseed পাওয়া যায়নি।")

    try:
        payload = json.loads(data_match.group(1))
    except Exception:
        raise ValueError("Encrypted payload corrupt।")

    seed = int(seed_match.group(1))

    b64_chars = []
    for symbol in payload:
        if symbol in CUSTOM_TO_B64:
            b64_chars.append(CUSTOM_TO_B64[symbol])
        else:
            b64_chars.append(symbol)

    b64_string = "".join(b64_chars)

    try:
        encrypted_bytes = base64.b64decode(b64_string)
    except Exception as e:
        raise ValueError(f"Base64 decode failed: {e}")

    output = bytearray()
    current_key = seed
    for encrypted_byte in encrypted_bytes:
        output.append(encrypted_byte ^ current_key)
        current_key = (current_key + 31) & 0xFF

    try:
        return output.decode("utf-8")
    except UnicodeDecodeError:
        return output.decode("utf-8", errors="replace")

# =========================================================
# 🎨 REVERSE SCRAMBLED CSS
# =========================================================

def restore_scrambled_css(html_content):
    pattern = re.compile(
        r"<script([^>]*)>"
        r"\s*\(function\(\)\{"
        r".*?"
        r"var\s+_k=(\d+),"
        r"_b=(\[[^\]]*\]),"
        r"_out=new Uint8Array"
        r".*?"
        r"document\.createElement\('style'\)"
        r".*?"
        r"\}\)\(\);"
        r"\s*</script>",
        re.DOTALL | re.IGNORECASE
    )

    def replacement(match):
        attrs = match.group(1)
        key = int(match.group(2))
        byte_list_text = match.group(3)

        try:
            byte_list = json.loads(byte_list_text)
        except Exception:
            return match.group(0)

        decoded = bytearray()
        current_key = key
        for value in byte_list:
            decoded.append(value ^ current_key)
            current_key = (current_key + 17) & 0xFF

        try:
            css = decoded.decode("utf-8")
        except Exception:
            css = decoded.decode("utf-8", errors="replace")

        return "<style>" + css + "</style>"

    return pattern.sub(replacement, html_content)

# =========================================================
# 📜 REVERSE SCRAMBLED JAVASCRIPT
# =========================================================

def restore_scrambled_scripts(html_content):
    pattern = re.compile(
        r"<script([^>]*)>"
        r"\s*\(function\(\)\{"
        r".*?"
        r"var\s+_k=(\d+),"
        r"_b=(\[[^\]]*\]),"
        r"_out=new Uint8Array"
        r".*?"
        r"\(0,eval\)\(_c\);"
        r".*?"
        r"\}\)\(\);"
        r"\s*</script>",
        re.DOTALL | re.IGNORECASE
    )

    def replacement(match):
        attrs = match.group(1)
        key = int(match.group(2))
        byte_list_text = match.group(3)

        try:
            byte_list = json.loads(byte_list_text)
        except Exception:
            return match.group(0)

        decoded = bytearray()
        current_key = key
        for value in byte_list:
            decoded.append(value ^ current_key)
            current_key = (current_key + 19) & 0xFF

        try:
            javascript = decoded.decode("utf-8")
        except Exception:
            javascript = decoded.decode("utf-8", errors="replace")

        return "<script" + attrs + ">" + javascript + "</script>"

    return pattern.sub(replacement, html_content)

# =========================================================
# 🔓 COMPLETE UNLOCK ENGINE
# =========================================================

def unlock_html(encrypted_html):
    decoded = decode_outer_layer(encrypted_html)
    decoded = restore_scrambled_css(decoded)
    decoded = restore_scrambled_scripts(decoded)
    return decoded

# =========================================================
# 🧹 SAFE FILE NAME
# =========================================================

def safe_filename(name):
    name = os.path.basename(name)
    name = re.sub(r"[^a-zA-Z0-9._-]", "_", name)
    return name

# =========================================================
# /START
# =========================================================

@bot.message_handler(commands=["start"])
def start_handler(message):
    register_user(message.from_user)
    if not access_allowed(message):
        return

    bot.send_message(
        message.chat.id,
        "👑 <b>H4X HTML DECODER BOT</b>\n\n"
        "🔓 আপনার encrypted HTML file unlock করার জন্য পাঠান।\n\n"
        "সাপোর্টেড ফরম্যাট:\n"
        "• MAHDE-style Lock Bot\n"
        "• Custom Alphabet + XOR based protection\n\n"
        "📁 এখন encrypted HTML file পাঠান।"
    )

# =========================================================
# /HELP
# =========================================================

@bot.message_handler(commands=["help"])
def help_handler(message):
    if not access_allowed(message):
        return

    bot.send_message(
        message.chat.id,
        "🔓 <b>UNLOCK BOT HELP</b>\n\n"
        "1️⃣ encrypted HTML file পাঠান\n"
        "2️⃣ Bot encryption structure চেক করবে\n"
        "3️⃣ Outer cipher decode করবে\n"
        "4️⃣ CSS/JS scrambling reverse করবে\n"
        "5️⃣ unlocked HTML file পাঠাবে\n\n"
        "⚠️ শুধুমাত্র compatible encryption ফরম্যাট সাপোর্ট করে।"
    )

# =========================================================
# 📁 DOCUMENT HANDLER
# =========================================================

@bot.message_handler(content_types=["document"])
def document_handler(message):
    if not access_allowed(message):
        return

    document = message.document
    original_name = document.file_name or "encrypted.html"
    lower_name = original_name.lower()

    if not lower_name.endswith((".html", ".htm")):
        bot.reply_to(
            message,
            "❌ <b>Invalid File</b>\n\n"
            "শুধু <code>.html</code> অথবা <code>.htm</code> file পাঠান।"
        )
        return

    processing = bot.reply_to(
        message,
        "⏳ <b>UNLOCK PROCESSING...</b>\n\n"
        "🔐 Reading encrypted payload...\n"
        "🔄 Reversing custom cipher...\n"
        "🎨 Restoring CSS...\n"
        "📜 Restoring JavaScript...\n\n"
        "⚡ একটু অপেক্ষা করুন..."
    )

    input_path = None
    output_path = None

    try:
        file_info = bot.get_file(document.file_id)
        file_bytes = bot.download_file(file_info.file_path)

        safe_name = safe_filename(original_name)
        input_path = "locked_" + safe_name

        with open(input_path, "wb") as f:
            f.write(file_bytes)

        encrypted_html = file_bytes.decode("utf-8", errors="replace")

        if "_0xdata" not in encrypted_html or "_0xseed" not in encrypted_html:
            raise ValueError(
                "এই ফাইলটি MAHDE-style Lock Bot-এর compatible encrypted HTML নয়।"
            )

        unlocked_html = unlock_html(encrypted_html)

        if not unlocked_html.strip():
            raise ValueError("Decoded HTML empty।")

        base_name = os.path.splitext(safe_name)[0]
        output_name = "H4X_Unlocked_" + base_name + ".html"
        output_path = output_name

        with open(output_path, "w", encoding="utf-8", errors="surrogatepass", newline="") as f:
            f.write(unlocked_html)

        with open(output_path, "rb") as f:
            bot.send_document(
                message.chat.id,
                f,
                caption=(
                    "👑 ━━━━━━━━━━━━━━━━━━━ 👑\n"
                    "🔓 <b>H4X UNLOCK SUCCESS</b>\n"
                    "👑 ━━━━━━━━━━━━━━━━━━━ 👑\n\n"
                    f"📁 <b>Original:</b> <code>{html.escape(original_name)}</code>\n"
                    f"📄 <b>Unlocked:</b> <code>{html.escape(output_name)}</code>\n\n"
                    "✅ Outer cipher decoded\n"
                    "✅ Custom alphabet restored\n"
                    "✅ XOR layer reversed\n"
                    "✅ CSS restored\n"
                    "✅ JavaScript restored\n\n"
                    f"🤖 <b>Bot:</b> {html.escape(BOT_USERNAME)}"
                )
            )

        # Admin notification
        if ADMIN_ID:
            try:
                user = message.from_user
                admin_text = (
                    "🔓 <b>NEW UNLOCK REQUEST</b>\n\n"
                    f"👤 Name: {html.escape(user.first_name or '')}\n"
                    f"🆔 ID: <code>{user.id}</code>\n"
                    f"🔗 Username: @{html.escape(user.username or 'N/A')}\n"
                    f"📁 File: <code>{html.escape(original_name)}</code>\n"
                    f"⏰ Time: <code>{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</code>"
                )
                bot.send_message(ADMIN_ID, admin_text)
            except Exception as e:
                print("Admin notification error:", e)

        try:
            bot.delete_message(message.chat.id, processing.message_id)
        except Exception:
            pass

    except Exception as e:
        try:
            bot.edit_message_text(
                "❌ <b>UNLOCK FAILED</b>\n\n"
                f"⚠️ কারণ:\n<code>{html.escape(str(e)[:1000])}</code>\n\n"
                "সম্ভবত fileটি এই format-এর নয় অথবা fileটি corrupt।",
                message.chat.id,
                processing.message_id
            )
        except Exception:
            bot.send_message(
                message.chat.id,
                f"❌ <b>Unlock failed:</b>\n<code>{html.escape(str(e))}</code>"
            )

    finally:
        for path in [input_path, output_path]:
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except Exception:
                    pass

# =========================================================
# 🔘 CHECK JOIN
# =========================================================

@bot.callback_query_handler(func=lambda call: call.data == "check_join")
def check_join(call):
    register_user(call.from_user)

    if is_subscribed(call.from_user.id):
        bot.answer_callback_query(call.id, "✅ Verified! Unlock Bot is ready.", show_alert=False)
        try:
            bot.edit_message_text(
                "🔓 <b>ACCESS UNLOCKED</b>\n\nএখন আপনার encrypted HTML file পাঠান।",
                call.message.chat.id,
                call.message.message_id
            )
        except Exception:
            pass
    else:
        bot.answer_callback_query(call.id, "❌ আগে channel-এ join করুন।", show_alert=True)

# =========================================================
# 👑 ADMIN PANEL
# =========================================================

@bot.message_handler(commands=["admin"])
def admin_handler(message):
    if not ADMIN_ID:
        return
    if message.from_user.id != ADMIN_ID:
        bot.reply_to(message, "⛔ Admin only.")
        return

    users = get_user_count()
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("📊 USER COUNT", callback_data="admin_stats"))

    bot.send_message(
        message.chat.id,
        "👑 <b>H4X DECODER ADMIN PANEL</b>\n\n"
        f"👥 Total Users: <code>{users}</code>\n"
        "🟢 Bot Status: Online",
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data == "admin_stats")
def admin_stats(call):
    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "⛔ Access denied.", show_alert=True)
        return
    bot.answer_callback_query(call.id, f"Users: {get_user_count()}", show_alert=True)

# =========================================================
# 🌐 KEEP ALIVE SERVER
# =========================================================

class ReusableTCPServer(socketserver.TCPServer):
    allow_reuse_address = True

def run_server():
    class Handler(http.server.SimpleHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            page = """
            <!DOCTYPE html>
            <html>
            <head><title>H4X Decoder Bot</title></head>
            <body style="background:#0b0e14;color:#58a6ff;text-align:center;font-family:Arial;padding-top:80px;">
            <h1>🔓 H4X HTML DECODER BOT</h1>
            <p style="color:#3fb950">🟢 Bot Online</p>
            </body>
            </html>
            """
            self.wfile.write(page.encode())

        def log_message(self, format, *args):
            pass

    while True:
        try:
            with ReusableTCPServer(("", PORT), Handler) as server:
                print(f"🌐 Keep Alive running on {PORT}")
                server.serve_forever()
        except Exception as e:
            print("Server error:", e)
            time.sleep(5)

# =========================================================
# 🚀 START BOT
# =========================================================

if __name__ == "__main__":
    print("🔓 H4X HTML DECODER BOT STARTING...")

    threading.Thread(target=run_server, daemon=True).start()

    while True:
        try:
            bot.remove_webhook()
            time.sleep(1)
            print("🚀 Telegram polling started...")
            bot.infinity_polling(
                timeout=30,
                long_polling_timeout=30,
                skip_pending=True
            )
        except Exception as e:
            print("⚠️ Bot Error:", e)
            time.sleep(3)