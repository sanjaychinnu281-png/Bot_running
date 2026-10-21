import os
import sys
import time
import zipfile
import subprocess
import logging
import json
import re
import psutil
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# Enable Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- CONFIGURATION ---
BOT_TOKEN = os.getenv("BOT_TOKEN", "8919091291:AAFC70_c3n5WogOwa7nULDEYVd8UEpy96iM")
ADMIN_ID = int(os.getenv("ADMIN_ID", "8095880938"))
ADMIN_USERNAME = "@sbg_mod"

HOSTING_DIR = os.path.abspath("./user_bots")
DATA_FILE = os.path.abspath("approved_bots.json")

os.makedirs(HOSTING_DIR, exist_ok=True)

running_bots = {}

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {"approved": [], "pending": {}}

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)

db_data = load_data()


def get_main_keyboard(user_id: int):
    keyboard = [
        [
            InlineKeyboardButton("📁 Your Files", callback_data="btn_my_files"),
            InlineKeyboardButton("📤 Upload Guide", callback_data="btn_upload_guide"),
        ],
        [
            InlineKeyboardButton("🏓 Ping", callback_data="btn_ping"),
            InlineKeyboardButton("📊 System Info", callback_data="btn_sysinfo"),
        ],
        [
            InlineKeyboardButton("👨‍💻 Admin Contact", url=f"https://t.me/{ADMIN_USERNAME.replace('@', '')}"),
            InlineKeyboardButton("❓ Help", callback_data="btn_help"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


# --- ADVANCED SMART AUTO-INSTALLER ---
def auto_install_requirements(file_path):
    """Scan .py file for any imports and auto-install missing packages via pip"""
    if not file_path.endswith('.py'):
        return
    
    # Mapping of import names to pip package names
    import_to_package = {
        "bs4": "beautifulsoup4",
        "telegram": "python-telegram-bot",
        "cv2": "opencv-python",
        "PIL": "Pillow",
        "mongoengine": "mongoengine",
        "motor": "motor",
        "pymongo": "pymongo",
        "dotenv": "python-dotenv",
        "gtts": "gtts",
        "yt_dlp": "yt-dlp",
        "google.generativeai": "google-generativeai",
        "apscheduler": "apscheduler",
        "yaml": "pyyaml",
        "cryptography": "cryptography",
        "speedtest": "speedtest-cli"
    }

    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
            
        # Extract all import statements
        imports = re.findall(r'^\s*(?:import|from)\s+([a-zA-Z0-9_]+)', content, re.MULTILINE)
        
        standard_libs = sys.builtin_module_names + (
            "os", "sys", "time", "json", "re", "math", "random", "datetime", 
            "subprocess", "logging", "asyncio", "pathlib", "shutil", "sqlite3",
            "urllib", "http", "socket", "threading", "multiprocessing", "collections",
            "io", "string", "abc", "typing", "functools", "itertools"
        )

        for imp in set(imports):
            if imp in standard_libs:
                continue
            pkg = import_to_package.get(imp, imp)
            try:
                __import__(pkg.replace("-", "_"))
            except ImportError:
                logger.info(f"Auto-installing missing dependency: {pkg}")
                subprocess.run([sys.executable, "-m", "pip", "install", pkg], check=False)
    except Exception as e:
        logger.error(f"Error in auto-installer: {e}")


# --- HANDLERS ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    msg = (
        f"👋 Welcome **{user.first_name}** to **CHINNU HOSTING BOT**!\n\n"
        "📤 **Koi bhi `.py` file ya `.zip` upload karein.**\n"
        "⚡ *Universal Auto-Installer Active hai - koi bhi bot error nahi dega!*\n\n"
        "👇 Niche diye gaye buttons ka use karein:"
    )
    if update.message:
        await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=get_main_keyboard(user.id))
    elif update.callback_query:
        await update.callback_query.message.edit_text(msg, parse_mode="Markdown", reply_markup=get_main_keyboard(user.id))


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    doc = update.message.document
    file_name = doc.file_name

    if not (file_name.endswith('.py') or file_name.endswith('.zip')):
        await update.message.reply_text("❌ Kripya sirf `.py` ya `.zip` file hi upload karein.")
        return

    user_file_prefix = f"{user.id}_{file_name}"
    save_path = os.path.join(HOSTING_DIR, user_file_prefix)

    file = await context.bot.get_file(doc.file_id)
    await file.download_to_drive(save_path)

    db_data["pending"][user_file_prefix] = {
        "user_id": user.id,
        "first_name": user.first_name,
        "file_name": file_name,
        "full_path": save_path
    }
    save_data(db_data)

    await update.message.reply_text(
        f"📥 **File Uploaded:** `{file_name}`\n"
        "⏳ **Status:** Admin Approval ka intezaar hai.",
        parse_mode="Markdown"
    )

    admin_keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Approve", callback_data=f"approve_{user_file_prefix}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"reject_{user_file_prefix}")
        ]
    ])

    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=(
            f"🔔 **New Host Request!**\n\n"
            f"👤 **User:** {user.first_name} (`{user.id}`)\n"
            f"📄 **File:** `{file_name}`"
        ),
        parse_mode="Markdown",
        reply_markup=admin_keyboard
    )


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    user_id = query.from_user.id

    if data in ["btn_my_files", "btn_manage"]:
        await show_user_files(query)
    elif data == "btn_upload_guide":
        await query.message.edit_text(
            "📤 **Upload Kaise Karein:**\n\n"
            "Seedhe apni `.py` file ya `.zip` archive is chat me document ki tarah bhej dein. Admin approve karte hi aap run kar sakenge!",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="btn_help")]])
        )
    elif data == "btn_ping":
        start_time = time.time()
        await query.answer("🏓 Pinging...", cache_time=0)
        end_time = time.time()
        ping_ms = round((end_time - start_time) * 1000)
        await query.message.edit_text(
            f"🏓 **Pong!**\nLatency: `{ping_ms}ms`\nStatus: Online 🟢",
            parse_mode="Markdown",
            reply_markup=get_main_keyboard(user_id)
        )
        return
    elif data == "btn_sysinfo":
        cpu = psutil.cpu_percent()
        ram = psutil.virtual_memory().percent
        await query.message.edit_text(
            f"🖥️ **System Resource Usage**\n\n"
            f"⚙️ **CPU:** `{cpu}%`\n"
            f"📊 **RAM:** `{ram}%`\n"
            f"🤖 **Active Bots:** `{len(running_bots)}`",
            parse_mode="Markdown",
            reply_markup=get_main_keyboard(user_id)
        )
    elif data == "btn_help":
        await start(update, context)
        return

    # --- ADMIN ACTIONS ---
    elif data.startswith("approve_"):
        if user_id != ADMIN_ID:
            return
        target_key = data.replace("approve_", "")
        if target_key in db_data["pending"]:
            info = db_data["pending"].pop(target_key)
            db_data["approved"].append(target_key)
            save_data(db_data)

            await query.message.edit_text(f"✅ Approved `{info['file_name']}`.")
            await context.bot.send_message(
                chat_id=info["user_id"],
                text=f"🎉 Aapki file `{info['file_name']}` Admin dwara **Approve** kar di gayi hai!"
            )

    elif data.startswith("reject_"):
        if user_id != ADMIN_ID:
            return
        target_key = data.replace("reject_", "")
        if target_key in db_data["pending"]:
            info = db_data["pending"].pop(target_key)
            if os.path.exists(info["full_path"]):
                os.remove(info["full_path"])
            save_data(db_data)
            await query.message.edit_text(f"❌ Rejected and deleted `{info['file_name']}`.")

    # --- PROCESS CONTROLS ---
    elif data.startswith("run_"):
        file_key = data.replace("run_", "")
        await run_bot_process(file_key, query)
    elif data.startswith("stop_"):
        file_key = data.replace("stop_", "")
        await stop_bot_process(file_key, query)
    elif data.startswith("log_"):
        file_key = data.replace("log_", "")
        await send_logs(file_key, query)
    
    try:
        await query.answer()
    except Exception:
        pass


