import sqlite3
from datetime import datetime
from typing import List, Tuple, Optional
import aiosqlite
import os

class Database:
    def __init__(self, db_path="websites.db"):
        self.db_path = db_path
        self.init_db()

    def init_db(self):
        """Inicializa la base de datos"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Tabla para websites monitoreados
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS websites (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                added_by INTEGER NOT NULL,
                added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active BOOLEAN DEFAULT 1
            )
        ''')
        
        # Tabla para historial de monitoreo
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS monitoring_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                website_id INTEGER,
                status TEXT NOT NULL,
                response_time REAL,
                checked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (website_id) REFERENCES websites (id)
            )
        ''')
        
        conn.commit()
        conn.close()

    async def add_website(self, url: str, name: str, added_by: int) -> bool:
        """Añade un nuevo website para monitorear"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    "INSERT INTO websites (url, name, added_by) VALUES (?, ?, ?)",
                    (url, name, added_by)
                )
                await db.commit()
            return True
        except sqlite3.IntegrityError:
            return False
        except Exception as e:
            print(f"Error adding website: {e}")
            return False

    async def remove_website(self, url: str) -> bool:
        """Elimina un website del monitoreo"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute(
                    "DELETE FROM websites WHERE url = ?",
                    (url,)
                )
                await db.commit()
                return cursor.rowcount > 0
        except Exception as e:
            print(f"Error removing website: {e}")
            return False

    async def get_all_websites(self) -> List[Tuple]:
        """Obtiene todos los websites activos"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute(
                    "SELECT id, url, name FROM websites WHERE is_active = 1"
                )
                return await cursor.fetchall()
        except Exception as e:
            print(f"Error getting websites: {e}")
            return []

    async def save_monitoring_result(self, website_id: int, status: str, response_time: float):
        """Guarda el resultado del monitoreo"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    "INSERT INTO monitoring_history (website_id, status, response_time) VALUES (?, ?, ?)",
                    (website_id, status, response_time)
                )
                await db.commit()
        except Exception as e:
            print(f"Error saving monitoring result: {e}")

    async def get_last_status(self, website_id: int) -> Optional[str]:
        """Obtiene el último estado del website"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute(
                    "SELECT status FROM monitoring_history WHERE website_id = ? ORDER BY checked_at DESC LIMIT 1",
                    (website_id,)
                )
                result = await cursor.fetchone()
                return result[0] if result else None
        except Exception as e:
            print(f"Error getting last status: {e}")
            return None

    async def list_websites(self) -> str:
        """Lista todos los websites monitoreados"""
        websites = await self.get_all_websites()
        if not websites:
            return "📋 No hay websites en monitoreo"
        
        result = "📋 *Websites monitoreados:*\n\n"
        for i, (_, url, name) in enumerate(websites, 1):
            last_status = await self.get_last_status(_)
            status_emoji = "✅" if last_status == "online" else "❌" if last_status == "offline" else "⏳"
            result += f"{i}. {status_emoji} *{name}*: `{url}`\n"
        
        return result
