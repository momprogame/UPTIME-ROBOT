#!/usr/bin/env python3
"""
Bot de Monitoreo Web para Telegram
Monitorea sitios web y notifica cambios de estado
"""

import asyncio
import aiohttp
import time
import os
import sys
from datetime import datetime
from typing import Optional, List, Tuple

# Configurar event loop para compatibilidad
import platform
if platform.system() == 'Windows':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Importaciones de Pyrogram (después de configurar el event loop)
from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.types import Message

# Importar configuración
try:
    from config import API_ID, API_HASH, BOT_TOKEN, OWNER_ID, MONITOR_INTERVAL
except ImportError:
    # Valores por defecto para desarrollo
    API_ID = os.getenv("API_ID", "14681595")
    API_HASH = os.getenv("API_HASH", "a86730aab5c59953c424abb4396d32d5")
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    OWNER_ID = int(os.getenv("OWNER_ID", "797046659"))
    MONITOR_INTERVAL = 60

# Importar base de datos
try:
    from database import Database
except ImportError:
    # Versión simple de Database si no existe el archivo
    import sqlite3
    import aiosqlite
    
    class Database:
        def __init__(self, db_path="websites.db"):
            self.db_path = db_path
            self.init_db()
        
        def init_db(self):
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
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
            try:
                async with aiosqlite.connect(self.db_path) as db:
                    await db.execute(
                        "INSERT INTO websites (url, name, added_by) VALUES (?, ?, ?)",
                        (url, name, added_by)
                    )
                    await db.commit()
                return True
            except:
                return False
        
        async def remove_website(self, url: str) -> bool:
            try:
                async with aiosqlite.connect(self.db_path) as db:
                    cursor = await db.execute(
                        "DELETE FROM websites WHERE url = ?",
                        (url,)
                    )
                    await db.commit()
                    return cursor.rowcount > 0
            except:
                return False
        
        async def get_all_websites(self) -> List[Tuple]:
            try:
                async with aiosqlite.connect(self.db_path) as db:
                    cursor = await db.execute(
                        "SELECT id, url, name FROM websites WHERE is_active = 1"
                    )
                    return await cursor.fetchall()
            except:
                return []
        
        async def save_monitoring_result(self, website_id: int, status: str, response_time: float):
            try:
                async with aiosqlite.connect(self.db_path) as db:
                    await db.execute(
                        "INSERT INTO monitoring_history (website_id, status, response_time) VALUES (?, ?, ?)",
                        (website_id, status, response_time)
                    )
                    await db.commit()
            except:
                pass
        
        async def get_last_status(self, website_id: int) -> Optional[str]:
            try:
                async with aiosqlite.connect(self.db_path) as db:
                    cursor = await db.execute(
                        "SELECT status FROM monitoring_history WHERE website_id = ? ORDER BY checked_at DESC LIMIT 1",
                        (website_id,)
                    )
                    result = await cursor.fetchone()
                    return result[0] if result else None
            except:
                return None
        
        async def list_websites(self) -> str:
            websites = await self.get_all_websites()
            if not websites:
                return "📋 No hay websites en monitoreo"
            
            result = "📋 *Websites monitoreados:*\n\n"
            for i, (_, url, name) in enumerate(websites, 1):
                last_status = await self.get_last_status(_)
                status_emoji = "✅" if last_status == "online" else "❌" if last_status == "offline" else "⏳"
                result += f"{i}. {status_emoji} *{name}*: `{url}`\n"
            
            return result

# Inicializar base de datos
db = Database()

# Variables globales
is_monitoring = True
bot = None

# Decorador para verificar si es el dueño
def owner_only(func):
    async def wrapper(client, message: Message):
        if message.from_user.id != OWNER_ID:
            await message.reply("⛔ No autorizado. Solo el dueño del bot puede usar este comando.")
            return
        return await func(client, message)
    return wrapper

# Comandos del bot
@Client.on_message(filters.command("start"))
async def start_command(client, message: Message):
    welcome_text = """
🚀 *Bienvenido al Bot de Monitoreo Web*

Este bot monitorea tus servicios web cada minuto y te notifica si cambian su estado.

*Comandos disponibles:*
/add <url> <nombre> - Añadir un website
/remove <url> - Eliminar un website
/list - Listar websites monitoreados
/status - Ver estado actual
/help - Mostrar esta ayuda

🔔 *Notificaciones:* Recibirás alertas cuando un website cambie de estado (online/offline)
    """
    await message.reply(welcome_text, parse_mode=ParseMode.MARKDOWN)

@Client.on_message(filters.command("help"))
async def help_command(client, message: Message):
    await start_command(client, message)

@Client.on_message(filters.command("add"))
@owner_only
async def add_website(client, message: Message):
    try:
        parts = message.text.split(maxsplit=2)
        if len(parts) < 3:
            await message.reply("❌ Uso incorrecto.\nEjemplo: `/add https://ejemplo.com Mi Página Web`")
            return
        
        url = parts[1]
        name = parts[2]
        
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        
        success = await db.add_website(url, name, message.from_user.id)
        
        if success:
            await message.reply(f"✅ Website añadido correctamente:\n*{name}* - `{url}`", parse_mode=ParseMode.MARKDOWN)
        else:
            await message.reply("❌ El website ya existe en la base de datos o hubo un error.")
            
    except Exception as e:
        await message.reply(f"❌ Error: {str(e)}")

@Client.on_message(filters.command("remove"))
@owner_only
async def remove_website(client, message: Message):
    try:
        parts = message.text.split(maxsplit=1)
        if len(parts) < 2:
            await message.reply("❌ Uso incorrecto.\nEjemplo: `/remove https://ejemplo.com`")
            return
        
        url = parts[1]
        success = await db.remove_website(url)
        
        if success:
            await message.reply(f"✅ Website eliminado: `{url}`")
        else:
            await message.reply("❌ No se encontró el website en la base de datos.")
            
    except Exception as e:
        await message.reply(f"❌ Error: {str(e)}")