async def show_user_files(query):
    user_id = query.from_user.id
    user_prefix = f"{user_id}_"

    all_files = os.listdir(HOSTING_DIR)
    if user_id == ADMIN_ID:
        my_files = [f for f in all_files if (f.endswith('.py') or f.endswith('.zip'))]
    else:
        my_files = [f for f in all_files if f.startswith(user_prefix) and (f.endswith('.py') or f.endswith('.zip'))]

    if not my_files:
        await query.message.edit_text(
            "📁 **Koi files nahi mili.**\nKripya pehle koi `.py` ya `.zip` file upload karein.",
            parse_mode="Markdown",
            reply_markup=get_main_keyboard(user_id)
        )
        return

    msg = "📁 **Aapke Uploaded Projects:**\n\n"
    keyboard = []

    for item in my_files:
        clean_name = item.replace(user_prefix, "") if item.startswith(user_prefix) else item
        is_approved = item in db_data["approved"] or user_id == ADMIN_ID
        is_running = item in running_bots

        if not is_approved:
            msg += f"• `{clean_name}` - ⏳ Pending Approval\n"
        elif is_running:
            msg += f"• `{clean_name}` - 🟢 Running (PID: {running_bots[item]['process'].pid})\n"
            keyboard.append([
                InlineKeyboardButton(f"🛑 Stop {clean_name}", callback_data=f"stop_{item}"),
                InlineKeyboardButton(f"📋 Logs", callback_data=f"log_{item}")
            ])
        else:
            msg += f"• `{clean_name}` - 🔴 Stopped\n"
            keyboard.append([
                InlineKeyboardButton(f"🚀 Start {clean_name}", callback_data=f"run_{item}")
            ])

    keyboard.append([InlineKeyboardButton("🔙 Back to Main Menu", callback_data="btn_help")])
    await query.message.edit_text(msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))


