"""
Video Music Bot - YouTube va Instagram videolaridan musiqa yuklovchi bot
Created by: Botirbek Tulqinov
Created at: 2025-02-05 07:21:49 UTC
"""

import os
import logging
from datetime import datetime, time
import shutil
import sqlite3
from typing import Final, Optional, Dict, Any, List
import aiohttp
from shazamio import Shazam
import requests
import asyncio
from moviepy.editor import VideoFileClip
import aiofiles
from urllib.parse import urlparse, parse_qs
import re  
from config import Config
from pathlib import Path

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, error, CallbackQuery, Message
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
import ffmpeg

# SSL muammosini hal qilish
ssl._create_default_https_context = ssl._create_unverified_context

# Bot konfiguratsiyasi


# Conversation states
DB_FILE: Final = "bot_database.db"
DOWNLOADS_DIR: Final = "downloads"
TEMP_DIR = "temp"
MAX_FILE_SIZE = 50 * 1024 * 1024 
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
    def get_channels(self) -> List[Dict[str, str]]:
        """Get all channels"""
        try:
            conn = sqlite3.connect(self.db_file)
            cur = conn.cursor()
            
            cur.execute("SELECT channel_id, channel_username FROM channels")
            channels = [
                {
                    "channel_id": row[0],
                    "channel_username": row[1]
                } 
                for row in cur.fetchall()
            ]
            
            conn.close()
            print("Debug - Retrieved channels:", channels)  # Debug print
            return channels
            
        except Exception as e:
            logger.error(f"Get channels error: {str(e)}")
            return []

    def delete_channel(self, channel_id: str) -> bool:
        """Delete a channel"""
        try:
            conn = sqlite3.connect(self.db_file)
            cur = conn.cursor()
            
            # Check if channel exists
            cur.execute('SELECT channel_id FROM channels WHERE channel_id = ?', (channel_id,))
            if not cur.fetchone():
                conn.close()
                return False
                
            # Delete channel
            cur.execute('DELETE FROM channels WHERE channel_id = ?', (channel_id,))
            conn.commit()
            conn.close()
            print(f"Debug - Deleted channel: {channel_id}")  # Debug print
            return True
            
        except Exception as e:
            logger.error(f"Delete channel error: {str(e)}")
            return False

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
    if str(user.id) != str(Config.ADMIN_ID):
        await update.message.reply_text(
            "❌ Bu buyruq faqat admin uchun!\n"
            f"👤 Admin bilan bog'lanish: {ADMIN_CONTACT}"
        )
        return
    
    # Admin panelga kirish uchun parol so'rash
    await update.message.reply_text(
        "🔐 Admin panelga kirish uchun /parol <parol> ko'rinishida kiriting\n"
        "Masalan: /parol 12345"
    )

