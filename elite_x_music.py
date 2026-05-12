"""
ELITE X MUSIC - Single File Telegram Music Bot

Setup:
1) pip install pyrogram tgcrypto py-tgcalls yt-dlp python-dotenv
2) Create .env file in same folder:
   API_ID=your_api_id
   API_HASH=your_api_hash
   BOT_TOKEN=your_bot_token
   SESSION_STRING=your_pyrogram_string_session
   OWNER_ID=your_telegram_id
3) Run:
   python elite_x_music.py

Note: Never share BOT_TOKEN, API_HASH, or SESSION_STRING publicly.
"""

import asyncio
import os
import re
import subprocess
from pathlib import Path
from typing import Dict, Optional

from dotenv import load_dotenv
from pyrogram import Client, filters
from pyrogram.enums import ChatMemberStatus
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

try:
    from pytgcalls import PyTgCalls
    from pytgcalls.types.input_stream import AudioPiped
except Exception:
    PyTgCalls = None
    AudioPiped = None

load_dotenv()

# =========================
# CONFIG
# =========================
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
SESSION_STRING = os.getenv("SESSION_STRING", "")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))
PREFIX = os.getenv("PREFIX", "/")

BOT_NAME = "ELITE X MUSIC"
DOWNLOAD_DIR = Path("downloads")
DOWNLOAD_DIR.mkdir(exist_ok=True)

if not API_ID or not API_HASH or not BOT_TOKEN or not SESSION_STRING:
    raise SystemExit(
        "Missing config. Add API_ID, API_HASH, BOT_TOKEN, SESSION_STRING in .env file."
    )

# Bot client for commands
bot = Client(
    "elite_x_music_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
)

# User client for voice chat streaming
user = Client(
    SESSION_STRING,
    api_id=API_ID,
    api_hash=API_HASH,
    session_string=SESSION_STRING,
)

call_py = PyTgCalls(user) if PyTgCalls else None

# Per-chat queue
queues: Dict[int, list] = {}
current: Dict[int, str] = {}

# =========================
# HELPERS
# =========================

def is_url(text: str) -> bool:
    return bool(re.match(r"https?://", text or ""))

async def is_admin(chat_id: int, user_id: int) -> bool:
    if user_id == OWNER_ID:
        return True
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        return member.status in [ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR]
    except Exception:
        return False

async def download_audio(query: str) -> Optional[str]:
    """Download audio with yt-dlp and return file path."""
    safe_name = str(abs(hash(query)))
    output = DOWNLOAD_DIR / f"{safe_name}.%(ext)s"
    search_query = query if is_url(query) else f"ytsearch1:{query}"

    cmd = [
        "yt-dlp",
        "-x",
        "--audio-format",
        "mp3",
        "--audio-quality",
        "0",
        "--no-playlist",
        "-o",
        str(output),
        search_query,
    ]

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, err = await proc.communicate()
    if proc.returncode != 0:
        print("yt-dlp error:", err.decode(errors="ignore"))
        return None

    files = list(DOWNLOAD_DIR.glob(f"{safe_name}.*"))
    return str(files[0]) if files else None

async def play_next(chat_id: int, message: Optional[Message] = None):
    if not queues.get(chat_id):
        current.pop(chat_id, None)
        return

    title, audio_path = queues[chat_id].pop(0)
    current[chat_id] = title

    try:
        await call_py.change_stream(chat_id, AudioPiped(audio_path))
    except Exception:
        await call_py.join_group_call(chat_id, AudioPiped(audio_path))

    if message:
        await message.reply_text(f"▶️ Now Playing: **{title}**")

# =========================
# COMMANDS
# =========================

@bot.on_message(filters.command("start", prefixes=PREFIX))
async def start_cmd(_, message: Message):
    buttons = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("➕ Add Me To Group", url=f"https://t.me/{(await bot.get_me()).username}?startgroup=true")],
            [InlineKeyboardButton("📚 Help", callback_data="help")],
        ]
    )
    await message.reply_photo(
        photo="https://graph.org/file/4a60754e91eb1bb137fdd.jpg",
        caption=(
            f"🎧 **{BOT_NAME}**\n\n"
            "Premium Telegram VC Music Bot\n"
            "Use /play song_name in group voice chat."
        ),
        reply_markup=buttons,
    )