@Client.on_message(filters.command("list"))
@owner_only
async def list_websites(client, message: Message):
    websites_list = await db.list_websites()
    await message.reply(websites_list, parse_mode=ParseMode.MARKDOWN)

@Client.on_message(filters.command("status"))
@owner_only
async def check_status_now(client, message: Message):
    await message.reply("🔍 Verificando estado de todos los websites...")
    await check_all_websites(client, manual=True)

@Client.on_message(filters.command("stop"))
@owner_only
async def stop_monitoring(client, message: Message):
    global is_monitoring
    is_monitoring = False
    await message.reply("⏹️ Monitoreo detenido. Usa /start_monitor para reanudar.")

@Client.on_message(filters.command("start_monitor"))
@owner_only
async def start_monitoring(client, message: Message):
    global is_monitoring
    if not is_monitoring:
        is_monitoring = True
        await message.reply("▶️ Monitoreo reanudado.")
        asyncio.create_task(monitoring_loop(client))
    else:
        await message.reply("✅ El monitoreo ya está activo.")

async def check_website(session, website_id: int, url: str, name: str) -> dict:
    """Verifica el estado de un website"""
    start_time = time.time()
    try:
        async with session.get(url, timeout=10, allow_redirects=True) as response:
            response_time = time.time() - start_time
            status = "online" if response.status < 400 else "offline"
            return {
                "id": website_id,
                "url": url,
                "name": name,
                "status": status,
                "response_time": round(response_time * 1000, 2),
                "status_code": response.status
            }
    except asyncio.TimeoutError:
        return {
            "id": website_id,
            "url": url,
            "name": name,
            "status": "offline",
            "response_time": None,
            "error": "Timeout"
        }
    except Exception as e:
        return {
            "id": website_id,
            "url": url,
            "name": name,
            "status": "offline",
            "response_time": None,
            "error": str(e)[:50]
        }

async def check_all_websites(client, manual: bool = False):
    """Verifica todos los websites en la base de datos"""
    websites = await db.get_all_websites()
    
    if not websites:
        return
    
    async with aiohttp.ClientSession() as session:
        tasks = []
        for website_id, url, name in websites:
            tasks.append(check_website(session, website_id, url, name))
        
        results = await asyncio.gather(*tasks)
        
        for result in results:
            website_id = result["id"]
            current_status = result["status"]
            response_time = result["response_time"]
            
            await db.save_monitoring_result(website_id, current_status, response_time or 0)
            
            last_status = await db.get_last_status(website_id)
            
            if last_status and last_status != current_status and not manual:
                status_emoji = "✅" if current_status == "online" else "❌"
                message_text = f"""
🔔 *¡Cambio de estado detectado!*

*Website:* {result['name']}
*URL:* `{result['url']}`
*Estado:* {status_emoji} {current_status.upper()}
*Tiempo:* {response_time}ms
                """
                
                if result.get("error"):
                    message_text += f"\n*Error:* {result['error']}"
                
                try:
                    await client.send_message(OWNER_ID, message_text, parse_mode=ParseMode.MARKDOWN)
                except Exception as e:
                    print(f"Error enviando notificación: {e}")

async def monitoring_loop(client):
    """Bucle principal de monitoreo"""
    global is_monitoring
    print("✓ Bucle de monitoreo iniciado")
    
    while is_monitoring:
        try:
            await check_all_websites(client, manual=False)
        except Exception as e:
            print(f"Error en monitoreo: {e}")
            try:
                await client.send_message(OWNER_ID, f"⚠️ Error en monitoreo: {str(e)[:100]}")
            except:
                pass
        
        await asyncio.sleep(MONITOR_INTERVAL)

async def main():
    """Función principal"""
    global is_monitoring, bot
    
    print("🚀 Iniciando bot de monitoreo...")
    
    # Crear instancia del bot
    bot = Client(
        "web_monitor_bot",
        api_id=API_ID,
        api_hash=API_HASH,
        bot_token=BOT_TOKEN
    )
    
    # Iniciar el bot
    await bot.start()
    print("✓ Bot iniciado correctamente")
    
    # Obtener información del bot
    bot_info = await bot.get_me()
    print(f"✓ Bot: @{bot_info.username}")
    
    # Notificar al dueño
    try:
        await bot.send_message(
            OWNER_ID,
            "🚀 *Bot de monitoreo iniciado*\nMonitoreando websites cada minuto.",
            parse_mode=ParseMode.MARKDOWN
        )
        print("✓ Notificación de inicio enviada")
    except Exception as e:
        print(f"⚠ No se pudo enviar notificación: {e}")
    
    # Iniciar monitoreo
    is_monitoring = True
    monitor_task = asyncio.create_task(monitoring_loop(bot))
    
    # Mantener el bot corriendo
    try:
        # Mantener el bot activo
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print("\n⏹ Deteniendo bot...")
    finally:
        is_monitoring = False
        monitor_task.cancel()
        await bot.stop()
        print("✓ Bot detenido")

def run_bot():
    """Ejecutar el bot"""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⏹ Bot detenido por el usuario")
    except Exception as e:
        print(f"❌ Error fatal: {e}")
        sys.exit(1)

if __name__ == "__main__":
    # Verificar token
    if not BOT_TOKEN:
        print("❌ Error: BOT_TOKEN no está configurado")
        print("Configura BOT_TOKEN en las variables de entorno de Render")
        sys.exit(1)
    
    run_bot()
