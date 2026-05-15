import asyncio
import json
import time
import os
import psutil
import logging
import static_ffmpeg

static_ffmpeg.add_paths()

try:
    loop = asyncio.get_event_loop()
except RuntimeError:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

from pyrogram import Client, filters, idle
from pyrogram.types import (
    Message,
    BotCommand,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery
)

import pyrogram.errors

try:
    from pyrogram.errors import GroupcallForbidden
except ImportError:
    class GroupcallForbidden(pyrogram.errors.exceptions.forbidden_403.Forbidden):
        pass
    pyrogram.errors.GroupcallForbidden = GroupcallForbidden

from pytgcalls import PyTgCalls
from pytgcalls.types import MediaStream, Update, StreamEnded
from yt_dlp import YoutubeDL
from config import API_ID, API_HASH, BOT_TOKEN, SESSION_STRING, OWNER_ID

logging.basicConfig(level=logging.INFO)

if not os.path.exists("downloads"):
    os.makedirs("downloads")

bot = Client(
    "MusicBot3",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

user = Client(
    "UserSession3",
    api_id=API_ID,
    api_hash=API_HASH,
    session_string=SESSION_STRING
)

call_py = PyTgCalls(user)

ydl_opts = {
    'format': 'bestaudio/best',
    'outtmpl': 'downloads/%(id)s.%(ext)s',
    'noplaylist': True,
    'quiet': True,

    'cookiefile': 'cookies.txt',

    'extract_flat': False,
    'geo_bypass': True,
    'nocheckcertificate': True,

    'extractor_args': {
        'youtube': {
            'player_client': ['android', 'web']
        }
    },

    'http_headers': {
        'User-Agent':
        'com.google.android.youtube/19.09.37 (Linux; Android 12)'
    }
}

QUEUE = {}
PLAYING = {}
START_TIME = time.time()


def load_chats():
    if os.path.exists("chats.json"):
        try:
            with open("chats.json", "r") as f:
                return set(json.load(f))
        except:
            pass
    return set()


def save_chats():
    with open("chats.json", "w") as f:
        json.dump(list(TRACKED_CHATS), f)


TRACKED_CHATS = load_chats()


@bot.on_message(filters.group | filters.private, group=1)
async def track_chats(client, message):
    if message.chat:
        cid = message.chat.id
        if cid not in TRACKED_CHATS:
            TRACKED_CHATS.add(cid)
            save_chats()


def get_control_markup():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "⏸ Pause",
                callback_data="pause"
            ),
            InlineKeyboardButton(
                "▶️ Resume",
                callback_data="resume"
            )
        ],
        [
            InlineKeyboardButton(
                "⏭ Skip",
                callback_data="skip"
            ),
            InlineKeyboardButton(
                "⏹ Stop",
                callback_data="stop"
            )
        ]
    ])


async def extract_song(query):

    def run():
        with YoutubeDL(ydl_opts) as ydl:

            search_query = (
                query
                if query.startswith("http")
                else f"ytsearch1:{query}"
            )

            info = ydl.extract_info(
                search_query,
                download=True
            )

            if "entries" in info:
                info = info["entries"][0]

            filepath = os.path.abspath(
                ydl.prepare_filename(info)
            )

            return {
                "title":
                info.get(
                    "title",
                    "Unknown"
                ),

                "thumbnail":
                info.get(
                    "thumbnail",
                    "https://telegra.ph/file/default.jpg"
                ),

                "file":
                filepath
            }

    return await asyncio.to_thread(run)


async def play_next(chat_id):

    if chat_id in QUEUE and QUEUE[chat_id]:

        next_song = QUEUE[chat_id].pop(0)

        try:

            await call_py.play(
                chat_id,
                MediaStream(
                    next_song["file"],
                    video_flags=MediaStream.Flags.IGNORE
                )
            )

            PLAYING[chat_id] = True

            await bot.send_photo(
                chat_id,
                photo=next_song["thumbnail"],
                caption=f"▶️ **Now Playing:**\n{next_song['title']}",
                reply_markup=get_control_markup()
            )

        except Exception as e:

            await bot.send_message(
                chat_id,
                f"❌ {e}"
            )

            await play_next(chat_id)

    else:

        PLAYING[chat_id] = False

        try:
            await call_py.leave_call(chat_id)
        except:
            pass