async def check_admin_password(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin parolini tekshirish"""
    user = update.effective_user
    
    # Admin ekanligini tekshirish
    if str(user.id) != str(Config.ADMIN_ID):
        await update.message.reply_text("❌ Bu buyruq faqat admin uchun!")
        return
    
    # Parolni olish
    try:
        entered_password = context.args[0] if context.args else ""
    except:
        entered_password = ""
    
    # Parolni tekshirish
    if entered_password == Config.ADMIN_PASSWORD:
        context.user_data['is_admin'] = True
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
async def delete_channel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle channel deletion"""
    if update.message and update.message.text == "➖ Kanal o'chirish":
        db = Database()
        channels = db.get_channels()
        print("Debug - Channels list:", channels)  # Debug print
        
        if not channels:
            await update.message.reply_text(
                "❌ Kanallar ro'yxati bo'sh",
                reply_markup=ReplyKeyboardMarkup([
                    [KeyboardButton("◀️ Admin panelga qaytish")]
                ], resize_keyboard=True)
            )
            return

        keyboard = []
        for channel in channels:
            channel_id = channel.get('channel_id')
            channel_username = channel.get('channel_username')
            
            if channel_id and channel_username:
                keyboard.append([
                    InlineKeyboardButton(
                        f"❌ {channel_username}", 
                        callback_data=f"del_{channel_id}"
                    )
                ])
                
        if not keyboard:
            await update.message.reply_text(
                "❌ Kanallar ro'yxatini olishda xatolik",
                reply_markup=ReplyKeyboardMarkup([
                    [KeyboardButton("◀️ Admin panelga qaytish")]
                ], resize_keyboard=True)
            )
            return
            
        keyboard.append([InlineKeyboardButton("◀️ Orqaga", callback_data="admin_back")])
        
        await update.message.reply_text(
            "🗑 O'chirish uchun kanallarni tanlang:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    # Handle callback query
    query = update.callback_query
    if not query:
        return
    
    try:
        if not query.data.startswith('del_'):
            await query.answer("❌ Noto'g'ri so'rov")
            return

        channel_id = query.data.split('_')[1]
        db = Database()
        
        if db.delete_channel(channel_id):
            channels = db.get_channels()
            
            if channels:
                keyboard = []
                for channel in channels:
                    channel_id = channel.get('channel_id')
                    channel_username = channel.get('channel_username')
                    
                    if channel_id and channel_username:
                        keyboard.append([
                            InlineKeyboardButton(
                                f"❌ {channel_username}", 
                                callback_data=f"del_{channel_id}"
                            )
                        ])

                keyboard.append([InlineKeyboardButton("◀️ Orqaga", callback_data="admin_back")])
                
                await query.edit_message_text(
                    "✅ Kanal o'chirildi!\n\n"
                    "🗑 Boshqa kanalni o'chirish uchun tanlang:",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            else:
                keyboard = [[InlineKeyboardButton("◀️ Orqaga", callback_data="admin_back")]]
                await query.edit_message_text(
                    "✅ Barcha kanallar o'chirildi!",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            
            await query.answer("✅ Kanal muvaffaqiyatli o'chirildi!")
        else:
            await query.answer("❌ Kanalni o'chirishda xatolik yuz berdi")
            
    except Exception as e:
        logger.error(f"Delete channel error: {str(e)}")
        await query.answer("❌ Xatolik yuz berdi")
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
    """Kanallar callback query larini qayta ishlash"""
    query = update.callback_query
    await query.answer()
    
    if query.data.startswith('remove_channel_'):
        channel_id = query.data.replace('remove_channel_', '')
        
        try:
            # Kanalni bazadan o'chirish
            if db.remove_channel(channel_id):
                # Yangilangan ro'yxatni ko'rsatish
                channels = db.get_channels()
                if channels:
                    text = "✅ Kanal o'chirildi!\n\n📢 Yangilangan ro'yxat:\n\n"
                    for i, ch in enumerate(channels, 1):
                        text += f"{i}. {ch['channel_name']}\n"
                        text += f"└ {ch['channel_id']}\n\n"
                else:
                    text = "✅ Kanal o'chirildi!\n\n❌ Boshqa kanallar yo'q."
                
                # Admin klaviaturasini qayta ko'rsatish
                await query.message.edit_text(
                    text,
                    reply_markup=get_admin_keyboard()
                )
            else:
                await query.message.edit_text(
                    "❌ Kanalni o'chirishda xatolik yuz berdi!",
                    reply_markup=get_admin_keyboard()
                )
                
        except Exception as e:
            logger.error(f"Kanal o'chirishda xato: {str(e)}")
            await query.message.edit_text(
                "❌ Xatolik yuz berdi!\n"
                "Qaytadan urinib ko'ring.",
                reply_markup=get_admin_keyboard()
            )
            
    elif query.data == "admin_back":
        await query.message.edit_text(
            "🔙 Admin panelga qaytdingiz",
            reply_markup=get_admin_keyboard()
        )

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
async def extract_video_id(url: str) -> Optional[str]:
    """YouTube URL dan video ID ni olish"""
    try:
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
            if match and match.group(1):
                return match.group(1)
        return None
    except Exception as e:
        logger.error(f"Video ID ni ajratishda xato: {str(e)}")
        return None
async def process_video(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Video va URL larni qayta ishlash"""
    message = update.message
    text = message.text if message.text else ""
    status_message = None

    if not os.path.exists(DOWNLOADS_DIR):
        os.makedirs(DOWNLOADS_DIR)

    try:
        # YouTube video uchun
        if "youtube.com" in text.lower() or "youtu.be" in text.lower():
            status_message = await message.reply_text("⏳ Video ma'lumotlari yuklanmoqda...")
            
            try:
                # Video ma'lumotlarini olish
                ydl_opts = {
                    'quiet': True,
                    'no_warnings': True,
                    'extract_flat': True,
                    'format': 'best',
                    'noplaylist': True,  # Playlistlarni yuklamaslik
                    'cookiesfrombrowser': ('chrome',),
                    'cookiefile': 'cookies.txt',
                    'no_check_certificate': True,
                    'nocheckcertificate': True,
                    'extractor_args': {
                        'youtube': {
                            'player_skip': 'webpage,configs',
                            'skip': 'webpage'
                        }
                    },
                    'http_headers': {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                        'Accept-Language': 'en-us,en;q=0.5',
                        'Sec-Fetch-Mode': 'navigate'
                    }
                }

                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    try:
                        # Video ma'lumotlarini olish
                        info = ydl.extract_info(text, download=False)
                        
                        if not info:
                            await status_message.edit_text(
                                "❌ Video topilmadi.\n"
                                "Iltimos, boshqa video tanlang."
                            )
                            return

                        # Mavjud formatlarni olish
                        formats = []
                        for f in info.get('formats', []):
                            if f.get('ext') == 'mp4' and f.get('vcodec', 'none') != 'none':
                                height = f.get('height', 0)
                                if height in [360, 480, 720, 1080]:
                                    formats.append({
                                        'height': height,
                                        'format_id': f['format_id']
                                    })

                        # Formatlarni saralash
                        formats = sorted(formats, key=lambda x: x['height'])
                        
                        if not formats:
                            await status_message.edit_text(
                                "❌ Yuklab olish mumkin bo'lgan formatlar topilmadi."
                            )
                            return

                        # Sifat tanlash tugmalarini yaratish
                        keyboard = []
                        row = []
                        
                        for fmt in formats:
                            callback_data = f"quality_{text}_{fmt['height']}"
                            row.append(InlineKeyboardButton(f"{fmt['height']}p", callback_data=callback_data))
                            
                            if len(row) == 2:
                                keyboard.append(row)
                                row = []
                        
                        if row:
                            keyboard.append(row)

                        keyboard.append([InlineKeyboardButton("❌ Bekor qilish", callback_data="cancel_download")])
                        reply_markup = InlineKeyboardMarkup(keyboard)

                        # Video ma'lumotlari bilan xabar yuborish
                        duration = info.get('duration', 0)
                        minutes, seconds = divmod(duration, 60)
                        hours, minutes = divmod(minutes, 60)
                        
                        duration_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}" if hours > 0 else f"{minutes:02d}:{seconds:02d}"
                        
                        await status_message.edit_text(
                            f"📹 {info.get('title')}\n"
                            f"👤 {info.get('uploader', 'Noma\'lum')}\n"
                            f"⏱ Davomiyligi: {duration_str}\n\n"
                            "📥 Yuklab olish sifatini tanlang:",
                            reply_markup=reply_markup
                        )

                    except yt_dlp.utils.DownloadError as e:
                        logger.error(f"YouTube yuklab olish xatosi: {str(e)}")
                        await status_message.edit_text(
                            "❌ Video yuklab olishda xatolik yuz berdi.\n"
                            "Iltimos, qayta urinib ko'ring."
                        )
                        return

            except Exception as e:
                logger.error(f"YouTube xatosi: {str(e)}")
                await status_message.edit_text(
                    "❌ Xatolik yuz berdi.\n"
                    "Iltimos, qayta urinib ko'ring."
                )
                return

        # Instagram video uchun
        elif "instagram.com" in text.lower():
            status_message = await message.reply_text("⏳ Instagram video aniqlanmoqda...")
            
            try:
                # URL dan ID ni olish
                if '/reel/' in text:
                    post_id = text.split('/reel/')[1].split('/')[0].split('?')[0]
                elif '/p/' in text:
                    post_id = text.split('/p/')[1].split('/')[0].split('?')[0]
                else:
                    await status_message.edit_text(
                        "❌ Noto'g'ri Instagram URL.\n"
                        "Namuna:\n"
                        "- https://www.instagram.com/p/XXXXX\n"
                        "- https://www.instagram.com/reel/XXXXX"
                    )
                    return

                await status_message.edit_text("📥 Video yuklanmoqda...")

                # Instaloader sozlamalari
                L = instaloader.Instaloader(
                    dirname_pattern=DOWNLOADS_DIR,
                    filename_pattern=f"instagram_{post_id}",
                    download_pictures=False,
                    download_video_thumbnails=False,
                    download_geotags=False,
                    download_comments=False,
                    save_metadata=False,
                    post_metadata_txt_pattern=""
                )

                try:
                    # Post ni olish
                    post = Post.from_shortcode(L.context, post_id)
                    
                    # Video ekanligini tekshirish
                    if not post.is_video:
                        await status_message.edit_text("❌ Bu post video emas!")
                        return

                    # Videoni yuklash
                    video_path = os.path.join(DOWNLOADS_DIR, f"instagram_{post_id}.mp4")
                    L.download_post(post, target=DOWNLOADS_DIR)

                    # Fayl mavjudligini tekshirish
                    if not os.path.exists(video_path):
                        raise FileNotFoundError("Video fayl topilmadi")

                    # Video hajmini tekshirish
                    if os.path.getsize(video_path) > 50 * 1024 * 1024:
                        os.remove(video_path)
                        await status_message.edit_text(
                            "❌ Video hajmi juda katta (50MB dan oshiq).\n"
                            "Iltimos, boshqa video tanlang."
                        )
                        return

                    # Musiqani aniqlash
                    music_info = None
                    try:
                        await status_message.edit_text("🎵 Videodagi musiqa aniqlanmoqda...")
                        
                        # Audio extraction va Shazam
                        audio_path = os.path.join(DOWNLOADS_DIR, f"temp_audio_{post_id}.mp3")
                        stream = ffmpeg.input(video_path)
                        stream = ffmpeg.output(stream, audio_path, acodec='libmp3lame', ac=2, ar='44100')
                        ffmpeg.run(stream, capture_stdout=True, capture_stderr=True, overwrite_output=True)

                        if os.path.exists(audio_path):
                            shazam = Shazam()
                            async with aiofiles.open(audio_path, 'rb') as f:
                                content = await f.read()
                                result = await shazam.recognize_song(content)
                                
                                if result and 'track' in result:
                                    track = result['track']
                                    music_info = {
                                        'title': track.get('title', 'Noma\'lum'),
                                        'artist': track.get('subtitle', 'Noma\'lum'),
                                        'url': track.get('share', {}).get('href', '')
                                    }
                            
                            # Audio faylni o'chirish
                            os.remove(audio_path)
                            
                    except Exception as e:
                        logger.error(f"Musiqani aniqlashda xato: {str(e)}")

                    # Caption tayyorlash
                    caption = f"📱 Instagram video\n"
                    if post.caption:
                        caption += f"📝 {post.caption[:500]}...\n" if len(post.caption) > 500 else f"📝 {post.caption}\n"
                    
                    if music_info:
                        caption += (
                            f"\n🎵 Aniqlangan musiqa:\n"
                            f"📌 Nomi: {music_info['title']}\n"
                            f"👤 Ijrochi: {music_info['artist']}\n"
                        )
                        if music_info.get('url'):
                            caption += f"🔗 Musiqa havolasi: {music_info['url']}\n"

                    # Videoni yuborish
                    await status_message.edit_text("📤 Video yuborilmoqda...")
                    async with aiofiles.open(video_path, 'rb') as f:
                        await message.reply_video(
                            video=await f.read(),
                            caption=caption,
                            supports_streaming=True
                        )
                    
                    await status_message.delete()

                except instaloader.exceptions.InstaloaderException as e:
                    logger.error(f"Instagram yuklab olishda xato: {str(e)}")
                    await status_message.edit_text(
                        "❌ Video yuklab olishda xatolik yuz berdi.\n"
                        "Sabablari:\n"
                        "1. Video mavjud emas\n"
                        "2. Post yopiq profilda\n"
                        "3. Video o'chirilgan\n"
                        "Iltimos, boshqa video tanlang."
                    )
                    return

            except Exception as e:
                logger.error(f"Instagram xato: {str(e)}")
                await status_message.edit_text(
                    "❌ Instagram video yuklab olishda xatolik yuz berdi.\n"
                    "Iltimos, qaytadan urinib ko'ring."
                )
                return

        else:
            await message.reply_text(
                "❌ Noto'g'ri format!\n\n"
                "Quyidagilarni yuborishingiz mumkin:\n"
                "1. YouTube video linki\n"
                "2. Instagram video/reel linki"
            )

    except Exception as e:
        logger.error(f"Video qayta ishlashda xato: {str(e)}")
        if status_message:
            await status_message.edit_text("❌ Xatolik yuz berdi")
        else:
            await message.reply_text("❌ Xatolik yuz berdi")

    finally:
        # Vaqtinchalik fayllarni tozalash
        try:
            for file in os.listdir(DOWNLOADS_DIR):
                file_path = os.path.join(DOWNLOADS_DIR, file)
                try:
                    if os.path.isfile(file_path):
                        os.remove(file_path)
                except Exception as e:
                    logger.error(f"Faylni o'chirishda xato: {str(e)}")
        except Exception as e:
            logger.error(f"Fayllarni tozalashda xato: {str(e)}")

async def ask_video_quality(update: Update, context: ContextTypes.DEFAULT_TYPE, video_url: str) -> None:
    """Video sifatini tanlash uchun tugmalar"""
    try:
        # Video ma'lumotlarini olish
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': True,
            'format': 'best',
            'format_sort': ['res:1080', 'res:720', 'res:480', 'res:360'],
            'prefer_free_formats': True
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                info = ydl.extract_info(video_url, download=False)
                
                if not info:
                    raise ValueError("Video ma'lumotlari topilmadi")

                # Formatlarni olish
                formats = []
                seen_heights = set()
                
                for f in info.get('formats', []):
                    if (f.get('ext') == 'mp4' and 
                        f.get('vcodec', 'none') != 'none' and 
                        f.get('height', 0) in [360, 480, 720, 1080] and
                        f.get('height') not in seen_heights):
                        
                        height = f.get('height', 0)
                        seen_heights.add(height)
                        formats.append({
                            'height': height,
                            'format_id': f['format_id'],
                            'filesize': f.get('filesize', 0)
                        })

                if not formats:
                    raise ValueError("Yuklanadigan formatlar topilmadi")

                # Formatlarni saralash
                formats = sorted(formats, key=lambda x: x['height'], reverse=True)
                
                # Tugmalarni yaratish
                keyboard = []
                video_id = video_url.split("v=")[1].split("&")[0] if "v=" in video_url else video_url.split("/")[-1]
                
                for fmt in formats:
                    # Fayl hajmini tekshirish (50MB dan kichik bo'lsa)
                    if fmt.get('filesize', 0) == 0 or fmt.get('filesize', 0) <= 50 * 1024 * 1024:
                        callback_data = f"quality_{video_id}_{fmt['height']}"
                        if len(callback_data) > 64:  # Telegram limit
                            callback_data = f"quality_{video_id[:10]}_{fmt['height']}"
                        keyboard.append([InlineKeyboardButton(f"📹 {fmt['height']}p", callback_data=callback_data)])

                if not keyboard:
                    raise ValueError("Yuklash uchun mos formatlar topilmadi")

                keyboard.append([InlineKeyboardButton("❌ Bekor qilish", callback_data="cancel_download")])
                reply_markup = InlineKeyboardMarkup(keyboard)

                # Video ma'lumotlari
                duration = info.get('duration', 0)
                minutes, seconds = divmod(duration, 60)
                hours, minutes = divmod(minutes, 60)
                duration_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}" if hours > 0 else f"{minutes:02d}:{seconds:02d}"
                
                title = info.get('title', 'Noma\'lum')
                if len(title) > 100:
                    title = title[:97] + "..."

                await update.message.reply_text(
                    f"📹 {title}\n"
                    f"👤 {info.get('uploader', 'Noma\'lum')}\n"
                    f"⏱ Davomiyligi: {duration_str}\n\n"
                    "📥 Yuklab olish sifatini tanlang:",
                    reply_markup=reply_markup
                )

            except Exception as e:
                logger.error(f"Video ma'lumotlarini olishda xato: {str(e)}")
                raise

    except Exception as e:
        logger.error(f"Sifat tanlashda xato: {str(e)}")
        await update.message.reply_text(
            "❌ Video sifatlarini olishda xatolik yuz berdi.\n"
            "Iltimos, qaytadan urinib ko'ring."
        )

async def download_video_with_quality(video_url: str, height: int, status_message) -> dict:
    try:
        ydl_opts = {
            'format': f'bestvideo[height<={height}][ext=mp4]+bestaudio[ext=m4a]/best[height<={height}][ext=mp4]',
            'outtmpl': os.path.join(DOWNLOADS_DIR, '%(title)s.%(ext)s'),
            'quiet': True,
            'no_warnings': True,
            'noplaylist': True,
            'merge_output_format': 'mp4',
            'max_filesize': 50 * 1024 * 1024  
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=True)
            video_path = ydl.prepare_filename(info)
            
            if not os.path.exists(video_path):
                raise FileNotFoundError("Video yuklanmadi")
            
            if os.path.getsize(video_path) > 50 * 1024 * 1024:
                os.remove(video_path)
                raise ValueError("Video hajmi juda katta (50MB dan oshiq)")
            
            return {
                'path': video_path,
                'title': info.get('title', 'Noma\'lum'),
                'duration': info.get('duration', 0),
                'height': height
            }
            
    except Exception as e:
        logger.error(f"Video yuklashda xato: {str(e)}")
        raise

async def quality_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Tanlangan sifatdagi videoni yuklash va yuborish"""
    query = update.callback_query
    await query.answer()
    
    status_message = None
    video_path = None
    
    try:
        if query.data == "cancel_download":
            await query.message.edit_text("❌ Yuklash bekor qilindi")
            return

        # quality_videoUrl_height
        _, video_id, height = query.data.split('_', 2)
        height = int(height)

        # Video URL ni to'g'ri formatda yaratish
        video_url = f"https://www.youtube.com/watch?v={video_id}"
        logger.info(f"Video URL: {video_url}, Height: {height}")

        # Progress xabari
        status_message = await query.message.reply_text(
            f"⏳ {height}p sifatdagi video yuklanmoqda...\n"
            "⚠️ Bu bir necha daqiqa vaqt olishi mumkin."
        )

        try:
            # Video yuklab olish sozlamalari
            ydl_opts = {
                'format': f'bestvideo[height<={height}]+bestaudio/best[height<={height}]',
                'outtmpl': os.path.join(DOWNLOADS_DIR, '%(title)s.%(ext)s'),
                'merge_output_format': 'mp4',
                'quiet': True,
                'no_warnings': True,
                'noplaylist': True
            }

            # Videoni yuklash
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(video_url, download=True)
                video_path = os.path.join(DOWNLOADS_DIR, f"{info['title']}.mp4")

                if os.path.exists(video_path):
                    # Fayl hajmini tekshirish
                    if os.path.getsize(video_path) > 50 * 1024 * 1024:
                        os.remove(video_path)
                        await status_message.edit_text(
                            "❌ Video hajmi juda katta (50MB dan oshiq).\n"
                            "Iltimos, pastroq sifatni tanlang."
                        )
                        return

                    try:
                        # Musiqani aniqlash
                        await status_message.edit_text("🎵 Videodagi musiqa aniqlanmoqda...")
                        music_info = await extract_and_identify_music(video_path)

                        # Caption tayyorlash
                        duration = info.get('duration', 0)
                        minutes, seconds = divmod(duration, 60)
                        hours, minutes = divmod(minutes, 60)
                        duration_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}" if hours > 0 else f"{minutes:02d}:{seconds:02d}"

                        caption = (
                            f"📹 {info.get('title', 'Video')}\n"
                            f"👤 {info.get('uploader', 'Noma\'lum')}\n"
                            f"🎥 {height}p\n"
                            f"⏱ Davomiyligi: {duration_str}\n"
                            f"🔗 {video_url}"
                        )

                        if music_info:
                            caption += (
                                f"\n\n🎵 Aniqlangan musiqa:\n"
                                f"📌 Nomi: {music_info['title']}\n"
                                f"👤 Ijrochi: {music_info['artist']}\n"
                            )
                            if music_info.get('url'):
                                caption += f"🔗 Musiqa havolasi: {music_info['url']}"

                        # Videoni yuborish
                        await status_message.edit_text("📤 Video yuborilmoqda...")
                        async with aiofiles.open(video_path, 'rb') as f:
                            video_file = await f.read()
                            await query.message.reply_video(
                                video=video_file,
                                caption=caption,
                                filename=f"{info['title']}.mp4",
                                supports_streaming=True,
                                duration=int(info.get('duration', 0)),
                                width=info.get('width'),
                                height=info.get('height')
                            )

                    except Exception as e:
                        logger.error(f"Video yuborishda xato: {str(e)}")
                        raise

                else:
                    raise FileNotFoundError("Video file not found after download")

        except Exception as e:
            logger.error(f"Video yuklashda xato: {str(e)}")
            raise

    except Exception as e:
        logger.error(f"Sifat tanlash xatosi: {str(e)}")
        if status_message:
            await status_message.edit_text(
                "❌ Xatolik yuz berdi.\n"
                "Iltimos, qaytadan urinib ko'ring."
            )

    finally:
        # Status xabarni o'chirish
        try:
            if status_message:
                await status_message.delete()
        except Exception as e:
            logger.error(f"Status xabarni o'chirishda xato: {str(e)}")

        # Vaqtinchalik fayllarni tozalash
        try:
            if video_path and os.path.exists(video_path):
                os.remove(video_path)
            
            # Qo'shimcha fayllarni tozalash
            for file in os.listdir(DOWNLOADS_DIR):
                file_path = os.path.join(DOWNLOADS_DIR, file)
                try:
                    if os.path.isfile(file_path):
                        os.remove(file_path)
                except Exception as e:
                    logger.error(f"Faylni o'chirishda xato: {str(e)}")
        except Exception as e:
            logger.error(f"Fayllarni tozalashda xato: {str(e)}")

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
    """Video va URL larni qayta ishlash"""
    message = update.message
    text = message.text if message.text else ""
    status_message = None

    if not os.path.exists(DOWNLOADS_DIR):
        os.makedirs(DOWNLOADS_DIR)

    try:
        # YouTube video uchun
        if "youtube.com" in text.lower() or "youtu.be" in text.lower():
            status_message = await message.reply_text("⏳ Video ma'lumotlari yuklanmoqda...")
            
            try:
                # Video ma'lumotlarini olish
                ydl_opts = {
                    'quiet': True,
                    'no_warnings': True,
                    'extract_flat': True
                }

                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    try:
                        info = ydl.extract_info(text, download=False)
                        
                        if not info:
                            await status_message.edit_text(
                                "❌ Video topilmadi.\n"
                                "Iltimos, boshqa video tanlang."
                            )
                            return

                        # Formatlarni olish
                        seen_heights = set()
                        formats = []
                        
                        for f in info.get('formats', []):
                            if (f.get('ext') == 'mp4' and 
                                f.get('vcodec', 'none') != 'none' and 
                                f.get('height', 0) in [360, 480, 720, 1080] and
                                f.get('height') not in seen_heights):
                                
                                height = f.get('height', 0)
                                seen_heights.add(height)
                                formats.append({
                                    'height': height,
                                    'format_id': f['format_id']
                                })

                        if not formats:
                            await status_message.edit_text(
                                "❌ Yuklab olish mumkin bo'lgan formatlar topilmadi."
                            )
                            return

                        # Formatlarni saralash
                        formats = sorted(formats, key=lambda x: x['height'], reverse=True)
                        keyboard = []
                        
                        # Video ID ni olish
                        video_id = None
                        if "v=" in text:
                            video_id = text.split("v=")[1].split("&")[0]
                        else:
                            video_id = text.split("/")[-1]

                        # Tugmalarni yaratish
                        for fmt in formats:
                            callback_data = f"quality_{video_id}_{fmt['height']}"
                            if len(callback_data) > 64:  # Telegram limit
                                callback_data = f"quality_{video_id[:10]}_{fmt['height']}"
                            keyboard.append([InlineKeyboardButton(f"📹 {fmt['height']}p", callback_data=callback_data)])

                        keyboard.append([InlineKeyboardButton("❌ Bekor qilish", callback_data="cancel_download")])
                        reply_markup = InlineKeyboardMarkup(keyboard)

                        # Video ma'lumotlari
                        duration = info.get('duration', 0)
                        minutes, seconds = divmod(duration, 60)
                        hours, minutes = divmod(minutes, 60)
                        duration_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}" if hours > 0 else f"{minutes:02d}:{seconds:02d}"
                        
                        title = info.get('title', 'Noma\'lum')
                        if len(title) > 100:
                            title = title[:97] + "..."

                        await status_message.edit_text(
                            f"📹 {title}\n"
                            f"👤 {info.get('uploader', 'Noma\'lum')}\n"
                            f"⏱ Davomiyligi: {duration_str}\n\n"
                            "📥 Yuklab olish sifatini tanlang:",
                            reply_markup=reply_markup
                        )
                        return

                    except yt_dlp.utils.DownloadError as e:
                        logger.error(f"YouTube yuklab olish xatosi: {str(e)}")
                        await status_message.edit_text(
                            "❌ Video yuklab olishda xatolik yuz berdi.\n"
                            "Iltimos, qayta urinib ko'ring."
                        )
                        return

            except Exception as e:
                logger.error(f"YouTube xatosi: {str(e)}")
                await status_message.edit_text(
                    "❌ Xatolik yuz berdi.\n"
                    "Iltimos, qayta urinib ko'ring."
                )
                return
        # Instagram media uchun
        elif "instagram.com" in text.lower():
            status_message = await message.reply_text("⏳ Instagram media aniqlanmoqda...")
            
            try:
                # Instaloader sozlamalari
                L = instaloader.Instaloader(
                    dirname_pattern=str(DOWNLOADS_DIR),
                    download_pictures=True,
                    download_videos=True,
                    download_video_thumbnails=False,
                    download_geotags=False,
                    download_comments=False,
                    save_metadata=False,
                    post_metadata_txt_pattern="",
                    max_connection_attempts=3,
                    request_timeout=30,
                    fatal_status_codes=[400, 429, 500, 503],
                    iphone_support=True,
                    user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1"
                )

                # Session bilan ishlash
                session_path = Path("sessions")
                session_file = session_path / f"{Config.INSTAGRAM_USERNAME}_instagram.session"
                session_path.mkdir(exist_ok=True)

                try:
                    if session_file.exists():
                        L.load_session_from_file(Config.INSTAGRAM_USERNAME, str(session_file))
                        # Session fayl yaroqliligini tekshirish
                        try:
                            profile = instaloader.Profile.from_username(L.context, Config.INSTAGRAM_USERNAME)
                            profile.get_posts()
                            logger.info("Instagram session is valid")
                        except:
                            logger.warning("Invalid session, creating new one")
                            if session_file.exists():
                                session_file.unlink()
                            L.login(Config.INSTAGRAM_USERNAME, Config.INSTAGRAM_PASSWORD)
                            L.save_session_to_file(str(session_file))
                    else:
                        L.login(Config.INSTAGRAM_USERNAME, Config.INSTAGRAM_PASSWORD)
                        L.save_session_to_file(str(session_file))
                        logger.info("New Instagram session created")

                    await status_message.edit_text("📥 Media aniqlanmoqda...")

                    # Story uchun
                    if '/stories/' in text:
                        try:
                            username = text.split('/stories/')[1].split('/')[0]
                            story_id = text.split('/stories/')[1].split('/')[1].split('?')[0]
                            
                            await status_message.edit_text("📥 Story yuklanmoqda...")
                            
                            profile = instaloader.Profile.from_username(L.context, username)
                            stories = L.get_stories([profile.userid])
                            
                            story_found = False
                            for story in stories:
                                for item in story.get_items():
                                    if str(item.mediaid) == story_id:
                                        story_found = True
                                        L.download_storyitem(item, target=DOWNLOADS_DIR)
                                        
                                        media_path = None
                                        if item.is_video:
                                            media_path = os.path.join(DOWNLOADS_DIR, f"{username}_{story_id}.mp4")
                                            # Musiqani aniqlash
                                            try:
                                                await status_message.edit_text("🎵 Videodagi musiqa aniqlanmoqda...")
                                                music_info = await extract_and_identify_music(media_path)
                                                caption = f"📱 Instagram Story\n👤 @{username}"
                                                if music_info:
                                                    caption += (
                                                        f"\n\n🎵 Aniqlangan musiqa:\n"
                                                        f"📌 Nomi: {music_info['title']}\n"
                                                        f"👤 Ijrochi: {music_info['artist']}\n"
                                                    )
                                                    if music_info.get('url'):
                                                        caption += f"🔗 Musiqa havolasi: {music_info['url']}"
                                            except Exception as e:
                                                logger.error(f"Musiqani aniqlashda xato: {str(e)}")
                                                caption = f"📱 Instagram Story\n👤 @{username}"
                                            
                                            await status_message.edit_text("📤 Story yuborilmoqda...")
                                            async with aiofiles.open(media_path, 'rb') as f:
                                                await message.reply_video(
                                                    video=await f.read(),
                                                    caption=caption,
                                                    supports_streaming=True
                                                )
                                        else:
                                            media_path = os.path.join(DOWNLOADS_DIR, f"{username}_{story_id}.jpg")
                                            async with aiofiles.open(media_path, 'rb') as f:
                                                await message.reply_photo(
                                                    photo=await f.read(),
                                                    caption=f"📱 Instagram Story\n👤 @{username}"
                                                )
                                        break
                                if story_found:
                                    break
                            
                            if not story_found:
                                await status_message.edit_text(
                                    "❌ Story topilmadi.\n"
                                    "Story o'chirilgan yoki mavjud emas."
                                )
                        
                        except Exception as e:
                            logger.error(f"Story yuklashda xato: {str(e)}")
                            await status_message.edit_text(
                                "❌ Story yuklab olishda xatolik.\n"
                                "Story mavjud emas yoki yopiq profilda."
                            )
                            return

                    # Post va Reel uchun
                    elif '/p/' in text or '/reel/' in text:
                        try:
                            media_id = text.split('/p/')[1].split('/')[0].split('?')[0] if '/p/' in text else text.split('/reel/')[1].split('/')[0].split('?')[0]
                            media_type = "Post" if '/p/' in text else "Reel"
                            
                            await status_message.edit_text(f"📥 {media_type} yuklanmoqda...")
                            
                            post = instaloader.Post.from_shortcode(L.context, media_id)
                            L.download_post(post, target=DOWNLOADS_DIR)
                            
                            # Media faylini aniqlash
                            media_path = None
                            if post.is_video:
                                media_path = os.path.join(DOWNLOADS_DIR, f"{post.date_utc.strftime('%Y-%m-%d_%H-%M-%S')}_UTC.mp4")
                                
                                if os.path.exists(media_path):
                                    # Fayl hajmini tekshirish
                                    if os.path.getsize(media_path) > 50 * 1024 * 1024:
                                        os.remove(media_path)
                                        await status_message.edit_text(f"❌ {media_type} hajmi juda katta (50MB dan oshiq).")
                                        return
                                    
                                    # Caption tayyorlash
                                    caption = f"📱 Instagram {media_type}\n"
                                    if post.caption:
                                        caption += f"📝 {post.caption[:500]}...\n" if len(post.caption) > 500 else f"📝 {post.caption}\n"
                                    caption += f"👤 @{post.owner_username}\n"
                                    
                                    # Musiqani aniqlash
                                    try:
                                        await status_message.edit_text("🎵 Videodagi musiqa aniqlanmoqda...")
                                        music_info = await extract_and_identify_music(media_path)
                                        if music_info:
                                            caption += (
                                                f"\n🎵 Aniqlangan musiqa:\n"
                                                f"📌 Nomi: {music_info['title']}\n"
                                                f"👤 Ijrochi: {music_info['artist']}\n"
                                            )
                                            if music_info.get('url'):
                                                caption += f"🔗 Musiqa havolasi: {music_info['url']}"
                                    except Exception as e:
                                        logger.error(f"Musiqani aniqlashda xato: {str(e)}")
                                    
                                    # Videoni yuborish
                                    await status_message.edit_text(f"📤 {media_type} yuborilmoqda...")
                                    async with aiofiles.open(media_path, 'rb') as f:
                                        await message.reply_video(
                                            video=await f.read(),
                                            caption=caption,
                                            supports_streaming=True
                                        )
                            else:
                                media_path = os.path.join(DOWNLOADS_DIR, f"{post.date_utc.strftime('%Y-%m-%d_%H-%M-%S')}_UTC.jpg")
                                if os.path.exists(media_path):
                                    caption = f"📱 Instagram {media_type}\n"
                                    if post.caption:
                                        caption += f"📝 {post.caption[:500]}...\n" if len(post.caption) > 500 else f"📝 {post.caption}\n"
                                    caption += f"👤 @{post.owner_username}"
                                    
                                    async with aiofiles.open(media_path, 'rb') as f:
                                        await message.reply_photo(
                                            photo=await f.read(),
                                            caption=caption
                                        )
                                        
                        except Exception as e:
                            logger.error(f"{media_type} yuklashda xato: {str(e)}")
                            await status_message.edit_text(
                                f"❌ {media_type} yuklab olishda xatolik.\n"
                                f"{media_type} mavjud emas yoki yopiq profilda."
                            )
                            return

                    else:
                        await status_message.edit_text(
                            "❌ Noto'g'ri Instagram URL.\n"
                            "Quyidagi formatlar qo'llab-quvvatlanadi:\n"
                            "- https://www.instagram.com/stories/username/ID\n"
                            "- https://www.instagram.com/p/XXXXX\n"
                            "- https://www.instagram.com/reel/XXXXX"
                        )
                        return

                except instaloader.exceptions.LoginRequiredException:
                    logger.error("Instagram login required")
                    if session_file.exists():
                        session_file.unlink()
                    await status_message.edit_text(
                        "⚠️ Instagram tizimiga qayta kirish kerak.\n"
                        "Iltimos, bir necha daqiqadan so'ng qayta urinib ko'ring."
                    )
                    return
                
                except Exception as e:
                    logger.error(f"Instagram session error: {str(e)}")
                    if session_file.exists():
                        session_file.unlink()
                    await status_message.edit_text(
                        "❌ Instagram tizimiga kirishda xatolik.\n"
                        "Iltimos, qayta urinib ko'ring."
                    )
                    return

            except Exception as e:
                logger.error(f"Instagram xato: {str(e)}")
                await status_message.edit_text(
                    "❌ Instagram media yuklab olishda xatolik yuz berdi.\n"
                    "Iltimos, qaytadan urinib ko'ring."
                )
                return

        else:
            await message.reply_text(
                "❌ Noto'g'ri format!\n\n"
                "Quyidagilarni yuborishingiz mumkin:\n"
                "1. YouTube video linki\n"
                "2. Instagram story/post/reel linki"
            )

    except Exception as e:
        logger.error(f"Video qayta ishlashda xato: {str(e)}")
        if status_message:
            await status_message.edit_text("❌ Xatolik yuz berdi")
        else:
            await message.reply_text("❌ Xatolik yuz berdi")

    finally:
        # YouTube video uchun status xabarni o'chirmaslik
        if status_message and not ("youtube.com" in text.lower() or "youtu.be" in text.lower()):
            try:
                await status_message.delete()
            except Exception as e:
                logger.error(f"Status xabarni o'chirishda xato: {str(e)}")
        
        # Vaqtinchalik fayllarni tozalash
        try:
            for file in os.listdir(DOWNLOADS_DIR):
                file_path = os.path.join(DOWNLOADS_DIR, file)
                try:
                    if os.path.isfile(file_path):
                        os.remove(file_path)
                except Exception as e:
                    logger.error(f"Faylni o'chirishda xato: {str(e)}")
        except Exception as e:
            logger.error(f"Fayllarni tozalashda xato: {str(e)}")


async def youtube_quality_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """YouTube video yuklab olish"""
    query = update.callback_query
    await query.answer()

    try:
        _, message_id, format_id = query.data.split('_')
        message_id = int(message_id)
        
        # Video ma'lumotlarini olish
        video_info = context.user_data.get(f'yt_info_{message_id}')
        if not video_info:
            await query.edit_message_text("❌ Video ma'lumotlari topilmadi!")
            return

        await query.edit_message_text("📥 Video yuklanmoqda...")

        try:
            # Videoni yuklash
            video_path = os.path.join(DOWNLOADS_DIR, f"youtube_{message_id}.mp4")
            ydl_opts = {
                'format': f"{format_id}+bestaudio[ext=m4a]",
                'outtmpl': video_path,
                'quiet': True
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([video_info['url']])

            # Videoni yuborish
            await query.edit_message_text("📤 Video yuborilmoqda...")
            
            async with aiofiles.open(video_path, 'rb') as f:
                await query.message.reply_video(
                    video=await f.read(),
                    caption=f"📺 {video_info['title']}\n🔗 {video_info['url']}",
                    supports_streaming=True
                )

            await query.message.delete()

        except Exception as e:
            logger.error(f"YouTube yuklab olishda xato: {str(e)}")
            await query.edit_message_text(
                "❌ Video yuklab olishda xatolik yuz berdi.\n"
                "Qayta urinib ko'ring."
            )

        finally:
            # Fayllarni tozalash
            try:
                if os.path.exists(video_path):
                    os.remove(video_path)
                if f'yt_info_{message_id}' in context.user_data:
                    del context.user_data[f'yt_info_{message_id}']
            except:
                pass

    except Exception as e:
        logger.error(f"YouTube callback xato: {str(e)}")
        await query.edit_message_text("❌ Xatolik yuz berdi")

async def cancel_download(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    # Yuklanayotgan videoni bekor qilish
    await query.message.edit_text("❌ Yuklash bekor qilindi!")
    
    # Context dan URL ni o'chirish
    message_id = query.message.reply_to_message.message_id
    if f'yt_url_{message_id}' in context.user_data:
        del context.user_data[f'yt_url_{message_id}']

async def download_instagram_video(message: Message, url: str, status_message: Message) -> Optional[Dict[str, Any]]:
    """Instagram videoni yuklash va musiqani aniqlash"""
    try:
        # URL dan ID ni olish
        if '/reel/' in url:
            post_code = url.split('/reel/')[1].split('/')[0].split('?')[0]
        elif '/p/' in url:
            post_code = url.split('/p/')[1].split('/')[0].split('?')[0]
        else:
            await status_message.edit_text("❌ Noto'g'ri Instagram URL")
            return None

        # Instaloader sozlamalari
        L = instaloader.Instaloader(
            dirname_pattern=DOWNLOADS_DIR,
            filename_pattern=f"instagram_{post_code}",
            download_pictures=False,
            download_video_thumbnails=False,
            download_geotags=False,
            download_comments=False,
            save_metadata=False,
            post_metadata_txt_pattern=""
        )

        try:
            await status_message.edit_text("📥 Video yuklanmoqda...")
            
            # Post ni olish va tekshirish
            post = Post.from_shortcode(L.context, post_code)
            if not post.is_video:
                await status_message.edit_text("❌ Bu post video emas!")
                return None

            # Videoni yuklash
            L.download_post(post, target=DOWNLOADS_DIR)
            
            # Video faylni topish
            video_path = None
            for file in os.listdir(DOWNLOADS_DIR):
                if file.endswith('.mp4') and post_code in file:
                    video_path = os.path.join(DOWNLOADS_DIR, file)
                    break

            if not video_path or not os.path.exists(video_path):
                raise FileNotFoundError("Video fayl topilmadi")

            # Musiqani aniqlash
            await status_message.edit_text("🎵 Videodagi musiqa aniqlanmoqda...")
            
            # Audio faylga o'tkazish
            audio_path = os.path.join(DOWNLOADS_DIR, f"temp_audio_{post_code}.mp3")
            stream = ffmpeg.input(video_path)
            stream = ffmpeg.output(stream, audio_path, acodec='libmp3lame', ac=2, ar='44100')
            ffmpeg.run(stream, capture_stdout=True, capture_stderr=True, overwrite_output=True)

            music_info = None
            if os.path.exists(audio_path):
                try:
                    shazam = Shazam()
                    async with aiofiles.open(audio_path, 'rb') as f:
                        content = await f.read()
                        result = await shazam.recognize_song(content)
                        
                        if result and 'track' in result:
                            track = result['track']
                            music_info = {
                                'title': track.get('title', 'Noma\'lum'),
                                'artist': track.get('subtitle', 'Noma\'lum'),
                                'url': track.get('share', {}).get('href', '')
                            }
                except Exception as e:
                    logger.error(f"Musiqani aniqlashda xato: {str(e)}")
                finally:
                    if os.path.exists(audio_path):
                        os.remove(audio_path)

            # Caption tayyorlash
            caption = f"📱 Instagram video\n🔗 {url}"
            if music_info:
                caption += (
                    f"\n\n🎵 Aniqlangan musiqa:\n"
                    f"📌 Nomi: {music_info['title']}\n"
                    f"👤 Ijrochi: {music_info['artist']}"
                )
                if music_info['url']:
                    caption += f"\n🔗 Musiqa havolasi: {music_info['url']}"

            return {
                'video_path': video_path,
                'caption': caption
            }

        except Exception as e:
            logger.error(f"Instagram video yuklab olishda xato: {str(e)}")
            await status_message.edit_text(
                "❌ Video yuklab olishda xatolik yuz berdi.\n"
                "Sabablari:\n"
                "1. Video mavjud emas\n"
                "2. Post yopiq profilda\n"
                "3. Link noto'g'ri"
            )
            return None

    except Exception as e:
        logger.error(f"Instagram xato: {str(e)}")
        await status_message.edit_text("❌ Xatolik yuz berdi")
        return None

async def extract_and_identify_music(video_path: str) -> Optional[Dict[str, str]]:
    """Extract audio from video and identify using Shazam"""
    temp_audio = os.path.join(TEMP_DIR, f"temp_audio_{os.path.basename(video_path)}.mp3")
    try:
        # Extract audio using ffmpeg
        stream = ffmpeg.input(video_path)
        stream = ffmpeg.output(stream, temp_audio, acodec='libmp3lame', ac=2, ar='44100')
        ffmpeg.run(stream, capture_stdout=True, capture_stderr=True, overwrite_output=True)

        # Initialize Shazam
        shazam = Shazam()

        # Read audio file in chunks for better memory management
        async with aiofiles.open(temp_audio, 'rb') as f:
            audio_bytes = await f.read()

        # Recognize song
        result = await shazam.recognize_song(audio_bytes)
        if result and 'track' in result:
            track = result['track']
            return {
                'title': track.get('title', 'Noma\'lum'),
                'artist': track.get('subtitle', 'Noma\'lum'),
                'album': track.get('sections', [{}])[0].get('metadata', [{}])[0].get('text', 'Noma\'lum'),
                'url': track.get('share', {}).get('href', '')
            }
        return None

    except Exception as e:
        logger.error(f"Musiqani aniqlashda xato: {str(e)}")
        return None

    finally:
        # Clean up temp audio file
        if os.path.exists(temp_audio):
            try:
                os.remove(temp_audio)
            except Exception as e:
                logger.error(f"Vaqtinchalik audio faylni o'chirishda xato: {str(e)}")

async def download_youtube_video(url: str) -> dict:
    """YouTube videoni yuklab olish"""
    try:
        ydl_opts = {
            'format': 'best[ext=mp4]/best',
            'outtmpl': os.path.join(DOWNLOADS_DIR, '%(title)s.%(ext)s'),
            'noplaylist': True,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            video_path = ydl.prepare_filename(info)
            return {'video_path': video_path}
            
    except Exception as e:
        logger.error(f"YouTube video yuklab olishda xato: {str(e)}")
        return None

async def find_song_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Qo'shiqni topish"""
    query = update.callback_query
    await query.answer()
    
    try:
        message_id = query.data.split('_')[2]
        video_info = context.user_data.get(f'video_{message_id}')
        
        if not video_info:
            await query.message.reply_text("❌ Video ma'lumotlari topilmadi!")
            return
        
        status = await query.message.reply_text("🎵 Qo'shiq izlanmoqda...")
        
        # Video faylini yuklab olish
        video_file = await context.bot.get_file(video_info['file_id'])
        temp_path = os.path.join(DOWNLOADS_DIR, f"temp_{message_id}.mp4")
        await video_file.download_to_drive(temp_path)
        
        # Audio faylga o'girish
        audio_path = os.path.join(DOWNLOADS_DIR, f"audio_{message_id}.mp3")
        stream = ffmpeg.input(temp_path)
        stream = ffmpeg.output(stream, audio_path, acodec='libmp3lame')
        ffmpeg.run(stream, overwrite_output=True)
        
        # Shazam orqali qo'shiqni aniqlash
        try:
            shazam = Shazam()
            with open(audio_path, 'rb') as f:
                results = await shazam.recognize_song(f.read())
            
            if results.get('track'):
                track = results['track']
                response_text = (
                    f"🎵 Qo'shiq topildi!\n\n"
                    f"📌 Nomi: {track.get('title', 'Noma\'lum')}\n"
                    f"👤 Ijrochi: {track.get('subtitle', 'Noma\'lum')}\n"
                    f"💿 Albom: {track.get('album', {}).get('title', 'Noma\'lum')}"
                )
                
                # YouTube da qidirish uchun tugma
                keyboard = [[
                    InlineKeyboardButton(
                        "🎵 YouTube da topish",
                        callback_data=f"yt_search_{track.get('title')}_{track.get('subtitle')}"
                    )
                ]]
                
                await status.edit_text(
                    response_text,
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            else:
                await status.edit_text(
                    "❌ Qo'shiq topilmadi.\n"
                    "Sabablari:\n"
                    "1. Video da musiqa yo'q\n"
                    "2. Musiqa juda past\n"
                    "3. Musiqa bazada yo'q"
                )
        
        except Exception as e:
            logger.error(f"Qo'shiqni aniqlashda xato: {str(e)}")
            await status.edit_text("❌ Qo'shiqni aniqlashda xatolik yuz berdi")
        
        finally:
            # Vaqtinchalik fayllarni tozalash
            if os.path.exists(temp_path):
                os.remove(temp_path)
            if os.path.exists(audio_path):
                os.remove(audio_path)
    
    except Exception as e:
        logger.error(f"Qo'shiq topish callback da xato: {str(e)}")
        await query.message.reply_text("❌ Xatolik yuz berdi")
async def download_song_from_youtube(update: Update, search_query: str, output_dir: str) -> Optional[Dict[str, Any]]:
    """Topilgan qo'shiqni to'liq versiyasini yuklash"""
    query = update.callback_query
    await query.answer()

    try:
        # Get song info from callback data
        _, title, artist = query.data.split("_", 2)
        status_message = await query.message.reply_text("🎵 Qo'shiq qidirilmoqda...")

        # Search and download song
        search_query = f"{artist} - {title}"
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': os.path.join(DOWNLOADS_DIR, '%(title)s.%(ext)s'),
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'quiet': True,
            'no_warnings': True
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # Search for the song
                result = ydl.extract_info(f"ytsearch1:{search_query}", download=False)
                if 'entries' in result and result['entries']:
                    # Download first result
                    info = ydl.extract_info(result['entries'][0]['url'], download=True)
                    audio_path = ydl.prepare_filename(info).rsplit('.', 1)[0] + '.mp3'

                    if os.path.exists(audio_path):
                        # Send audio file
                        await status_message.edit_text("📤 Qo'shiq yuborilmoqda...")
                        async with aiofiles.open(audio_path, 'rb') as f:
                            await query.message.reply_audio(
                                audio=await f.read(),
                                title=info.get('title', title),
                                performer=info.get('artist', artist),
                                duration=info.get('duration'),
                                caption=f"🎵 {info.get('title', title)}\n"
                                       f"👤 {info.get('artist', artist)}"
                            )
                        await status_message.delete()

                        # Clean up
                        try:
                            os.remove(audio_path)
                        except Exception as e:
                            logger.error(f"Faylni o'chirishda xato: {str(e)}")
                    else:
                        raise FileNotFoundError("Audio fayl yaratilmadi")
                else:
                    await status_message.edit_text("❌ Qo'shiq topilmadi")
        except Exception as e:
            logger.error(f"Qo'shiqni yuklashda xato: {str(e)}")
            await status_message.edit_text(
                "❌ Qo'shiqni yuklashda xatolik yuz berdi.\n"
                "Iltimos, qaytadan urinib ko'ring."
            )

    except Exception as e:
        logger.error(f"Callback handler xatosi: {str(e)}")
        await query.message.reply_text("❌ Xatolik yuz berdi")

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
        "📝 Yubormoqchi bo'lgan xabaringizni yuboring:\n\n"
        "Bekor qilish uchun /cancel"
    )
    return BROADCAST

async def broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Xabarni barcha foydalanuvchilarga yuborish"""
    if not is_admin(update):
        return ConversationHandler.END
    
    message = update.message
    users = db.get_all_users()
    
    if not users:
        await message.reply_text(
            "❌ Foydalanuvchilar topilmadi!",
            reply_markup=get_admin_keyboard()
        )
        return ConversationHandler.END
    
    progress_msg = await message.reply_text("📤 Xabar yuborilmoqda...")
    
    success_count = 0
    fail_count = 0
    
    for user in users:
        try:
            await context.bot.copy_message(
                chat_id=user['user_id'],
                from_chat_id=message.chat_id,
                message_id=message.message_id
            )
            success_count += 1
        except Exception as e:
            logger.error(f"Xabar yuborishda xato {user['user_id']}: {str(e)}")
            fail_count += 1
        
        # Har 10 ta yuborishda progressni yangilash
        if (success_count + fail_count) % 10 == 0:
            await progress_msg.edit_text(
                f"📤 Xabar yuborilmoqda...\n"
                f"✅ Yuborildi: {success_count}\n"
                f"❌ Xatolik: {fail_count}\n"
                f"📊 Progress: {((success_count + fail_count) / len(users)) * 100:.1f}%"
            )
    
    # Yakuniy natija
    result_text = (
        "📬 Xabar yuborish yakunlandi!\n\n"
        f"👥 Jami foydalanuvchilar: {len(users)}\n"
        f"✅ Muvaffaqiyatli: {success_count}\n"
        f"❌ Xatolik: {fail_count}"
    )
    
    await progress_msg.edit_text(
        result_text,
        reply_markup=get_admin_keyboard()
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
            await delete_channel_callback(update, context)
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
    if not os.path.exists(DOWNLOADS_DIR):
        os.makedirs(DOWNLOADS_DIR)
    
    app = Application.builder().token(Config.BOT_TOKEN).build()

    # 1. First register conversation handlers
    admin_handler = ConversationHandler(
        entry_points=[CommandHandler("admin", admin_command)],
        states={
            ADMIN_AUTH: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_auth)]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    
    broadcast_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex('^📝 Xabar yuborish$'), broadcast_command)],
        states={
            BROADCAST: [MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_message)]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    
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

    # 2. Register command handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("stop", stop_command))
    app.add_handler(CommandHandler("admin", admin_command))
    app.add_handler(CommandHandler("parol", check_admin_password))

    # 3. Register conversation handlers
    app.add_handler(admin_handler)
    app.add_handler(broadcast_handler)
    app.add_handler(add_channel_handler)
    

    # 4. Register callback query handlers
    app.add_handler(CallbackQueryHandler(youtube_quality_callback, pattern="^yt_"))
    app.add_handler(CallbackQueryHandler(cancel_download, pattern="^cancel_download$"))
    app.add_handler(CallbackQueryHandler(find_song_callback, pattern="^find_song_"))
    app.add_handler(CallbackQueryHandler(quality_callback, pattern="^quality_"))
    app.add_handler(CallbackQueryHandler(quality_callback))
    app.add_handler(CallbackQueryHandler(check_subscription_callback, pattern="^check_subscription$"))
    app.add_handler(CallbackQueryHandler(delete_channel_callback, pattern="^del_"))
    app.add_handler(CallbackQueryHandler(channel_callback, pattern="^(remove_channel_|admin_back)"))
    app.add_handler(CallbackQueryHandler(channel_callback, pattern="^(add_channel|remove_channel|refresh_channels)$"))
    app.add_handler(CallbackQueryHandler(handle_callback, pattern=r'^song_'))
    app.add_handler(CallbackQueryHandler(handle_callback, pattern=r'^cancel_search$'))
    app.add_handler(CallbackQueryHandler(download_instagram_video, pattern="^download_video_"))

    # 5. Register media handlers
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_music_recognition))
    app.add_handler(MessageHandler(
        filters.VIDEO | filters.Regex(r'(instagram\.com|youtube\.com|youtu\.be)'),
        process_video
    ))
    # Add callback query handler for song download button
    app.add_handler(CallbackQueryHandler(
        download_song_from_youtube,
        pattern="^download_song_"
    ))

    # 6. Register admin panel message handlers
    app.add_handler(MessageHandler(filters.Regex("^📊 Statistika$"), show_statistics))
    app.add_handler(MessageHandler(filters.Regex("^📋 Kanallar ro'yxati$"), show_channels))
    app.add_handler(MessageHandler(filters.Regex("^➖ Kanal o'chirish$"), delete_channel_callback))
    app.add_handler(MessageHandler(filters.Regex("^⚙️ Sozlamalar$"), settings_command))

    # 7. Register the catch-all text handler LAST
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

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
