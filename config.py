import os
from dotenv import load_dotenv
from datetime import datetime

# .env faylini yuklash
load_dotenv(".env")

class Config:
    # Bot sozlamalari
    BOT_TOKEN = os.getenv('BOT_TOKEN')
    ADMIN_ID = int(os.getenv('ADMIN_ID', 0))
    ADMIN_USERNAME = os.getenv('ADMIN_USERNAME')
    ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD')
    # Admin panel sozlamalari
    ADMIN_ENABLED = os.getenv('ADMIN_ENABLED', 'true').lower() == 'true'
    ADMIN_COMMAND = os.getenv('ADMIN_COMMAND', 'admin')
    ADMIN_WELCOME_MESSAGE = os.getenv('ADMIN_WELCOME_MESSAGE', '👋 Admin panelga xush kelibsiz!')
    ADMIN_HELP_MESSAGE = os.getenv('ADMIN_HELP_MESSAGE', 'Admin buyruqlari:')
    ADMIN_ACCESS_DENIED = os.getenv('ADMIN_ACCESS_DENIED', '❌ Kechirasiz, bu buyruq faqat adminlar uchun.')
    
    # Vaqt
    CURRENT_DATE = datetime.strptime(
        os.getenv('CURRENT_DATE', '2025-02-10 15:28:44'),
        '%Y-%m-%d %H:%M:%S'
    )
    
    # API kalitlari
    RAPIDAPI_KEY = os.getenv('RAPIDAPI_KEY')
    
    # Papkalar
    DOWNLOADS_DIR = os.getenv('DOWNLOADS_DIR', 'downloads')
    TEMP_DIR = os.getenv('TEMP_DIR', 'temp')
    
    # Debug
    DEBUG_MODE = os.getenv('DEBUG_MODE', 'False').lower() == 'true'
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
    
    @classmethod
    def validate(cls):
        """Muhim o'zgaruvchilarni tekshirish"""
        required_vars = [
            'BOT_TOKEN',
            'ADMIN_ID',
            'ADMIN_USERNAME',
            'ADMIN_PASSWORD'
        ]
        
        missing_vars = [var for var in required_vars if not getattr(cls, var)]
        
        if missing_vars:
            raise ValueError(
                f"Quyidagi muhim o'zgaruvchilar topilmadi: {', '.join(missing_vars)}\n"
                ".env faylini tekshiring"
            )
        
        # Kerakli papkalarni yaratish
        os.makedirs(cls.DOWNLOADS_DIR, exist_ok=True)
        os.makedirs(cls.TEMP_DIR, exist_ok=True)