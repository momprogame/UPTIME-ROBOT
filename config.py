import os
from dotenv import load_dotenv

load_dotenv()

# Configuración desde variables de entorno
API_ID = os.getenv("API_ID", "14681595")
API_HASH = os.getenv("API_HASH", "a86730aab5c59953c424abb4396d32d5")
BOT_TOKEN = os.getenv("BOT_TOKEN")  # Necesitarás obtener esto de @BotFather
OWNER_ID = int(os.getenv("OWNER_ID", "797046659"))
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///websites.db")
MONITOR_INTERVAL = 60  # 1 minuto en segundos
