"""
Telegram Bot for posting to channels
Replacement for ControllerBot - @Ipoteka_lux_Bot
"""
import os, logging, asyncio, sqlite3
from datetime import datetime
from aiogram import Bot, Dispatcher, Router, F
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup,
    ChatMemberAdministrator, ChatMemberOwner
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.enums import ParseMode

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
DB_PATH = os.getenv("DB_PATH", "bot_data.db")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS channels (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id INTEGER UNIQUE NOT NULL,
        title TEXT, username TEXT,
        added_by INTEGER, added_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
    c.execute("""CREATE TABLE IF NOT EXISTS posts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER, text TEXT,
        media_type TEXT, media_file_id TEXT,
        published_at TEXT, channels TEXT)""")
    conn.commit(); conn.close()

def get_db():
    return sqlite3.connect(DB_PATH)

class AddChannel(StatesGroup):
    waiting_for_forward = State()

class NewPost(StatesGroup):
    waiting_for_content = State()
    waiting_for_channel_select = State()

router = Router()

@router.message(CommandStart())
async def cmd_start(message: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Мои каналы", callback_data="my_channels")],
        [InlineKeyboardButton(text="✍️ Новый пост", callback_data="new_post")],
        [InlineKeyboardButton(text="⚙️ Настройки", callback_data="settings")],
    ])
    await message.answer(
        f"👋 Привет, {message.from_user.first_name}!\n\n"
        "Я бот для публикации постов в твои Telegram-каналы.\n\n"
        "📢 <b>Мои каналы</b> — управление каналами\n"
        "✍️ <b>Новый пост</b> — создать и опубликовать\n"
        "⚙️ <b>Настройки</b> — настройки бота\n\n"
        "/addchannel — подключить канал\n"
        "/newpost — создать пост\n"
        "/mychannels — список каналов\n"
        "/help — помощь",
        reply_markup=kb, parse_mode=ParseMode.HTML)

@router.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        "📖 <b>Команды:</b>\n\n"
        "/start — главное меню\n"
        "/addchannel — подключить канал\n"
        "/newpost — создать пост\n"
        "/mychannels — список каналов\n"
        "/removechannel — отключить канал\n"
        "/settings — настройки\n"
        "/help — справка\n\n"
        "<b>Как подключить канал:</b>\n"
        "1. Добавь бота в канал как админа\n"
        "2. Дай права на публикацию\n"
        "3. Перешли сюда сообщение из канала",
        parse_mode=ParseMode.HTML)

@router.message(Command("addchannel"))
async def cmd_add_channel(message: Message, state: FSMContext):
    await state.set_state(AddChannel.waiting_for_forward)
    await message.answer(
        "📢 Перешли мне сообщение из канала.\n"
        "⚠️ Бот должен быть админом канала.\n/cancel — отмена",
        parse_mode=ParseMode.HTML)

@router.callback_query(F.data == "add_channel")
async def cb_add_channel(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AddChannel.waiting_for_forward)
    await callback.message.answer("📢 Перешли сообщение из канала.\n/cancel — отмена")
    await callback.answer()

@router.message(AddChannel.waiting_for_forward)
async def process_channel_forward(message: Message, state: FSMContext, bot: Bot):
    if message.text and message.text.startswith("/cancel"):
        await state.clear(); await message.answer("❌ Отменено."); return
    chat_id = None
    if message.forward_from_chat:
        chat_id = message.forward_from_chat.id
    elif message.text and (message.text.startswith("@") or message.text.startswith("-100")):
        try:
            if message.text.startswith("-100"): chat_id = int(message.text.strip())
            else: chat = await bot.get_chat(message.text.strip()); chat_id = chat.id
        except: pass
    if not chat_id:
        await message.answer("❌ Не удалось определить канал. Перешли сообщение из канала."); return
    try:
        bot_member = await bot.get_chat_member(chat_id, bot.id)
        if not isinstance(bot_member, (ChatMemberAdministrator, ChatMemberOwner)):
            await message.answer("❌ Бот не админ канала. Добавь и попробуй снова."); return
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}"); return
    try:
        chat_info = await bot.get_chat(chat_id)
        title = chat_info.title or "Без названия"
        username = chat_info.username or ""
    except: title, username = "Канал", ""
    db = get_db()
    try:
        db.execute("INSERT OR REPLACE INTO channels (chat_id,title,username,added_by) VALUES (?,?,?,?)",
                   (chat_id, title, username, message.from_user.id))
        db.commit()
        await message.answer(f"✅ Канал <b>{title}</b> подключён!\nID: <code>{chat_id}</code>",
                             parse_mode=ParseMode.HTML)
    except Exception as e: await message.answer(f"❌ Ошибка: {e}")
    finally: db.close()
    await state.clear()

