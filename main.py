"""
Video Music Bot - YouTube va Instagram videolaridan musiqa yuklovchi bot
Created by: Botirbek Tulqinov
Created at: 2025-02-05 07:21:49 UTC
"""

import os
import logging
from datetime import datetime, time
import sqlite3
from typing import Final, Optional, Dict, Any, List
from shazamio import Shazam
import requests
import asyncio
from moviepy.editor import VideoFileClip
import aiofiles
from urllib.parse import urlparse, parse_qs
import re  
from config import Config

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, error, CallbackQuery
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler, 
    CallbackQueryHandler,
    ConversationHandler,
    filters,
    ContextTypes
)
import ssl
import certifi

# SSL muammosini hal qilish
ssl._create_default_https_context = ssl._create_unverified_context

# Bot konfiguratsiyasi


# Conversation states
DB_FILE: Final = "bot_database.db"
DOWNLOADS_DIR: Final = "downloads"
ADMIN_CONTACT: Final = "https://t.me/hkarise"  # Admin bilan bog'lanish linki
BOT_INSTRUCTIONS: Final = """
🤖 Video Music Bot Qo'llanmasi

1️⃣ Botdan foydalanish uchun quyidagi kanallarga a'zo bo'ling:
{channels_list}

2️⃣ Bot imkoniyatlari:
• YouTube va Instagram videolaridan musiqa yuklab olish
• Videodagi qo'shiqni aniqlash
• Qo'shiqning to'liq versiyasini topib berish
• Qo'shiq haqida to'liq ma'lumot (nomi, ijrochi, so'zlari)

3️⃣ Buyruqlar:
/start - Botni ishga tushirish
/help - Ushbu qo'llanmani ko'rish
/stop - Botni to'xtatish

❓ Muammo yoki savollar bo'lsa:
👤 Admin: {admin_contact}

⚠️ Eslatma: Bot faqat kanal a'zolari uchun ishlaydi!
"""

# Logging sozlamalari
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=getattr(logging, Config.LOG_LEVEL)
)
logger = logging.getLogger(__name__)
YDL_OPTS = {
    'format': 'bestaudio/best',
    'quiet': True,
    'no_warnings': True,
    'extract_flat': True,
    'default_search': 'ytsearch',
    'noplaylist': True,
}

RESULTS_PER_PAGE = 10  # Har bir sahifada ko'rsatiladigan natijalar soni

# Conversation states
        
ADDING_CHANNEL = range(1)
ADMIN_AUTH = range(1)  # Admin autentifikatsiyasi uchun
BROADCAST = range(1)  # Conversation state uchun