@call_py.on_update()
async def stream_handler(client, update):

    if isinstance(update, StreamEnded):

        await play_next(
            update.chat_id
        )


@bot.on_message(filters.command("play") & filters.group)
async def play(client, message: Message):

    if len(message.command) < 2:
        return await message.reply_text(
            "Usage:\n/play song"
        )

    query = " ".join(message.command[1:])

    msg = await message.reply_text(
        "🔎 Searching..."
    )

    try:

        data = await extract_song(query)

        chat_id = message.chat.id

        if PLAYING.get(chat_id):

            QUEUE.setdefault(
                chat_id,
                []
            )

            QUEUE[chat_id].append(
                data
            )

            await msg.delete()

            return await message.reply_photo(
                photo=data["thumbnail"],
                caption=f"📝 Added To Queue\n\n{data['title']}"
            )

        await msg.edit_text(
            "🎵 Joining VC..."
        )

        await call_py.play(
            chat_id,
            MediaStream(
                data["file"],
                video_flags=MediaStream.Flags.IGNORE
            )
        )

        PLAYING[chat_id] = True

        await msg.delete()

        await message.reply_photo(
            photo=data["thumbnail"],
            caption=f"▶️ Now Playing\n\n{data['title']}",
            reply_markup=get_control_markup()
        )

    except Exception as e:

        await msg.edit_text(
            f"❌ Error:\n{e}"
        )


@bot.on_message(filters.command("playforce") & filters.group)
async def playforce(client, message):

    if len(message.command) < 2:
        return

    query = " ".join(
        message.command[1:]
    )

    msg = await message.reply_text(
        "⚡ Force searching..."
    )

    try:

        data = await extract_song(
            query
        )

        await call_py.play(
            message.chat.id,
            MediaStream(
                data["file"],
                video_flags=MediaStream.Flags.IGNORE
            )
        )

        PLAYING[
            message.chat.id
        ] = True

        await msg.delete()

        await message.reply_photo(
            photo=data["thumbnail"],
            caption=f"⚡ Force Playing\n\n{data['title']}",
            reply_markup=get_control_markup()
        )

    except Exception as e:

        await msg.edit_text(
            f"❌ {e}"
        )


@bot.on_message(filters.command("skip"))
async def skip(client, message):

    await play_next(
        message.chat.id
    )

    await message.reply_text(
        "⏭ Skipped"
    )


@bot.on_message(filters.command("stop"))
async def stop(client, message):

    cid = message.chat.id

    QUEUE[cid] = []

    PLAYING[cid] = False

    try:
        await call_py.leave_call(cid)
    except:
        pass

    await message.reply_text(
        "⏹ Stopped"
    )


@bot.on_message(filters.command("ping"))
async def ping(client, message):

    await message.reply_text(
        "🏓 Pong"
    )


@bot.on_message(filters.command("stats"))
async def stats(client, message):

    uptime = int(
        time.time() -
        START_TIME
    )

    await message.reply_text(
f"""📊 Bot Stats

⏱ Uptime: {uptime}s
👥 Chats: {len(TRACKED_CHATS)}
🎵 Active VC: {sum(PLAYING.values())}
💾 RAM: {psutil.virtual_memory().percent}%
🖥 CPU: {psutil.cpu_percent()}%
"""
    )


@bot.on_callback_query()
async def callback(client, query):

    cid = query.message.chat.id

    try:

        if query.data == "pause":
            await call_py.pause_stream(cid)

        elif query.data == "resume":
            await call_py.resume_stream(cid)

        elif query.data == "skip":
            await play_next(cid)

        elif query.data == "stop":

            QUEUE[cid] = []

            PLAYING[cid] = False

            await call_py.leave_call(
                cid
            )

        await query.answer()

    except Exception as e:

        await query.answer(
            str(e),
            show_alert=True
        )


async def main():

    print("Bot starting...")

    await bot.start()

    await user.start()

    await call_py.start()

    await bot.set_bot_commands([
        BotCommand(
            "play",
            "Play music"
        ),
        BotCommand(
            "playforce",
            "Force play"
        ),
        BotCommand(
            "skip",
            "Skip music"
        ),
        BotCommand(
            "stop",
            "Stop music"
        ),
        BotCommand(
            "ping",
            "Ping"
        ),
        BotCommand(
            "stats",
            "Stats"
        )
    ])

    print("Bot started.")

    await idle()


if __name__ == "__main__":
    loop.run_until_complete(
        main()
    )