@router.message(Command("mychannels"))
async def cmd_my_channels(message: Message): await show_channels(message)

@router.callback_query(F.data == "my_channels")
async def cb_my_channels(callback: CallbackQuery):
    await show_channels(callback.message, edit=True); await callback.answer()

async def show_channels(message: Message, edit: bool = False):
    db = get_db()
    channels = db.execute("SELECT chat_id,title,username FROM channels").fetchall()
    db.close()
    if not channels:
        text = "📢 Нет каналов.\n/addchannel — подключить"
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="➕ Подключить", callback_data="add_channel")]])
    else:
        lines = ["📢 <b>Каналы:</b>\n"]
        for i,(cid,title,uname) in enumerate(channels,1):
            u = f" (@{uname})" if uname else ""
            lines.append(f"{i}. <b>{title}</b>{u}")
        text = "\n".join(lines)
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ Подключить", callback_data="add_channel")],
            [InlineKeyboardButton(text="🗑 Отключить", callback_data="remove_channel_list")]])
    if edit: await message.edit_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
    else: await message.answer(text, reply_markup=kb, parse_mode=ParseMode.HTML)

@router.message(Command("removechannel"))
async def cmd_remove_channel(message: Message): await show_remove_list(message)

@router.callback_query(F.data == "remove_channel_list")
async def cb_remove_list(callback: CallbackQuery):
    await show_remove_list(callback.message); await callback.answer()