async def run_bot_process(file_key: str, query):
    target_path = os.path.join(HOSTING_DIR, file_key)

    if file_key in running_bots:
        await query.message.reply_text("⚠️ Yeh bot pehle se running hai!")
        return

    if file_key.endswith('.zip'):
        extract_folder = os.path.join(HOSTING_DIR, file_key.replace('.zip', ''))
        os.makedirs(extract_folder, exist_ok=True)
        
        with zipfile.ZipFile(target_path, 'r') as zip_ref:
            zip_ref.extractall(extract_folder)
        
        req_file = os.path.join(extract_folder, "requirements.txt")
        if os.path.exists(req_file):
            subprocess.run([sys.executable, "-m", "pip", "install", "-r", req_file], check=False)
        
        # Scan and auto-install for all python files inside zip
        for root, _, files in os.walk(extract_folder):
            for file in files:
                if file.endswith('.py'):
                    auto_install_requirements(os.path.join(root, file))

        main_file = os.path.join(extract_folder, "main.py")
        if not os.path.exists(main_file):
            for root, _, files in os.walk(extract_folder):
                for file in files:
                    if file.endswith('.py'):
                        main_file = os.path.join(root, file)
                        break
            if not os.path.exists(main_file):
                await query.message.reply_text("❌ ZIP ke andar koi valid `.py` file nahi mili.")
                return
        
        cmd = [sys.executable, main_file]
        run_cwd = extract_folder
    else:
        if not os.path.exists(target_path):
            await query.message.reply_text("❌ File nahi mili.")
            return
        
        # Auto-install dependencies for single .py file
        auto_install_requirements(target_path)
        
        cmd = [sys.executable, target_path]
        run_cwd = HOSTING_DIR

    log_path = os.path.join(HOSTING_DIR, f"{file_key}.log")
    log_file = open(log_path, "a")

    proc = subprocess.Popen(cmd, stdout=log_file, stderr=subprocess.STDOUT, cwd=run_cwd)

    running_bots[file_key] = {
        "process": proc,
        "log_file": log_path,
        "log_obj": log_file
    }

    await query.message.reply_text(f"🚀 **Bot Successfully Start Ho Gaya!** (PID: `{proc.pid}`)")
    await show_user_files(query)


async def stop_bot_process(file_key: str, query):
    if file_key not in running_bots:
        await query.message.reply_text("❌ Bot run nahi ho raha hai.")
        return

    bot_info = running_bots.pop(file_key)
    proc = bot_info["process"]

    try:
        parent = psutil.Process(proc.pid)
        for child in parent.children(recursive=True):
            child.terminate()
        parent.terminate()
    except Exception as e:
        logger.error(f"Error: {e}")

    if "log_obj" in bot_info and not bot_info["log_obj"].closed:
        bot_info["log_obj"].close()

    await query.message.reply_text("🛑 **Bot Stop Kar Diya Gaya Hai.**")
    await show_user_files(query)


async def send_logs(file_key: str, query):
    log_path = os.path.join(HOSTING_DIR, f"{file_key}.log")
    if not os.path.exists(log_path):
        await query.message.reply_text("📋 Abhi koi logs available nahi hain.")
        return

    with open(log_path, "r") as f:
        lines = f.readlines()[-25:]
        logs = "".join(lines) if lines else "Log file khali hai."

    await query.message.reply_text(f"📋 **Last 25 Logs:**\n```\n{logs[:3500]}\n```", parse_mode="Markdown")


def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))

    logger.info("Chinnu Hosting Bot Online...")
    app.run_polling()


if __name__ == "__main__":
    main()