class Database:
    def __init__(self):
        self.init_database()

    def init_database(self):
        """Database yaratish"""
        try:
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            
            # Kanallar jadvali
            c.execute('''CREATE TABLE IF NOT EXISTS channels
                        (id INTEGER PRIMARY KEY AUTOINCREMENT,
                        channel_id TEXT UNIQUE,
                        channel_name TEXT,
                        added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
            
            # Foydalanuvchilar jadvali
            c.execute('''CREATE TABLE IF NOT EXISTS users
                        (id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER UNIQUE,
                        username TEXT,
                        first_name TEXT,
                        joined_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        is_blocked INTEGER DEFAULT 0)''')
            
            # Yuklanmalar jadvali
            c.execute('''CREATE TABLE IF NOT EXISTS downloads
                        (id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER,
                        file_type TEXT,
                        file_name TEXT,
                        file_size INTEGER,
                        download_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES users(user_id))''')
            
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Database yaratishda xato: {str(e)}")
    def create_tables():
        """Database jadvallarini yaratish"""
        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()
        
        # Foydalanuvchilar jadvali
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE,
            username TEXT,
            first_name TEXT,
            joined_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_blocked INTEGER DEFAULT 0
        )
        """)
        
        # Kanallar jadvali
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS channels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel_id TEXT UNIQUE,
            channel_name TEXT,
            added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        
        # Yuklab olishlar jadvali
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS downloads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            file_type TEXT,
            file_name TEXT,
            file_size INTEGER,
            download_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
        """)
        
        conn.commit()
        conn.close()

    def add_channel(self, channel_id: str, channel_name: str) -> bool:
        """Yangi kanal qo'shish"""
        try:
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            
            # Kanal mavjudligini tekshirish
            c.execute("SELECT channel_id FROM channels WHERE channel_id = ?", (channel_id,))
            if c.fetchone():
                conn.close()
                return False
            
            # Yangi kanalni qo'shish
            c.execute(
                "INSERT INTO channels (channel_id, channel_name) VALUES (?, ?)",
                (channel_id, channel_name)
            )
            
            conn.commit()
            conn.close()
            return True
            
        except Exception as e:
            logger.error(f"Database: Kanal qo'shishda xato: {str(e)}")
            return False
    # Database klasiga o'chirish metodini qo'shamiz
    def remove_channel(self, channel_id: str) -> bool:
        """Kanalni o'chirish"""
        try:
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            
            # Kanalni o'chirish
            c.execute("DELETE FROM channels WHERE channel_id = ?", (channel_id,))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"Kanalni o'chirishda xato: {str(e)}")
            return False

    def get_channels(self) -> List[Dict[str, str]]:
        """Barcha kanallarni olish"""
        try:
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("SELECT channel_id, channel_name FROM channels")
            channels = [{"channel_id": row[0], "channel_name": row[1]} 
                       for row in c.fetchall()]
            conn.close()
            return channels
        except Exception as e:
            logger.error(f"Kanallarni olishda xato: {str(e)}")
            return []

    def add_user(self, user_id: int, username: str, first_name: str) -> bool:
        """Yangi foydalanuvchi qo'shish"""
        try:
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute(
                "INSERT OR REPLACE INTO users (user_id, username, first_name, joined_date) VALUES (?, ?, ?, ?)",
                (user_id, username, first_name, datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'))
            )
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"Foydalanuvchi qo'shishda xato: {str(e)}")
            return False

    def add_download(self, user_id: int, file_type: str, file_name: str, file_size: int) -> bool:
        """Yuklanmani qayd qilish"""
        try:
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute(
                "INSERT INTO downloads (user_id, file_type, file_name, file_size, download_date) VALUES (?, ?, ?, ?, ?)",
                (user_id, file_type, file_name, file_size, datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'))
            )
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"Yuklanmani qo'shishda xato: {str(e)}")
            return False
    def get_active_users_count(self, days: int) -> int:
        """Ma'lum kun ichida faol bo'lgan foydalanuvchilar sonini olish"""
        try:
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("""
                SELECT COUNT(DISTINCT user_id) FROM downloads 
                WHERE timestamp >= datetime('now', '-' || ? || ' days')
            """, (days,))
            count = c.fetchone()[0]
            conn.close()
            return count
        except Exception as e:
            logger.error(f"Faol foydalanuvchilarni olishda xato: {str(e)}")
            return 0

    def get_users_count(self) -> int:
        """Jami foydalanuvchilar sonini olish"""
        try:
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM users WHERE is_blocked = 0")
            count = c.fetchone()[0]
            conn.close()
            return count
        except Exception as e:
            logger.error(f"Foydalanuvchilar sonini olishda xato: {str(e)}")
            return 0

    def get_statistics(self) -> Dict[str, Any]:
        """Bot statistikasini olish"""
        try:
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            
            # Umumiy foydalanuvchilar
            c.execute("SELECT COUNT(*) FROM users WHERE is_blocked = 0")
            total_users = c.fetchone()[0]
            
            # Bugungi yuklanmalar
            today = datetime.utcnow().strftime('%Y-%m-%d')
            c.execute("SELECT COUNT(*) FROM downloads WHERE date(download_date) = date(?)", (today,))
            today_downloads = c.fetchone()[0]
            
            # Fayl turlari bo'yicha statistika
            c.execute("SELECT file_type, COUNT(*) FROM downloads GROUP BY file_type")
            downloads_by_type = dict(c.fetchall())
            
            # Umumiy yuklangan hajm
            c.execute("SELECT SUM(file_size) FROM downloads")
            total_size = c.fetchone()[0] or 0
            
            conn.close()
            
            return {
                "total_users": total_users,
                "today_downloads": today_downloads,
                "downloads_by_type": downloads_by_type,
                "total_size_mb": round(total_size / (1024 * 1024), 2)
            }
        except Exception as e:
            logger.error(f"Statistika olishda xato: {str(e)}")
            return {
                "total_users": 0,
                "today_downloads": 0,
                "downloads_by_type": {},
                "total_size_mb": 0
            }
    def get_all_users(self) -> List[Dict[str, Any]]:
        """Barcha foydalanuvchilarni olish"""
        try:
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("SELECT user_id, username, first_name FROM users WHERE is_blocked = 0")
            users = [{"user_id": row[0], "username": row[1], "first_name": row[2]} 
                    for row in c.fetchall()]
            conn.close()
            return users
        except Exception as e:
            logger.error(f"Foydalanuvchilarni olishda xato: {str(e)}")
            return []

    def clear_cache(self) -> bool:
        """Cache ni tozalash"""
        try:
            # Downloads papkasini tozalash
            for file in os.listdir(DOWNLOADS_DIR):
                file_path = os.path.join(DOWNLOADS_DIR, file)
                try:
                    if os.path.isfile(file_path):
                        os.unlink(file_path)
                except Exception as e:
                    logger.error(f"Faylni o'chirishda xato: {str(e)}")
            return True
        except Exception as e:
            logger.error(f"Cache ni tozalashda xato: {str(e)}")
            return False

# Database instance yaratish
db = Database()

# Kategoriyalar uchun keyboard yaratish
def get_main_keyboard():
    keyboard = [
        [KeyboardButton("🎵 Qo'shiq izlash"), KeyboardButton("🎬 YouTube")],
        [KeyboardButton("📸 Instagram")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
# Admin keyboard
def get_admin_keyboard():
    keyboard = [    
        [KeyboardButton("📊 Statistika"), KeyboardButton("📋 Kanallar ro'yxati")],
        [KeyboardButton("➕ Kanal qo'shish"), KeyboardButton("➖ Kanal o'chirish")],
        [KeyboardButton("📝 Xabar yuborish"), KeyboardButton("⚙️ Sozlamalar")],
        [KeyboardButton("◀️ Asosiy menyu")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# Start funksiyasini yangilash
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Start buyrug'i"""
    user = update.effective_user
    db.add_user(user.id, user.username, user.first_name)
    
    # Kanal a'zoligini tekshirish
    if not await check_subscription(update, context):
        return
    
    # User state ni tozalash
    context.user_data.clear()
    
    await update.message.reply_text(
        f"Salom {user.first_name}! 👋\n\n"
        "Quyidagi bo'limlardan birini tanlang:",
        reply_markup=get_main_keyboard()
    )
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Help buyrug'i"""
    # Kanallar ro'yxatini olish
    channels = db.get_channels()
    channels_list = "\n".join([f"• {channel['channel_name']} - {channel['channel_id']}" 
                              for channel in channels]) or "Hozircha kanallar yo'q"
    
    # Qo'llanmani yuborish
    help_text = BOT_INSTRUCTIONS.format(
        channels_list=channels_list,
        admin_contact=ADMIN_CONTACT
    )
    
    await update.message.reply_text(help_text, parse_mode='HTML')

async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Stop buyrug'i"""
    await update.message.reply_text(
        "👋 Bot to'xtatildi. Qayta ishga tushirish uchun /start buyrug'ini yuboring."
    )
    # Foydalanuvchi contextini tozalash
    context.user_data.clear()

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin buyrug'i"""
    user = update.effective_user
    
    # Admin ekanligini tekshirish
    if not (str(user.id) in map(str, Config.ADMIN_ID) or user.username == Config.ADMIN_USERNAME.replace("@", "")):
        await update.message.reply_text(
            "❌ Bu buyruq faqat admin uchun!\n"
            f"👤 Admin: {ADMIN_CONTACT}"
        )
        return
    
    await update.message.reply_text(
        "🔐 Admin panelga kirish uchun /parol <parol> ko'rinishida kiriting\n"
        "Masalan: /parol nimadir"
    )

async def check_admin_password(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin parolini tekshirish"""
    user = update.effective_user
    
    # Admin ekanligini tekshirish
    if not (str(user.id) in map(str, Config.ADMIN_IDS) or user.username == Config.ADMIN_USERNAME.replace("@", "")):
        return
    
    # Parolni olish
    try:
        entered_password = context.args[0] if context.args else ""
    except:
        entered_password = ""
    
    if entered_password == Config.ADMIN_PASSWORD:
        # Admin state ni saqlash
        context.user_data['is_admin'] = True
        
        # Admin panelni ochish
        await update.message.reply_text(
            "✅ Admin panelga xush kelibsiz!\n\n"
            "Quyidagi amallardan birini tanlang:",
            reply_markup=get_admin_keyboard()
        )
    else:
        await update.message.reply_text(
            "❌ Noto'g'ri parol!\n"
            "Qayta urinib ko'ring: /parol <parol>"
        )

async def admin_auth(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Admin parolini tekshirish"""
    entered_password = update.message.text.strip()
    
    if entered_password == Config.ADMIN_PASSWORD:
        # Admin state ni saqlash
        context.user_data['is_admin'] = True
        
        # Admin panelni ochish
        await update.message.reply_text(
            "✅ Admin panelga xush kelibsiz!\n\n"
            "📊 Statistika\n"
            "📋 Kanallar ro'yxati\n"
            "➕ Kanal qo'shish\n"
            "➖ Kanal o'chirish\n"
            "📝 Xabar yuborish\n"
            "⚙️ Sozlamalar\n\n"
            "Kerakli bo'limni tanlang:",
            reply_markup=get_admin_keyboard()
        )
        return ConversationHandler.END
    else:
        await update.message.reply_text(
            "❌ Noto'g'ri parol!\n"
            "Qayta urinib ko'ring yoki bekor qilish uchun /cancel buyrug'ini yuboring"
        )
        return ADMIN_AUTH

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Autentifikatsiyani bekor qilish"""
    await update.message.reply_text(
        "Admin panelga kirish bekor qilindi.",
        reply_markup=get_main_keyboard()
    )
    return ConversationHandler.END

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin panel"""
    if not is_admin(update):
        await update.message.reply_text("❌ Bu buyruq faqat admin uchun!")
        return

    keyboard = [
        [KeyboardButton("➕ Kanal qo'shish"), KeyboardButton("➖ Kanal o'chirish")],
        [KeyboardButton("📊 Statistika"), KeyboardButton("📋 Kanallar ro'yxati")],
        [KeyboardButton("📝 Xabar yuborish"), KeyboardButton("⚙️ Sozlamalar")]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    await update.message.reply_text(
        "🔰 Admin panel:\n"
        "Quyidagi amallardan birini tanlang:",
        reply_markup=reply_markup
    )
# Admin ekanligini tekshirish funksiyasi
def is_admin(update: Update) -> bool:
    """Foydalanuvchi admin ekanligini tekshirish"""
    user = update.effective_user
    return (user.username == Config.ADMIN_USERNAME or 
            user.id in Config.ADMIN_IDS)
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Bekor qilish buyrug'i"""
    await update.message.reply_text(
        "❌ Admin panelga kirish bekor qilindi.",
        reply_markup=ReplyKeyboardRemove()
    )
    if 'is_admin' in context.user_data:
        del context.user_data['is_admin']
    return ConversationHandler.END


async def show_statistics(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Bot statistikasini ko'rsatish"""
    if not is_admin(update):
        await update.message.reply_text("❌ Bu buyruq faqat admin uchun!")
        return

    try:
        stats = db.get_statistics()
        
        stats_text = (
            "📊 Bot Statistikasi\n\n"
            f"👥 Foydalanuvchilar: {stats['total_users']}\n"
            f"📥 Bugungi yuklanmalar: {stats['today_downloads']}\n"
            f"💾 Jami yuklangan hajm: {stats['total_size_mb']} MB\n\n"
            "📁 Fayl turlari bo'yicha:\n"
        )
        
        for file_type, count in stats['downloads_by_type'].items():
            stats_text += f"- {file_type}: {count} ta\n"
            
        stats_text += f"\n🕐 Yangilangan vaqt: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        
        await update.message.reply_text(stats_text)
        
    except Exception as e:
        logger.error(f"Statistika ko'rsatishda xato: {str(e)}")
        await update.message.reply_text("❌ Statistikani ko'rsatishda xatolik yuz berdi")


async def add_channel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Kanal qo'shish boshlash"""
    if not is_admin(update):
        await update.message.reply_text("❌ Bu buyruq faqat admin uchun!")
        return ConversationHandler.END
    
    await update.message.reply_text(
        "Yangi kanal ma'lumotlarini quyidagi formatda yuboring:\n"
        "@kanal_id Kanal nomi\n\n"
        "Masalan: @unilance 1-kanal\n\n"
        "Bekor qilish uchun /cancel"
    )
    return ADDING_CHANNEL
async def add_channel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Kanal qo'shish"""
    if not is_admin(update):
        await update.message.reply_text("❌ Bu buyruq faqat admin uchun!")
        return ConversationHandler.END
        
    try:
        text = update.message.text.strip()
        
        if not text:
            await update.message.reply_text(
                "❌ Kanal ma'lumotlari kiritilmadi!\n\n"
                "✅ To'g'ri format:\n"
                "https://t.me/kanal_linki Kanal nomi\n\n"
                "Masalan:\n"
                "https://t.me/best_master_uz_official 1-kanal"
            )
            return ADDING_CHANNEL

        # Link va kanal nomini ajratish
        parts = text.split()
        if len(parts) < 2:
            await update.message.reply_text(
                "❌ Kanal nomi kiritilmadi!\n\n"
                "✅ To'g'ri format:\n"
                "https://t.me/kanal_linki Kanal nomi\n\n"
                "Masalan:\n"
                "https://t.me/best_master_uz_official 1-kanal"
            )
            return ADDING_CHANNEL

        channel_link = parts[0]
        channel_name = ' '.join(parts[1:])

        # Linkdan username ni ajratib olish
        if "t.me/" in channel_link:
            channel_username = channel_link.split("t.me/")[-1].strip()
            channel_username = channel_username.replace("@", "").strip("/")
            channel_id = f"@{channel_username}"
            
            # Kanalni bazaga qo'shish
            if db.add_channel(channel_id, channel_name):
                # Bot o'zini kanal adminligini tekshirish
                try:
                    bot_member = await context.bot.get_chat_member(
                        chat_id=channel_id,
                        user_id=context.bot.id
                    )
                    if bot_member.status not in ['administrator']:
                        await update.message.reply_text(
                            "⚠️ Diqqat! Bot kanalda admin emas!\n"
                            "Botni kanalga admin qilib qo'ying."
                        )
                except Exception as e:
                    await update.message.reply_text(
                        "❌ Bot kanalni topa olmadi yoki kanalda admin emas!\n"
                        "Iltimos, quyidagilarni tekshiring:\n"
                        "1. Kanal linki to'g'ri kiritilganini\n"
                        "2. Bot kanalga qo'shilganini\n"
                        "3. Bot kanalda admin huquqlariga ega ekanini"
                    )
                    logger.error(f"Kanal tekshirishda xato: {str(e)}")
                    return ADDING_CHANNEL
                    
                channels = db.get_channels()
                channels_text = "✅ Kanal muvaffaqiyatli qo'shildi!\n\n📢 Kanallar ro'yxati:\n\n"
                
                for i, ch in enumerate(channels, 1):
                    channels_text += f"{i}. {ch['channel_name']}\n"
                    channels_text += f"└ {ch['channel_id']}\n\n"
                
                await update.message.reply_text(channels_text)
                return ConversationHandler.END
            else:
                await update.message.reply_text("❌ Bu kanal allaqachon qo'shilgan!")
                return ADDING_CHANNEL
        else:
            await update.message.reply_text(
                "❌ Noto'g'ri kanal linki!\n\n"
                "✅ Link formati:\n"
                "https://t.me/kanal_linki\n\n"
                "Masalan:\n"
                "https://t.me/best_master_uz_official 1-kanal"
            )
            return ADDING_CHANNEL

    except Exception as e:
        logger.error(f"Kanal qo'shishda xato: {str(e)}")
        await update.message.reply_text(
            "❌ Xatolik yuz berdi!\n"
            "Qaytadan urinib ko'ring"
        )
        return ADDING_CHANNEL

async def remove_channel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Kanal o'chirish"""
    if not is_admin(update):
        await update.message.reply_text("❌ Bu buyruq faqat admin uchun!")
        return

    channels = db.get_channels()
    if not channels:
        await update.message.reply_text("❌ Kanallar ro'yxati bo'sh!")
        return
    
    # Kanallar ro'yxatini tugmalar bilan ko'rsatish
    keyboard = []
    for channel in channels:
        keyboard.append([
            InlineKeyboardButton(
                f"❌ {channel['channel_name']} ({channel['channel_id']})", 
                callback_data=f"del_{channel['channel_id']}"
            )
        ])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "🗑 O'chirmoqchi bo'lgan kanalngizni tanlang:",
        reply_markup=reply_markup
    )

async def show_channels(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Kanallar ro'yxatini ko'rsatish"""
    if not is_admin(update):
        await update.message.reply_text("❌ Bu buyruq faqat admin uchun!")
        return

    channels = db.get_channels()
    if not channels:
        await update.message.reply_text("❌ Hozircha kanallar yo'q!")
        return

    channels_text = "📢 Kanallar ro'yxati:\n\n"
    
    for i, channel in enumerate(channels, 1):
        channels_text += f"{i}. {channel['channel_name']}\n"
        channels_text += f"└ {channel['channel_id']}\n\n"

    await update.message.reply_text(channels_text)
async def channel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Kanallar bilan bog'liq callback query larni qayta ishlash"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "add_channel":
        await add_channel_command(update, context)
    elif query.data == "remove_channel":
        await remove_channel_command(update, context)
    elif query.data == "refresh_channels":
        await show_channels(update, context)
async def channel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Kanal callback query larini qayta ishlash"""
    query = update.callback_query
    await query.answer()
    
    if query.data.startswith('del_'):
        channel_id = query.data.replace('del_', '')
        
        if db.remove_channel(channel_id):
            # Yangilangan kanallar ro'yxatini ko'rsatish
            channels = db.get_channels()
            if channels:
                channels_text = "✅ Kanal o'chirildi!\n\n📢 Yangilangan kanallar ro'yxati:\n\n"
                for i, channel in enumerate(channels, 1):
                    channels_text += f"{i}. {channel['channel_name']}\n"
                    channels_text += f"└ {channel['channel_id']}\n\n"
            else:
                channels_text = "✅ Kanal o'chirildi!\n\n❌ Boshqa kanallar yo'q."
            
            await query.message.edit_text(channels_text)
        else:
            await query.message.edit_text("❌ Kanalni o'chirishda xatolik yuz berdi!")
async def check_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Foydalanuvchi kanallarga a'zo bo'lganini tekshirish"""
    user_id = update.effective_user.id
    channels = db.get_channels()

    # Agar oldin tekshirilgan bo‘lsa, qayta tekshirmaymiz
    if context.user_data.get("is_subscribed"):
        return True

    if not channels:
        return True  # Kanallar yo‘q bo‘lsa, tekshirish shart emas

    not_subscribed = []

    for channel in channels:
        chat_id = channel['channel_id']

        # Chat ID formatini to‘g‘ri shaklga keltirish
        if chat_id.startswith("@"):
            chat_id = chat_id[1:]

        try:
            # A'zolikni tekshirish
            member = await context.bot.get_chat_member(chat_id=f"@{chat_id}", user_id=user_id)

            if member.status not in ["member", "administrator", "creator"]:
                not_subscribed.append(channel)

        except error.BadRequest as e:
            logger.error(f"Kanal ({chat_id}) tekshirishda xato: {str(e)}")
            not_subscribed.append(channel)

    if not not_subscribed:
        # A’zolikni tasdiqlaymiz
        context.user_data["is_subscribed"] = True
        return True  

    # Agar foydalanuvchi hali a’zo bo‘lmasa, xabar chiqaramiz
    keyboard = [
        [InlineKeyboardButton(f"➕ {channel['channel_name']}", url=f"https://t.me/{channel['channel_id'].replace('@', '')}")]
        for channel in not_subscribed
    ]
    keyboard.append([InlineKeyboardButton("✅ A'zolikni tekshirish", callback_data="check_subscription")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "❗️ Quyidagi kanallarga a'zo bo'lishingiz kerak:\n\n" +
        "\n".join([f"📣 {channel['channel_name']}" for channel in not_subscribed]) +
        "\n\nA'zo bo'lgach, ✅ tekshirish tugmasini bosing.",
        reply_markup=reply_markup
    )
    return False



async def check_subscription_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Foydalanuvchi kanallarga a'zo bo'lganini qayta tekshirish"""
    query = update.callback_query
    user_id = query.from_user.id
    channels = db.get_channels()

    if not channels:
        await query.message.edit_text("✅ Siz barcha kanallarga a'zo bo'lgansiz!")
        return

    not_subscribed = []
    for channel in channels:
        try:
            chat_id = channel['channel_id']
            if chat_id.startswith("@"):
                chat_id = chat_id[1:]

            member = await context.bot.get_chat_member(chat_id=f"@{chat_id}", user_id=user_id)

            if member.status not in ["member", "administrator", "creator"]:
                not_subscribed.append(channel)
        except error.BadRequest as e:
            logger.error(f"Kanal ({chat_id}) tekshirishda xato: {str(e)}")
            not_subscribed.append(channel)

    if not not_subscribed:
        # Foydalanuvchi barcha kanallarga a'zo bo'lgan, natijani saqlaymiz
        context.user_data["is_subscribed"] = True
        await query.message.edit_text(
            "✅ Siz barcha kanallarga a'zo bo'lgansiz!\n"
            "Botdan foydalanishingiz mumkin."
        )
    else:
        # Hali ham a'zo bo'lmagan kanallar bor, tugmalarni yangilaymiz
        keyboard = [
            [InlineKeyboardButton(f"➕ {ch['channel_name']}", url=f"https://t.me/{ch['channel_id'].replace('@', '')}")]
            for ch in not_subscribed
        ]
        keyboard.append([InlineKeyboardButton("✅ A'zolikni tekshirish", callback_data="check_subscription")])
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.message.edit_text(
            "❗️ Hali quyidagi kanallarga a'zo bo'lmagansiz. A'zo bo'lib, tekshirish tugmasini bosing:",
            reply_markup=reply_markup
        )


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Tugmalar bosilganda ishga tushadi"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "check_subscription":
        is_subscribed = await check_subscription(update, context)
        if is_subscribed:
            await query.message.delete()
            await query.message.reply_text(
                "✅ Barcha kanallarga a'zo bo'ldingiz!\n"
                "Botdan foydalanishingiz mumkin."
            )
        else:
            await query.answer("❌ Siz hali barcha kanallarga a'zo bo'lmagansiz!", show_alert=True)
async def recognize_song(file_path: str) -> Optional[Dict[str, Any]]:
    """Qo'shiqni aniqlash"""
    print(f"🎵 Qo'shiqni aniqlash boshlandi: {file_path}")
    temp_audio_path = None
    
    try:
        # Video faylidan audio qismini ajratib olish
        temp_audio_path = file_path.rsplit('.', 1)[0] + '_temp.mp3'
        print(f"🎼 Audio ajratilmoqda: {temp_audio_path}")
        
        try:
            # FFmpeg orqali video dan audio ni ajratish
            command = [
                'ffmpeg', '-i', file_path,
                '-vn',  # Video ni o'chirish
                '-acodec', 'libmp3lame',  # MP3 formatga o'tkazish
                '-ac', '2',  # Stereo
                '-ab', '160k',  # Bitrate
                '-ar', '44100',  # Sample rate
                '-y',  # Mavjud faylni qayta yozish
                temp_audio_path
            ]
            
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            print(f"🔧 FFmpeg natijasi: {stderr.decode() if stderr else 'OK'}")
            
            if not os.path.exists(temp_audio_path):
                print("❌ Audio fayl yaratilmadi")
                raise Exception("Audio fayl yaratilmadi")
                
        except Exception as e:
            print(f"❌ Audio ajratishda xato: {str(e)}")
            return None

        # Shazam orqali qo'shiqni aniqlash
        print("🔍 Shazam orqali qo'shiq qidirilmoqda...")
        shazam = Shazam()
        try:
            result = await shazam.recognize_song(temp_audio_path)
            print(f"📝 Shazam natijasi: {result if result else "Natija yo'q"}")
            
            if not result:
                print("❌ Shazam natija qaytarmadi")
                return None
                
            if 'track' not in result:
                print("❌ Natijada track ma'lumoti yo'q")
                return None
                
            track = result['track']
            print(f"✅ Track topildi: {track.get('title', 'Noma\'lum')}")
            
            # Qo'shiq ma'lumotlarini qaytarish
            return {
                'title': track.get('title', 'Noma\'lum'),
                'artist': track.get('subtitle', 'Noma\'lum ijrochi'),
                'album': track.get('sections', [{}])[0].get('metadata', [{}])[0].get('text', 'Noma\'lum albom'),
                'genre': track.get('genres', {}).get('primary', 'Noma\'lum janr'),
                'release_date': track.get('sections', [{}])[0].get('metadata', [{}])[1].get('text', 'Noma\'lum sana'),
                'lyrics': track.get('sections', [{}])[1].get('text', 'Qo\'shiq so\'zlari topilmadi'),
                'url': track.get('url', None)
            }
            
        except Exception as e:
            print(f"❌ Shazam bilan aniqlashda xato: {str(e)}")
            return None
            
    except Exception as e:
        print(f"❌ Qo'shiqni aniqlashda umumiy xato: {str(e)}")
        return None
        
    finally:
        # Vaqtinchalik faylni tozalash
        if temp_audio_path and os.path.exists(temp_audio_path):
            try:
                os.remove(temp_audio_path)
                print("🗑 Vaqtinchalik audio fayl o'chirildi")
            except Exception as e:
                print(f"❌ Vaqtinchalik faylni o'chirishda xato: {str(e)}")
def search_song_shazam(song_name):
    url = "https://shazam.p.rapidapi.com/search"
    querystring = {"term": song_name, "locale": "en-US", "offset": "0", "limit": "1"}

    headers = {
        "X-RapidAPI-Key": "e0d33af256msh9f0b1ebf978c0bbp1c9880jsnfeab1b6ac794",  # RapidAPI'dan kalitingizni qo'ying
        "X-RapidAPI-Host": "shazam.p.rapidapi.com"
    }

    response = requests.get(url, headers=headers, params=querystring)

    if response.status_code == 200:
        data = response.json()
        
        if "tracks" in data and "hits" in data["tracks"]:
            track = data["tracks"]["hits"][0]["track"]
            title = track["title"]
            subtitle = track["subtitle"]
            song_url = track.get("url", "Lyrics mavjud emas")

            result = f"🎵 {title} - {subtitle}\n🔗 Lyrics: {song_url}"
            return result
        else:
            return "❌ Qo‘shiq topilmadi."
    else:
        return "❌ API bilan bog‘lanishda xatolik yuz berdi."

# Foydalanuvchi qo‘shiq nomini yuborganda ishga tushadigan funksiya
async def handle_song_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    song_name = update.message.text
    result = search_song_shazam(song_name)
    await update.message.reply_text(result)

async def download_full_song(song_info: Dict[str, str]) -> Optional[Dict[str, str]]:
    """Qo'shiqni to'liq formatda qidirib topish va yuklash"""
    try:
        # Qo'shiq qidiruv so'rovi
        search_query = f"{song_info['artist']} - {song_info['title']} audio"
        
        # yt-dlp sozlamalari
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': f'{DOWNLOADS_DIR}/%(title)s.%(ext)s',
            'quiet': True,
            'no_warnings': True,
            'extract_flat': True,
            'default_search': 'ytsearch',
            # Audio sifati va hajmini optimallashtirish
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192', # 320 o'rniga 192 ishlatamiz
            }, {
                'key': 'FFmpegMetadata',
                'add_metadata': True,
            }],
            # Maksimal hajm (50MB)
            'max_filesize': 50 * 1024 * 1024,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # Qidirish
            result = ydl.extract_info(f"ytsearch1:{search_query}", download=False)
            if 'entries' in result and result['entries']:
                # Birinchi natijani yuklash
                info = ydl.extract_info(result['entries'][0]['url'], download=True)
                audio_path = ydl.prepare_filename(info).rsplit('.', 1)[0] + '.mp3'
                
                # Fayl hajmini tekshirish
                if os.path.exists(audio_path) and os.path.getsize(audio_path) < 50 * 1024 * 1024:
                    return {
                        'title': info['title'],
                        'artist': song_info['artist'],
                        'audio_path': audio_path,
                        'duration': info.get('duration', 0),
                        'url': info.get('webpage_url', ''),
                        'thumbnail': info.get('thumbnail', '')
                    }
                else:
                    # Fayl hajmi katta bo'lsa, uni o'chirib, None qaytarish
                    if os.path.exists(audio_path):
                        os.remove(audio_path)
                    return None
        
        return None
    except Exception as e:
        logger.error(f"Qo'shiqni yuklashda xato: {str(e)}")
        return None

def extract_video_id(url: str) -> str:
    """YouTube URL dan video ID ni olish"""
    try:
        # URL dan bo'sh joylarni tozalash
        url = url.strip()
        
        # YouTube video ID patterns
        patterns = [
            r'(?:v=|v/|embed/|youtu.be/)([^#&?]*)',
            r'(?:watch\?v=)([^#&?]*)',
            r'(?:embed/)([^#&?]*)',
            r'(?:shorts/)([^#&?]*)',
            r'(?:v/)([^#&?]*)',
            r'(?:youtu.be/)([^#&?]*)'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                video_id = match.group(1)
                if video_id:
                    return video_id
                    
        return None
        
    except Exception as e:
        logger.error(f"Video ID ni ajratishda xatolik: {str(e)}")
        return None

async def download_video_with_quality(url: str, quality: str) -> dict:
    """Foydalanuvchi tanlagan sifat bo'yicha YouTube videosini yuklab olish"""
    
    # downloads papkasini yaratish
    if not os.path.exists('downloads'):
        os.makedirs('downloads')
    
    quality_map = {
        "480p": {"format": "bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/best[height<=480][ext=mp4]"},
        "720p": {"format": "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]"},
        "1080p": {"format": "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080][ext=mp4]"},
    }

    ydl_opts = {
        **quality_map.get(quality, {"format": "best"}),
        'outtmpl': 'downloads/%(title)s.%(ext)s',
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True,
        'merge_output_format': 'mp4',
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            video_path = ydl.prepare_filename(info)
            
            # Agar fayl kengaytmasi webm bo'lsa, mp4 ga o'zgartiramiz
            if video_path.endswith('.webm'):
                new_path = video_path.rsplit('.', 1)[0] + '.mp4'
                if os.path.exists(new_path):
                    video_path = new_path

            if os.path.exists(video_path):
                return {
                    'title': info.get('title', 'Noma\'lum video'),
                    'video_path': video_path,
                    'duration': info.get('duration'),
                    'format': quality
                }
    except Exception as e:
        logger.error(f"Video yuklab olishda xatolik: {str(e)}")
        return None

    return None

async def ask_video_quality(update: Update, context: ContextTypes.DEFAULT_TYPE, video_url: str) -> None:
    """Foydalanuvchiga yuklab olish sifati uchun tugmalar chiqarish"""
    video_id = extract_video_id(video_url)
    print(f"🎯 Video sifati tanlash uchun video ID: {video_id}")  # Debug uchun
    
    if not video_id:
        await update.message.reply_text("❌ YouTube link noto'g'ri!")
        return

    keyboard = [
        [
            InlineKeyboardButton("480p", callback_data=f"quality_480p_{video_id}"),
            InlineKeyboardButton("720p", callback_data=f"quality_720p_{video_id}"),
            InlineKeyboardButton("1080p", callback_data=f"quality_1080p_{video_id}")
        ]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "📹 Yuklab olish sifatini tanlang:\n"
        "⚠️ Yuqori sifat = Katta hajm = Uzoqroq kutish",
        reply_markup=reply_markup
    )

async def quality_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Foydalanuvchi tanlagan sifat bo'yicha video yuklab olish"""
    query = update.callback_query
    await query.answer()

    try:
        # Format: quality_480p_videoId
        data = query.data.split("_", 2)  # Split into maximum 3 parts
        if len(data) != 3:
            await query.message.reply_text("❌ Noto'g'ri ma'lumot formati")
            return

        quality = data[1]  # 480p, 720p, 1080p
        video_id = data[2]  # Full video ID
        
        print(f"🎥 Tanlangan sifat: {quality}")
        print(f"🆔 Ishlov berilayotgan video ID: {video_id}")
        
        # Video ID uzunligini tekshirish (YouTube ID odatda 11 belgidan iborat)
        if not video_id:
            await query.message.reply_text(
                "❌ Video ID topilmadi.\n"
                "Iltimos, videoni qayta yuboring."
            )
            return
            
        video_url = f"https://www.youtube.com/watch?v={video_id}"
        print(f"🔗 Yuklanayotgan URL: {video_url}")

        # Progress xabarini yuborish
        progress_message = await query.message.reply_text(
            f"⏳ Video {quality} sifatida yuklanmoqda...\n"
            "⚠️ Bu bir necha daqiqa vaqt olishi mumkin."
        )

        # Videoni yuklash
        video_info = await download_video_with_quality(video_url, quality)
        
        if video_info and os.path.exists(video_info['video_path']):
            # Video hajmini tekshirish (50MB limit)
            file_size = os.path.getsize(video_info['video_path'])
            
            if file_size <= 50 * 1024 * 1024:  # 50MB limit
                async with aiofiles.open(video_info['video_path'], 'rb') as video_file:
                    await query.message.reply_video(
                        video=await video_file.read(),
                        caption=f"🎥 {video_info['title']} ({quality})\n"
                                f"🎮 Yuklab olindi",
                        supports_streaming=True,
                        filename=os.path.basename(video_info['video_path']),
                        read_timeout=60,
                        write_timeout=60,
                        connect_timeout=60,
                    )
                await progress_message.delete()
            else:
                await progress_message.edit_text(
                    "⚠️ Video hajmi juda katta (50MB dan oshiq). "
                    "Iltimos, pastroq sifatni tanlang."
                )
            
            # Yuklab olingan faylni o'chirish
            try:
                os.remove(video_info['video_path'])
            except Exception as e:
                logger.error(f"Faylni o'chirishda xatolik: {str(e)}")
        else:
            await progress_message.edit_text(
                "❌ Video yuklab olishda xatolik yuz berdi.\n"
                "Iltimos, qaytadan urinib ko'ring."
            )

    except Exception as e:
        logger.error(f"Callback handler xatoligi: {str(e)}")
        await query.message.reply_text(
            "❌ Xatolik yuz berdi. Iltimos, qaytadan urinib ko'ring."
        )

async def download_video(url: str) -> dict:
    """Instagram videosini yuklash"""
    ydl_opts = {
        'format': 'best',
        'outtmpl': 'downloads/%(title)s.%(ext)s',
        'quiet': True,
        'no_warnings': True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            video_path = ydl.prepare_filename(info)
            
            if os.path.exists(video_path):
                return {
                    'title': info.get('title', 'Instagram video'),
                    'video_path': video_path
                }
    except Exception as e:
        logger.error(f"Instagram video yuklab olishda xatolik: {str(e)}")
        return None

    return None
async def process_video(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """YouTube va Instagram videolarini yuklab olish"""
    message = await update.message.reply_text("⏳ Video yuklanmoqda...")
    audio_path = None
    video_info = None
    full_song = None
    original_url = update.message.text.strip()
    
    print(f"📥 Olingan URL: {original_url}")
    
    try:
        # YouTube videosi bo'lsa
        if "youtube.com" in original_url or "youtu.be" in original_url:
            # URL dan video ID ni ajratib olish
            video_id = extract_video_id(original_url)
            
            print(f"📌 Ajratilgan video ID: {video_id}")
            
            if not video_id:
                await message.edit_text(
                    "❌ Noto'g'ri YouTube URL.\n"
                    "Iltimos, to'g'ri linkni yuboring.\n"
                    "Masalan: https://www.youtube.com/watch?v=VIDEO_ID"
                )
                return
                
            # Tozalangan URL ni yaratish
            clean_url = f"https://www.youtube.com/watch?v={video_id}"
            print(f"🔗 Tozalangan URL: {clean_url}")
            
            await message.edit_text("📹 YouTube videolari uchun sifatni tanlang:")
            await ask_video_quality(update, context, clean_url)
            return

        # Instagram video bo'lsa
        elif "instagram.com" in original_url:
            if "/reel/" in original_url or "/p/" in original_url:
                video_info = await download_video(original_url)
                
                if not video_info:
                    await message.edit_text(
                        "❌ Video yuklab olishda xatolik yuz berdi.\n"
                        "Sabablari:\n"
                        "1. Video mavjud emas\n"
                        "2. Post yopiq profilda\n"
                        "3. Link noto'g'ri\n"
                    )
                    return

                # Video hajmini tekshirish
                if os.path.exists(video_info['video_path']):
                    file_size = os.path.getsize(video_info['video_path'])
                    if file_size > 2000 * 1024 * 1024:  
                        await message.edit_text(
                            "⚠️ Video hajmi juda katta (2000MB dan oshiq).\n"
                            "Telegram botlari 2000MB dan katta fayllarni yubora olmaydi."
                        )
                        # Faylni tozalash
                        cleanup_files(video_info['video_path'])
                        return

                    # Videoni yuborish
                    try:
                        await message.edit_text("📤 Video yuborilmoqda...")
                        async with aiofiles.open(video_info['video_path'], 'rb') as video_file:
                            sent_video = await update.message.reply_video(
                                video=await video_file.read(),
                                caption=f"📱 Instagram video\n🔗 {original_url}",
                                supports_streaming=True,
                                filename=os.path.basename(video_info['video_path']),
                                read_timeout=60,
                                write_timeout=60,
                                connect_timeout=60,
                            )
                        # Qo'shiq topish tugmasini qo'shish
                        video_filename = os.path.basename(video_info['video_path'])
                        keyboard = [[InlineKeyboardButton(
                            "🎵 Qo'shiqni to'liq versiyasini topish",
                            callback_data=f"find_song_{video_filename}"
                        )]]
                        reply_markup = InlineKeyboardMarkup(keyboard)
                        
                        await sent_video.reply_text(
                            "Videodagi qo'shiqni to'liq versiyasini topishni xohlasangiz, "
                            "quyidagi tugmani bosing:",
                            reply_markup=reply_markup
                        )
                        
                        # Muvaffaqiyatli yuklab olingani haqida xabar
                        await message.delete()
                        
                    except Exception as e:
                        logger.error(f"Video yuborishda xatolik: {str(e)}")
                        await message.edit_text(
                            "❌ Video yuborishda xatolik yuz berdi.\n"
                            "Iltimos, qaytadan urinib ko'ring."
                        )
                    finally:
                        # Faylni tozalash
                        cleanup_files(video_info['video_path'])
                else:
                    await message.edit_text(
                        "❌ Video fayli topilmadi.\n"
                        "Iltimos, qaytadan urinib ko'ring."
                    )
            else:
                await message.edit_text(
                    "❌ Noto'g'ri Instagram link.\n"
                    "Faqat Reels yoki Post linklar qo'llab-quvvatlanadi."
                )
        
        # TikTok video bo'lsa
        elif "tiktok.com" in original_url:
            await message.edit_text(
                "ℹ️ TikTok videolari hozircha qo'llab-quvvatlanmaydi."
            )
            
        else:
            await message.edit_text(
                "❌ Noto'g'ri link formati.\n"
                "Bot qo'llab-quvvatlaydigan platformalar:\n"
                "✅ YouTube\n"
                "✅ Instagram (Reels/Posts)\n"
            )
            
    except Exception as e:
        error_message = str(e)
        logger.error(f"Asosiy jarayonda xato: {error_message}")
        
        # Foydalanuvchiga tushunarli xato xabarini yuborish
        if "URL blocked" in error_message:
            await message.edit_text(
                "❌ Bu video yuklab olish uchun bloklangan.\n"
                "Boshqa video linkini yuboring."
            )
        elif "Private video" in error_message:
            await message.edit_text(
                "❌ Bu yopiq (private) video.\n"
                "Faqat ochiq videolarni yuklab olish mumkin."
            )
        elif "sign URL" in error_message:
            await message.edit_text(
                "❌ Video mavjud emas yoki o'chirilgan."
            )
        else:
            await message.edit_text(
                "❌ Xatolik yuz berdi.\n"
                "Iltimos, qaytadan urinib ko'ring yoki boshqa link yuboring."
            )
    
    finally:
        # Vaqtinchalik fayllarni tozalash
        try:
            if video_info and 'video_path' in video_info:
                if os.path.exists(video_info['video_path']):
                    os.remove(video_info['video_path'])
            if audio_path and os.path.exists(audio_path):
                os.remove(audio_path)
            if full_song and 'audio_path' in full_song:
                if os.path.exists(full_song['audio_path']):
                    os.remove(full_song['audio_path'])
        except Exception as e:
            logger.error(f"Fayllarni tozalashda xatolik: {str(e)}")

async def find_song_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    
    print("🎵 Qo'shiq topish funksiyasi boshlandi")
    print(f"👤 Foydalanuvchi: {update.effective_user.id}")
    
    try:
        # Callback data dan video message ID ni olish
        _, message_id = query.data.split('_')
        message_id = int(message_id)
        
        # Context dan video ma'lumotlarini olish
        video_data = context.user_data.get(f'video_{message_id}')
        
        if not video_data:
            print("❌ Video ma'lumotlari topilmadi")
            await query.message.reply_text(
                "❌ Video ma'lumotlari topilmadi.\n"
                "Iltimos, videoni qayta yuboring."
            )
            return
            
        # Status xabarini yuborish
        status_message = await query.message.reply_text("⏳ Video qayta yuklanmoqda...")
        
        try:
            # Video faylini yuklab olish
            file = await context.bot.get_file(video_data['file_id'])
            temp_video_path = os.path.join(DOWNLOADS_DIR, f"temp_video_{int(time.time())}.mp4")
            
            await file.download_to_drive(temp_video_path)
            print(f"📁 Video yuklandi: {temp_video_path}")
            
            if not os.path.exists(temp_video_path):
                raise FileNotFoundError("Video fayli yuklanmadi")
            
            await status_message.edit_text("🔍 Qo'shiq aniqlanmoqda...")
            
            # Qo'shiqni aniqlash
            song_info = await recognize_song(temp_video_path)
            
            if not song_info:
                await status_message.edit_text(
                    "❌ Qo'shiq aniqlanmadi.\n"
                    "Sabablari:\n"
                    "1. Video da qo'shiq yo'q\n"
                    "2. Qo'shiq sifati past\n"
                    "3. Qo'shiq bazada mavjud emas"
                )
                return
            
            # Qo'shiq haqida ma'lumot
            song_details = (
                f"🎵 Qo'shiq topildi!\n\n"
                f"📌 Nomi: {song_info['title']}\n"
                f"👤 Ijrochi: {song_info['artist']}\n"
            )
            
            if song_info.get('album'):
                song_details += f"💽 Albom: {song_info['album']}\n"
            if song_info.get('genre'):
                song_details += f"🎼 Janr: {song_info['genre']}\n"
            
            await status_message.edit_text(f"{song_details}\n⏳ To'liq versiya yuklanmoqda...")
            
            # YouTube dan qo'shiqni qidirish va yuklash
            search_query = f"{song_info['artist']} - {song_info['title']} audio"
            downloaded_song = await download_song_from_youtube(search_query, DOWNLOADS_DIR)
            
            if not downloaded_song:
                await status_message.edit_text(
                    f"{song_details}\n❌ Qo'shiqning to'liq versiyasini yuklab olishda xatolik yuz berdi."
                )
                return
            
            # Qo'shiqni yuborish
            async with aiofiles.open(downloaded_song['audio_path'], 'rb') as audio_file:
                await query.message.reply_audio(
                    audio=await audio_file.read(),
                    caption=f"🎵 {song_info['title']} - {song_info['artist']}\n"
                           f"🎼 To'liq versiya",
                    title=song_info['title'][:64],
                    performer=song_info['artist'][:64],
                    duration=downloaded_song.get('duration'),
                    filename=f"{song_info['title'][:32]}.mp3"
                )
            await status_message.delete()
            
        except Exception as e:
            print(f"❌ Xatolik: {str(e)}")
            await status_message.edit_text(
                "❌ Xatolik yuz berdi.\n"
                "Iltimos, qaytadan urinib ko'ring."
            )
        finally:
            # Fayllarni tozalash
            cleanup_files(temp_video_path)
            if 'downloaded_song' in locals() and downloaded_song and 'audio_path' in downloaded_song:
                cleanup_files(downloaded_song['audio_path'])
            
    except Exception as e:
        print(f"❌ Umumiy xatolik: {str(e)}")
        await query.message.reply_text(
            "❌ Xatolik yuz berdi.\n"
            "Iltimos, qaytadan urinib ko'ring."
        )
async def download_song_from_youtube(search_query: str, output_dir: str) -> Optional[Dict[str, Any]]:
    """YouTube orqali qo'shiqni yuklab olish"""
    try:
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': f'{output_dir}/%(title)s.%(ext)s',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',  # Audio sifatini pasaytirish
            }, {
                'key': 'FFmpegMetadata',
                'add_metadata': True,
            }],
            'quiet': True,
            'no_warnings': True,
            'extract_flat': True,
            'default_search': 'ytsearch',
            'max_filesize': 50 * 1024 * 1024,  # 50MB limit
            'noplaylist': True,  # Playlist emas, bitta qo'shiq
            'prefer_ffmpeg': True,
            'cachedir': False,  # Keshni o'chirish
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # Qo'shiqni qidirish
            search_results = ydl.extract_info(f"ytsearch1:{search_query}", download=False)
            
            if not search_results.get('entries'):
                return None
                
            # Birinchi natijani olish
            video_info = search_results['entries'][0]
            
            # Davomiylikni tekshirish (10 daqiqadan oshmasligi kerak)
            if video_info.get('duration', 0) > 600: 
                return None
                
            # Qo'shiqni yuklash
            info = ydl.extract_info(video_info['id'], download=True)
            
            if not info:
                return None
                
            # Yuklangan fayl yo'lini olish
            audio_path = ydl.prepare_filename(info).rsplit('.', 1)[0] + '.mp3'
            
            if not os.path.exists(audio_path):
                return None
                
            return {
                'title': info.get('title', 'Unknown'),
                'artist': info.get('artist', info.get('uploader', 'Unknown Artist')),
                'audio_path': audio_path,
                'duration': info.get('duration'),
                'thumbnail': info.get('thumbnail'),
            }
            
    except Exception as e:
        logger.error(f"Qo'shiqni yuklashda xato: {str(e)}")
        return None

async def handle_music_recognition(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Musiqani aniqlash va yuklash"""
    message = await update.message.reply_text("🎵 Musiqa aniqlanmoqda...")
    
    try:
        # Foydalanuvchi yuborgan audio faylni olish
        audio_file = None
        
        if update.message.voice:
            file = await context.bot.get_file(update.message.voice.file_id)
            audio_file = f"{DOWNLOADS_DIR}/voice_{update.message.voice.file_id}.ogg"
            await file.download_to_drive(audio_file)
        
        elif update.message.audio:
            file = await context.bot.get_file(update.message.audio.file_id)
            audio_file = f"{DOWNLOADS_DIR}/audio_{update.message.audio.file_id}.mp3"
            await file.download_to_drive(audio_file)
            
        if not audio_file:
            await message.edit_text(
                "❌ Audio fayl topilmadi!\n"
                "Iltimos, ovozli xabar yoki audio fayl yuboring."
            )
            return

        # Shazam orqali qo'shiqni aniqlash
        await message.edit_text("🔍 Qo'shiq izlanmoqda...")
        song_info = await recognize_song(audio_file)
        
        if not song_info:
            await message.edit_text(
                "❌ Qo'shiq aniqlanmadi.\n"
                "Iltimos, aniqroq audio yuborib ko'ring."
            )
            cleanup_files(audio_file)
            return

        # Qo'shiq haqida ma'lumot
        song_details = (
            f"🎵 Topildi!\n\n"
            f"📌 Nomi: {song_info['title']}\n"
            f"👤 Ijrochi: {song_info['artist']}\n"
        )
        
        if song_info.get('album'):
            song_details += f"💽 Albom: {song_info['album']}\n"
        if song_info.get('genre'):
            song_details += f"🎼 Janr: {song_info['genre']}\n"
            
        await message.edit_text(f"{song_details}\n⏳ Yuklanmoqda...")

        # Qo'shiqni YouTube dan yuklash
        search_query = f"{song_info['artist']} - {song_info['title']} audio"
        downloaded_song = await download_song_from_youtube(search_query, DOWNLOADS_DIR)
        
        if not downloaded_song:
            await message.edit_text(
                f"{song_details}\n❌ Qo'shiqni yuklab olishda xatolik yuz berdi."
            )
            cleanup_files(audio_file)
            return

        # Qo'shiq ma'lumotlarini tayyorlash
        caption = (
            f"🎵 {song_info['title']}\n"
            f"👤 {song_info['artist']}\n"
        )
        
        if downloaded_song.get('duration'):
            minutes = downloaded_song['duration'] // 60
            seconds = downloaded_song['duration'] % 60
            caption += f"⏱ Davomiyligi: {minutes}:{seconds:02d}\n"
            
        if song_info.get('lyrics'):
            lyrics = song_info['lyrics']
            if len(lyrics) > 500:
                lyrics = lyrics[:497] + "..."
            caption += f"\n📝 Qo'shiq so'zlari:\n{lyrics}"

        # Qo'shiqni yuborish
        try:
            async with aiofiles.open(downloaded_song['audio_path'], 'rb') as audio_file:
                await update.message.reply_audio(
                    audio=await audio_file.read(),
                    caption=caption,
                    title=song_info['title'],
                    performer=song_info['artist'],
                    duration=downloaded_song.get('duration'),
                    filename=f"{song_info['title']}.mp3",
                    thumb=downloaded_song.get('thumbnail'),
                )
            await message.delete()
            
        except Exception as e:
            logger.error(f"Qo'shiqni yuborishda xato: {str(e)}")
            await message.edit_text(
                f"{song_details}\n❌ Qo'shiqni yuborishda xatolik yuz berdi."
            )
            
    except Exception as e:
        logger.error(f"Musiqa aniqlashda xato: {str(e)}")
        await message.edit_text(
            "❌ Xatolik yuz berdi.\n"
            "Iltimos, qaytadan urinib ko'ring."
        )
        
    finally:
        # Fayllarni tozalash
        try:
            if 'audio_file' in locals() and audio_file:
                cleanup_files(audio_file)
            if 'downloaded_song' in locals() and downloaded_song:
                if 'audio_path' in downloaded_song and os.path.exists(downloaded_song['audio_path']):
                    cleanup_files(downloaded_song['audio_path'])
        except Exception as e:
            logger.error(f"Fayllarni tozalashda xato: {str(e)}")

async def download_video(url: str) -> Optional[Dict[str, str]]:
    """Videoni yuklab olish"""
    try:
        # Agar Instagram link bo'lsa
        if 'instagram.com' in url:
            try:
                # yt-dlp sozlamalari
                ydl_opts = {
                    'format': 'best',
                    'outtmpl': f'{DOWNLOADS_DIR}/%(title)s.%(ext)s',
                    'quiet': True,
                    'no_warnings': True,
                    'no_check_certificate': True,
                    'nocheckcertificate': True,
                    # Instagram uchun qo'shimcha sozlamalar
                    'extract_flat': True,
                    'ignoreerrors': True,
                    # Instagram uchun header
                    'http_headers': {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                        'Accept-Language': 'en-us,en;q=0.5',
                        'Sec-Fetch-Mode': 'navigate',
                    }
                }
                
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=True)
                    video_path = ydl.prepare_filename(info)
                    
                    if os.path.exists(video_path):
                        return {
                            'title': info.get('title', 'Instagram Video'),
                            'video_path': video_path
                        }
                    
            except Exception as e:
                logger.error(f"yt-dlp bilan yuklab olishda xato: {str(e)}")
                
                # yt-dlp ishlamasa Instaloader bilan urinib ko'ramiz
                L = instaloader.Instaloader(
                    dirname_pattern=DOWNLOADS_DIR,
                    download_videos=True,
                    download_video_thumbnails=False,
                    save_metadata=False,
                    verify_ssl=False,
                    quiet=True
                )
                
                post_id = url.split('/')[-2]
                post = Post.from_shortcode(L.context, post_id)
                L.download_post(post, target=DOWNLOADS_DIR)
                
                # Video faylini topish
                for file in os.listdir(DOWNLOADS_DIR):
                    if file.endswith('.mp4') and post_id in file:
                        video_path = os.path.join(DOWNLOADS_DIR, file)
                        if os.path.exists(video_path):
                            return {
                                'title': f'Instagram Video {post_id}',
                                'video_path': video_path
                            }
                
                raise Exception("Video fayli topilmadi")
                
        # YouTube va boshqa platformalar uchun
        else:
            ydl_opts = {
                'format': 'best',
                'outtmpl': f'{DOWNLOADS_DIR}/%(title)s.%(ext)s',
                'quiet': True,
                'no_warnings': True,
                'no_check_certificate': True,
                'nocheckcertificate': True,
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                video_path = ydl.prepare_filename(info)
                
                if os.path.exists(video_path):
                    return {
                        'title': info['title'],
                        'video_path': video_path
                    }
                else:
                    raise Exception("Video fayli topilmadi")
                    
    except Exception as e:
        logger.error(f"Video yuklab olishda xato: {str(e)}")
        return None
async def extract_audio(video_path: str) -> Optional[str]:
    """Videodan audioni ajratib olish"""
    try:
        audio_path = video_path.rsplit('.', 1)[0] + '.mp3'
        audio = AudioSegment.from_file(video_path)
        audio.export(audio_path, format='mp3')
        return audio_path
    except Exception as e:
        logger.error(f"Audio ajratishda xato: {str(e)}")
        return None
# Callback query handler qo'shamiz

async def add_channel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Kanal ma'lumotlarini qo'shish"""
    try:
        channel_id, channel_name = update.message.text.split('|')
        channel_id = channel_id.strip()
        channel_name = channel_name.strip()
        
        if db.add_channel(channel_id, channel_name):
            await update.message.reply_text(f"✅ Kanal muvaffaqiyatli qo'shildi!")
        else:
            await update.message.reply_text("❌ Kanal qo'shishda xatolik yuz berdi")
    except Exception as e:
        await update.message.reply_text("❌ Noto'g'ri format. Qaytadan urinib ko'ring.")
        logger.error(f"Kanal qo'shishda xato: {str(e)}")
    
    return ConversationHandler.END


async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Xabar yuborish boshlash"""
    if not is_admin(update):
        await update.message.reply_text("❌ Bu buyruq faqat admin uchun!")
        return ConversationHandler.END
    
    await update.message.reply_text(
        "📝 Barcha foydalanuvchilarga yuboriladigan xabarni kiriting:\n"
        "Bekor qilish uchun /cancel buyrug'ini yuboring."
    )
    return BROADCAST

async def broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Xabarni barcha foydalanuvchilarga yuborish"""
    message = update.message.text
    users = db.get_all_users()
    
    progress_msg = await update.message.reply_text("📤 Xabar yuborilmoqda...")
    success = 0
    failed = 0
    
    for user in users:
        try:
            await context.bot.send_message(
                chat_id=user['user_id'],
                text=message,
                parse_mode='HTML'
            )
            success += 1
        except Exception as e:
            failed += 1
            logger.error(f"Xabar yuborishda xato {user['user_id']}: {str(e)}")
    
    await progress_msg.edit_text(
        f"✅ Xabar yuborish yakunlandi:\n"
        f"✓ Muvaffaqiyatli: {success}\n"
        f"❌ Muvaffaqiyatsiz: {failed}"
    )
    return ConversationHandler.END

async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Bot sozlamalari"""
    if not is_admin(update):
        await update.message.reply_text("❌ Bu buyruq faqat admin uchun!")
        return
    
    keyboard = [
        [InlineKeyboardButton("🔄 Botni qayta ishga tushirish", callback_data="restart_bot")],
        [InlineKeyboardButton("🗑 Cache ni tozalash", callback_data="clear_cache")],
        [InlineKeyboardButton("📊 Batafsil statistika", callback_data="detailed_stats")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "⚙️ Bot sozlamalari:\n"
        "Quyidagi amallardan birini tanlang:",
        reply_markup=reply_markup
    )



# Asosiy message handler ni yangilash
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Xabarlarni qayta ishlash"""
    
    # Avval kanal a'zoligini tekshirish
    if not await check_subscription(update, context):
        return
        
    text = update.message.text
    user_state = context.user_data.get('state', '')
    
    # Admin autentifikatsiya jarayonida bo'lsa
    if context.user_data.get('authenticating'):
        return
    
    # Admin panel
    if context.user_data.get('is_admin'):
        if text == "◀️ Asosiy menyu":
            context.user_data['is_admin'] = False
            await update.message.reply_text(
                "Asosiy menyuga qaytdingiz.",
                reply_markup=get_main_keyboard()
            )
            return
        elif text == "📊 Statistika":
            await show_statistics(update, context)
            return
        elif text == "📋 Kanallar ro'yxati":
            await show_channels(update, context)
            return
        elif text == "➕ Kanal qo'shish":
            await add_channel_command(update, context)
            return
        elif text == "➖ Kanal o'chirish":
            await remove_channel_command(update, context)
            return
        elif text == "📝 Xabar yuborish":
            await broadcast_command(update, context)
            return
        elif text == "⚙️ Sozlamalar":
            await settings_command(update, context)
            return
        return
            
    # Kategoriya tanlash
    if text == "🎵 Qo'shiq izlash":
        context.user_data['state'] = 'search_song'
        await update.message.reply_text(
            "🎵 Qo'shiq nomini yoki ijrochisini yozing:",
            reply_markup=ReplyKeyboardMarkup([["◀️ Orqaga"]], resize_keyboard=True)
        )
        return
        
    elif text == "🎬 YouTube":
        context.user_data['state'] = 'youtube'
        await update.message.reply_text(
            "🎬 YouTube video linkini yuboring:",
            reply_markup=ReplyKeyboardMarkup([["◀️ Orqaga"]], resize_keyboard=True)
        )
        return
        
    elif text == "📸 Instagram":
        context.user_data['state'] = 'instagram'
        await update.message.reply_text(
            "📸 Instagram post linkini yuboring:",
            reply_markup=ReplyKeyboardMarkup([["◀️ Orqaga"]], resize_keyboard=True)
        )
        return
        
    elif text == "◀️ Orqaga":
        context.user_data['state'] = ''
        await update.message.reply_text(
            "Asosiy menyu:",
            reply_markup=get_main_keyboard()
        )
        return
        
    # State ga qarab ishlov berish
    if user_state == 'search_song':
        await search_and_show_results(update, context)
        
    elif user_state == 'youtube':
        if "youtube.com" in text or "youtu.be" in text:
            await process_video(update, context)
        else:
            await update.message.reply_text(
                "❌ Noto'g'ri format! YouTube video linkini yuboring."
            )
            
    elif user_state == 'instagram':
        if "instagram.com" in text:
            await process_video(update, context)
        else:
            await update.message.reply_text(
                "❌ Noto'g'ri format! Instagram post linkini yuboring."
            )
    
    else:
        await update.message.reply_text(
            "Iltimos, quyidagi bo'limlardan birini tanlang:",
            reply_markup=get_main_keyboard()
        )

async def get_audio_size(video_id: str) -> float:
    """Aniq audio fayl hajmini olish"""
    try:
        ydl_opts = {
            'format': 'bestaudio',
            'quiet': True,
            'no_warnings': True
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: ydl.extract_info(f"https://youtube.com/watch?v={video_id}", download=False)
            )
            
            # Audio formatini topish
            for f in info['formats']:
                if f.get('acodec') != 'none' and f.get('vcodec') == 'none':
                    filesize = f.get('filesize', 0)
                    if filesize:
                        return round(filesize / (1024 * 1024), 1)  # MB ga o'tkazish
            
            # Agar aniq hajm topilmasa, davomiylikka qarab taxminiy hisoblash
            duration = info.get('duration', 0)
            return round((duration / 60) * 2.4, 1)  # 192kbps ≈ 2.4 MB/min
            
    except Exception as e:
        logger.error(f"Fayl hajmini olishda xato: {str(e)}")
        return 0

async def search_youtube(query: str, offset: int = 0) -> List[Dict]:
    """YouTube da qo'shiqlarni qidirish - 10 tadan dinamik"""
    try:
        ydl_opts = {
            'format': 'bestaudio',
            'quiet': True,
            'no_warnings': True,
            'noplaylist': True,
            'extract_flat': True,
            'skip_download': True,
            'playliststart': offset + 1,
            'playlistend': offset + 10
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            results = await asyncio.get_event_loop().run_in_executor(
                None, 
                lambda: ydl.extract_info(f"ytsearch{offset + 10}:{query}", download=False)
            )
            
            if not results or 'entries' not in results:
                return []
            
            songs = []
            for video in results['entries']:
                if not video:
                    continue
                
                duration = video.get('duration', 0)
                duration_str = f"{int(duration // 60)}:{int(duration % 60):02d}"
                
                filesize = round((duration / 60) * 2.4, 1)
                views = format_view_count(video.get('view_count', 0))
                
                title = video.get('title', '').replace(' (Official Video)', '')\
                                            .replace(' (Lyrics)', '')\
                                            .replace(' [Official Video]', '')\
                                            .replace(' (Audio)', '')
                
                songs.append({
                    'id': video.get('id', ''),
                    'title': title,
                    'duration': duration_str,
                    'filesize_mb': filesize,
                    'views': views
                })
            
            return songs
            
    except Exception as e:
        logger.error(f"YouTube qidirishda xato: {str(e)}")
        return []

def create_results_message(songs: List[Dict], page: int, query: str, has_more: bool = True) -> tuple:
    """Natijalar xabarini va tugmalarini yaratish"""
    message_text = f"🔍 {query}\nРезультаты {page*10 + 1}-{page*10 + len(songs)}\n\n"
    
    for idx, song in enumerate(songs, start=page*10 + 1):
        message_text += (
            f"{idx}. {song['title']} {song['duration']} {song['views']} {song['filesize_mb']}MB\n"
        )
    
    # Tugmalar (5 tadan 2 qator)
    keyboard = []
    number_buttons = []
    
    for idx in range(len(songs)):
        number_buttons.append(
            InlineKeyboardButton(str(idx + page*10 + 1), callback_data=f"song_{songs[idx]['id']}")
        )
        if len(number_buttons) == 5:
            keyboard.append(number_buttons)
            number_buttons = []
    if number_buttons:
        keyboard.append(number_buttons)
    
    # Navigatsiya tugmalari
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️", callback_data=f"page_{page-1}"))
    nav_buttons.append(InlineKeyboardButton("❌", callback_data="cancel_search"))
    if has_more:
        nav_buttons.append(InlineKeyboardButton("➡️", callback_data=f"page_{page+1}"))
    
    keyboard.append(nav_buttons)
    
    return message_text, InlineKeyboardMarkup(keyboard)

async def search_and_show_results(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Qo'shiqlarni qidirish va natijalarni ko'rsatish"""
    query = update.message.text.strip()
    
    if not query:
        await update.message.reply_text("❌ Iltimos, qo'shiq nomini kiriting!")
        return
    
    status_message = await update.message.reply_text("🔍 Qo'shiqlar qidirilmoqda...")
    
    try:
        # Birinchi 10 ta natijani olish
        songs = await search_youtube(query, 0)
        
        if not songs:
            await status_message.edit_text(
                "❌ Qo'shiqlar topilmadi.\n"
                "Iltimos, boshqa so'rov bilan urinib ko'ring!"
            )
            return
        
        # Natijalarni saqlash
        context.user_data.update({
            'search_query': query,
            'current_page': 0
        })
        
        # Natijalarni ko'rsatish
        message_text, reply_markup = create_results_message(songs, 0, query)
        await status_message.edit_text(
            text=message_text,
            reply_markup=reply_markup
        )
        
    except Exception as e:
        logger.error(f"Qidirish va ko'rsatishda xato: {str(e)}")
        await status_message.edit_text(
            "❌ Xatolik yuz berdi.\n"
            "Iltimos, qaytadan urinib ko'ring!"
        )

def format_view_count(count: int) -> str:
    """Sonlarni M va K formatiga o'tkazish"""
    if count >= 1000000:
        return f"{count/1000000:.1f}M"
    elif count >= 1000:
        return f"{count/1000:.1f}K"
    return str(count)
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Callback query larni qayta ishlash"""
    query = update.callback_query
    await query.answer()
    
    try:
        if query.data == "cancel_search":
            await query.message.delete()
            await query.message.reply_text(
                "🔍 Yangi qo'shiq qidirish uchun nomini yozing:"
            )
            return
            
        elif query.data.startswith("page_"):
            page = int(query.data.split("_")[1])
            search_query = context.user_data.get('search_query', '')
            
            # Yangi sahifa uchun natijalarni olish
            songs = await search_youtube(search_query, page * 10)
            
            if songs:
                message_text, reply_markup = create_results_message(
                    songs, 
                    page, 
                    search_query,
                    has_more=len(songs) == 10
                )
                await query.message.edit_text(
                    text=message_text,
                    reply_markup=reply_markup
                )
            
        elif query.data.startswith("song_"):
            video_id = query.data.split("_")[1]
            await download_and_send_song(query.message, video_id)
            
    except Exception as e:
        logger.error(f"Callback da xato: {str(e)}")
        await query.message.edit_text(
            "❌ Xatolik yuz berdi!\nQaytadan urinib ko'ring!"
        )

async def download_and_send_song(message, video_id: str) -> None:
    """Qo'shiqni yuklab yuborish"""
    status_message = await message.reply_text("⏳ Qo'shiq yuklanmoqda...")
    
    try:
        ydl_opts = {
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'outtmpl': f'downloads/%(title)s.%(ext)s',
            'quiet': True,
            'no_warnings': True,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            video_url = f"https://youtube.com/watch?v={video_id}"
            info = ydl.extract_info(video_url, download=True)
            
            audio_path = ydl.prepare_filename(info).rsplit('.', 1)[0] + '.mp3'
            
            if not os.path.exists(audio_path):
                raise Exception("Fayl yuklanmadi")
            
            caption = (
                f"🎵 {info['title']}\n"
                f"👤 {info.get('uploader', 'Noma\'lum')}\n"
                f"⏱ {int(info['duration']//60)}:{int(info['duration']%60):02d}\n"
            )
            
            async with aiofiles.open(audio_path, 'rb') as audio_file:
                await message.reply_audio(
                    audio=await audio_file.read(),
                    caption=caption,
                    title=info['title'][:64],
                    performer=info.get('uploader', 'Unknown')[:64],
                    duration=int(info['duration']),
                    filename=f"{info['title'][:32]}.mp3"
                )
            
            await status_message.delete()
            
    except Exception as e:
        logger.error(f"Yuklashda xato: {str(e)}")
        await status_message.edit_text(
            "❌ Qo'shiqni yuklashda xatolik yuz berdi!\n"
            "Iltimos, qaytadan urinib ko'ring."
        )
    finally:
        try:
            if 'audio_path' in locals() and os.path.exists(audio_path):
                os.remove(audio_path)
        except Exception as e:
            logger.error(f"Faylni o'chirishda xato: {str(e)}")

def add_user(self, user_id: int, username: str, first_name: str) -> bool:
    """Yangi foydalanuvchi qo'shish"""
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        current_time = datetime.now(datetime.UTC).strftime('%Y-%m-%d %H:%M:%S')
        c.execute(
            "INSERT OR REPLACE INTO users (user_id, username, first_name, joined_date) VALUES (?, ?, ?, ?)",
            (user_id, username, first_name, current_time)
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Foydalanuvchi qo'shishda xato: {str(e)}")
        return False

def cleanup_files(*file_paths: str) -> None:
    """Fayllarni o'chirish"""
    for file_path in file_paths:
        try:
            if file_path and os.path.exists(file_path):
                os.remove(file_path)
        except Exception as e:
            logger.error(f"Faylni o'chirishda xato: {str(e)}")

def main():
    """Botni ishga tushirish"""
    # Yuklanmalar papkasini yaratish
    if not os.path.exists(DOWNLOADS_DIR):
        os.makedirs(DOWNLOADS_DIR)
    
    # Bot applicationini yaratish
    app = Application.builder().token(Config.BOT_TOKEN).build()

    # Admin autentifikatsiya handleri
    admin_handler = ConversationHandler(
        entry_points=[CommandHandler("admin", admin_command)],
        states={
            ADMIN_AUTH: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND, 
                    admin_auth
                )
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
        # Broadcast handler
    # Broadcast conversation handler
    broadcast_handler = ConversationHandler(
        entry_points=[
            MessageHandler(
                filters.Regex('^📝 Xabar yuborish$'),
                broadcast_command
            )
        ],
        states={
            BROADCAST: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    broadcast_message
                )
            ]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )

        # Message handler
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & filters.Regex(r'^(?!/).+'),
        handle_message))
    app.add_handler(admin_handler)
    app.add_handler(CallbackQueryHandler(find_song_callback, pattern="^find_song_"))
    app.add_handler(CallbackQueryHandler(quality_callback, pattern="^quality_"))
    app.add_handler(CallbackQueryHandler(handle_callback, pattern=r'^song_'))
    app.add_handler(CallbackQueryHandler(handle_callback, pattern=r'^cancel_search$'))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, search_and_show_results))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, process_video))
  


     # Kanallar uchun callback handler
    app.add_handler(CallbackQueryHandler(channel_callback, pattern="^(add_channel|remove_channel|refresh_channels)$"))
    # In main() function, add this before adding other handlers:    
    app.add_handler(CallbackQueryHandler(check_subscription_callback, pattern="^check_subscription$"))
    # Callback query handler
    app.add_handler(CallbackQueryHandler(channel_callback))
    # Kanal qo'shish handleri
    add_channel_handler = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("^➕ Kanal qo'shish$"), add_channel_command),
            CallbackQueryHandler(lambda u, c: add_channel_command(u, c), pattern="^add_channel$")
        ],
        states={
            ADDING_CHANNEL: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_channel)]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    app.add_handler(add_channel_handler)
    
    # Kanallar ro'yxati handleri
    app.add_handler(MessageHandler(filters.Regex("^📋 Kanallar ro'yxati$"), show_channels))
    # Handlerlarni qo'shish
    app.add_handler(broadcast_handler)
    app.add_handler(add_channel_handler)
    app.add_handler(MessageHandler(filters.Regex("^📊 Statistika$"), show_statistics))
        # Voice va audio message handler (yangi)
    app.add_handler(MessageHandler(
        filters.VOICE | filters.AUDIO,
        handle_music_recognition
    ))
    
    # Mavjud handlerlar
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        handle_message
    ))
    
    # Handlerlarni qo'shish
    app.add_handler(admin_handler)
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("stop", stop_command))
    
    # Admin panel handlerlari
    app.add_handler(CommandHandler("admin", admin_command))
    app.add_handler(CommandHandler("parol", check_admin_password))
    # Qo'shiq qidirish handleri
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_song_search))
    
    # Admin panel handlerlari
    app.add_handler(MessageHandler(
        filters.Regex("^📊 Statistika$"), 
        show_statistics
    ))
    app.add_handler(MessageHandler(
        filters.Regex("^➕ Kanal qo'shish$"),
        add_channel_command
    ))
    app.add_handler(MessageHandler(
        filters.Regex("^➖ Kanal o'chirish$"), 
        remove_channel_command
    ))
    app.add_handler(MessageHandler(
        filters.Regex("^📝 Xabar yuborish$"),
        broadcast_message
    ))
    app.add_handler(MessageHandler(
        filters.Regex("^⚙️ Sozlamalar$"),
        settings_command
    ))
    app.add_handler(MessageHandler(
        filters.Regex("^📋 Kanallar ro'yxati$"),
        show_channels
    ))
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        handle_message
    ))

    print(f"Bot ishga tushdi... (Ctrl+C bosib to'xtatish mumkin){Config.CURRENT_DATE}")
    logger.info("Bot ishga tushdi...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    try:
        import yt_dlp
        from pydub import AudioSegment
        import instaloader
        from instaloader import Post
        ssl._create_default_https_context = ssl._create_unverified_context
        Config.validate()
        main()
    except KeyboardInterrupt:
        print("\nBot to'xtatildi (Ctrl+C bosildi)")
        logger.info("Bot to'xtatildi (Ctrl+C bosildi)")
    except Exception as e:
        print(f"Xatolik yuz berdi: {str(e)}")
        logger.error(f"Xatolik yuz berdi: {str(e)}")