async def show_remove_list(message: Message):
    db = get_db()
    channels = db.execute("SELECT id,chat_id,title FROM channels").fetchall()
    db.close()
    if not channels: await message.answer("Нет каналов."); return
    buttons = [[InlineKeyboardButton(text=f"🗑 {t}", callback_data=f"rm_ch_{rid}")] for rid,_,t in channels]
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="my_channels")])
    await message.answer("Выбери канал:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@router.callback_query(F.data.startswith("rm_ch_"))
async def cb_remove(callback: CallbackQuery):
    rid = int(callback.data.split("_")[-1])
    db = get_db()
    ch = db.execute("SELECT title FROM channels WHERE id=?", (rid,)).fetchone()
    if ch: db.execute("DELETE FROM channels WHERE id=?", (rid,)); db.commit()
    db.close()
    await callback.message.edit_text(f"✅ {ch[0]} отключён." if ch else "Не найден.")
    await callback.answer()

@router.message(Command("newpost"))
async def cmd_new_post(message: Message, state: FSMContext):
    db = get_db()
    channels = db.execute("SELECT id,title FROM channels").fetchall()
    db.close()
    if not channels: await message.answer("❌ Сначала /addchannel"); return
    await state.set_state(NewPost.waiting_for_content)
    await state.update_data(channels=channels)
    await message.answer("✍️ Отправь контент: текст, фото, видео или документ.\n/cancel — отмена",
                         parse_mode=ParseMode.HTML)

@router.callback_query(F.data == "new_post")
async def cb_new_post(callback: CallbackQuery, state: FSMContext):
    db = get_db()
    channels = db.execute("SELECT id,title FROM channels").fetchall()
    db.close()
    if not channels: await callback.message.answer("❌ Сначала /addchannel"); await callback.answer(); return
    await state.set_state(NewPost.waiting_for_content)
    await state.update_data(channels=channels)
    await callback.message.answer("✍️ Отправь контент.\n/cancel — отмена")
    await callback.answer()

@router.message(NewPost.waiting_for_content)
async def process_content(message: Message, state: FSMContext):
    if message.text and message.text.startswith("/cancel"):
        await state.clear(); await message.answer("❌ Отменено."); return
    post = {}
    if message.photo:
        post = {"media_type":"photo","media_file_id":message.photo[-1].file_id,"text":message.caption or ""}
    elif message.video:
        post = {"media_type":"video","media_file_id":message.video.file_id,"text":message.caption or ""}
    elif message.document:
        post = {"media_type":"document","media_file_id":message.document.file_id,"text":message.caption or ""}
    elif message.text:
        post = {"media_type":"text","media_file_id":None,"text":message.text}
    else: await message.answer("❌ Неподдерживаемый тип."); return
    await state.update_data(post=post)
    data = await state.get_data()
    channels = data.get("channels",[])
    buttons = []
    if len(channels)>1:
        buttons.append([InlineKeyboardButton(text="📢 Все каналы", callback_data="pub_all")])
    for cid,title in channels:
        buttons.append([InlineKeyboardButton(text=f"📢 {title}", callback_data=f"pub_{cid}")])
    buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_post")])
    await state.set_state(NewPost.waiting_for_channel_select)
    await message.answer("📢 <b>Куда опубликовать:</b>",
                         reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode=ParseMode.HTML)

@router.callback_query(F.data == "cancel_post")
async def cb_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear(); await callback.message.edit_text("❌ Отменено."); await callback.answer()

@router.callback_query(F.data == "pub_all", NewPost.waiting_for_channel_select)
async def cb_pub_all(callback: CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data(); post = data["post"]
    db = get_db(); channels = db.execute("SELECT chat_id,title FROM channels").fetchall(); db.close()
    await callback.message.edit_text("⏳ Публикую...")
    results = []
    for cid,title in channels:
        try: await send_post(bot, cid, post); results.append(f"✅ {title}")
        except Exception as e: results.append(f"❌ {title}: {e}")
    save_history(post, callback.from_user.id, [c[0] for c in channels])
    await callback.message.edit_text("📤 <b>Результат:</b>\n\n"+"\n".join(results), parse_mode=ParseMode.HTML)
    await state.clear(); await callback.answer()

@router.callback_query(F.data.startswith("pub_"), NewPost.waiting_for_channel_select)
async def cb_pub_one(callback: CallbackQuery, state: FSMContext, bot: Bot):
    cid = int(callback.data.split("_")[-1])
    data = await state.get_data(); post = data["post"]
    db = get_db(); ch = db.execute("SELECT chat_id,title FROM channels WHERE id=?", (cid,)).fetchone(); db.close()
    if not ch: await callback.message.edit_text("❌ Канал не найден."); await state.clear(); await callback.answer(); return
    chat_id, title = ch
    try:
        await send_post(bot, chat_id, post)
        save_history(post, callback.from_user.id, [chat_id])
        await callback.message.edit_text(f"✅ Опубликовано в <b>{title}</b>!", parse_mode=ParseMode.HTML)
    except Exception as e: await callback.message.edit_text(f"❌ Ошибка: {e}")
    await state.clear(); await callback.answer()

async def send_post(bot: Bot, chat_id: int, post: dict):
    mt, text, fid = post.get("media_type"), post.get("text",""), post.get("media_file_id")
    if mt == "photo": await bot.send_photo(chat_id, fid, caption=text, parse_mode=ParseMode.HTML)
    elif mt == "video": await bot.send_video(chat_id, fid, caption=text, parse_mode=ParseMode.HTML)
    elif mt == "document": await bot.send_document(chat_id, fid, caption=text, parse_mode=ParseMode.HTML)
    else: await bot.send_message(chat_id, text, parse_mode=ParseMode.HTML)

def save_history(post, user_id, channel_ids):
    db = get_db()
    db.execute("INSERT INTO posts (user_id,text,media_type,media_file_id,published_at,channels) VALUES (?,?,?,?,?,?)",
               (user_id, post.get("text",""), post.get("media_type"), post.get("media_file_id"),
                datetime.now().isoformat(), ",".join(str(c) for c in channel_ids)))
    db.commit(); db.close()

@router.message(Command("settings"))
async def cmd_settings(message: Message): await show_settings(message)

@router.callback_query(F.data == "settings")
async def cb_settings(callback: CallbackQuery):
    await show_settings(callback.message, edit=True); await callback.answer()

async def show_settings(message: Message, edit: bool = False):
    db = get_db()
    ch = db.execute("SELECT COUNT(*) FROM channels").fetchone()[0]
    po = db.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
    db.close()
    text = f"⚙️ <b>Статистика</b>\n\n📢 Каналов: <b>{ch}</b>\n📝 Постов: <b>{po}</b>"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Каналы", callback_data="my_channels")],
        [InlineKeyboardButton(text="✍️ Новый пост", callback_data="new_post")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_start")]])
    if edit: await message.edit_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
    else: await message.answer(text, reply_markup=kb, parse_mode=ParseMode.HTML)

@router.callback_query(F.data == "back_start")
async def cb_back(callback: CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Мои каналы", callback_data="my_channels")],
        [InlineKeyboardButton(text="✍️ Новый пост", callback_data="new_post")],
        [InlineKeyboardButton(text="⚙️ Настройки", callback_data="settings")]])
    await callback.message.edit_text("🏠 <b>Главное меню</b>", reply_markup=kb, parse_mode=ParseMode.HTML)
    await callback.answer()

@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    cur = await state.get_state()
    if cur: await state.clear(); await message.answer("❌ Отменено.")
    else: await message.answer("Нет действия для отмены.")

async def main():
    if not BOT_TOKEN: logger.error("BOT_TOKEN не задан!"); return
    init_db()
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    logger.info("Бот запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