@bot.on_message(filters.command("help", prefixes=PREFIX))
async def help_cmd(_, message: Message):
    await message.reply_text(
        "🎧 **ELITE X MUSIC Commands**\n\n"
        "/play song name - Play song\n"
        "/pause - Pause music\n"
        "/resume - Resume music\n"
        "/skip - Skip current song\n"
        "/stop - Stop and leave VC\n"
        "/queue - Show queue\n"
        "/ping - Check bot alive\n\n"
        "Note: Group me voice chat ON hona chahiye."
    )

@bot.on_message(filters.command("ping", prefixes=PREFIX))
async def ping_cmd(_, message: Message):
    await message.reply_text("🏓 Pong! ELITE X MUSIC is alive.")

@bot.on_message(filters.command("play", prefixes=PREFIX) & filters.group)
async def play_cmd(_, message: Message):
    if not call_py:
        await message.reply_text("❌ pytgcalls install nahi hai. Run: pip install py-tgcalls")
        return

    query = " ".join(message.command[1:])
    if not query:
        await message.reply_text("Usage: `/play song name or YouTube link`")
        return

    msg = await message.reply_text("🔎 Searching & downloading...")
    audio_path = await download_audio(query)
    if not audio_path:
        await msg.edit_text("❌ Song download failed. Dusra song/link try karo.")
        return

    chat_id = message.chat.id
    queues.setdefault(chat_id, [])
    title = query[:80]

    if chat_id in current:
        queues[chat_id].append((title, audio_path))
        await msg.edit_text(f"✅ Added to queue: **{title}**")
    else:
        queues[chat_id].append((title, audio_path))
        await msg.edit_text("🎶 Starting music...")
        await play_next(chat_id, message)

@bot.on_message(filters.command("queue", prefixes=PREFIX) & filters.group)
async def queue_cmd(_, message: Message):
    chat_id = message.chat.id
    q = queues.get(chat_id, [])
    now = current.get(chat_id, "Nothing playing")
    text = f"🎧 **Now:** {now}\n\n"
    if not q:
        text += "📭 Queue empty."
    else:
        text += "📜 **Queue:**\n" + "\n".join([f"{i+1}. {x[0]}" for i, x in enumerate(q[:10])])
    await message.reply_text(text)

@bot.on_message(filters.command("pause", prefixes=PREFIX) & filters.group)
async def pause_cmd(_, message: Message):
    if not await is_admin(message.chat.id, message.from_user.id):
        await message.reply_text("❌ Sirf admin pause kar sakta hai.")
        return
    try:
        await call_py.pause_stream(message.chat.id)
        await message.reply_text("⏸ Music paused.")
    except Exception as e:
        await message.reply_text(f"❌ Pause error: `{e}`")

@bot.on_message(filters.command("resume", prefixes=PREFIX) & filters.group)
async def resume_cmd(_, message: Message):
    try:
        await call_py.resume_stream(message.chat.id)
        await message.reply_text("▶️ Music resumed.")
    except Exception as e:
        await message.reply_text(f"❌ Resume error: `{e}`")

@bot.on_message(filters.command("skip", prefixes=PREFIX) & filters.group)
async def skip_cmd(_, message: Message):
    if not await is_admin(message.chat.id, message.from_user.id):
        await message.reply_text("❌ Sirf admin skip kar sakta hai.")
        return
    await message.reply_text("⏭ Skipping...")
    await play_next(message.chat.id, message)

@bot.on_message(filters.command("stop", prefixes=PREFIX) & filters.group)
async def stop_cmd(_, message: Message):
    if not await is_admin(message.chat.id, message.from_user.id):
        await message.reply_text("❌ Sirf admin stop kar sakta hai.")
        return
    chat_id = message.chat.id
    queues.pop(chat_id, None)
    current.pop(chat_id, None)
    try:
        await call_py.leave_group_call(chat_id)
    except Exception:
        pass
    await message.reply_text("⏹ Music stopped and VC left.")

# =========================
# RUN
# =========================

async def main():
    print(f"Starting {BOT_NAME}...")
    await user.start()
    await bot.start()
    if call_py:
        await call_py.start()
    print(f"{BOT_NAME} started successfully!")
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
