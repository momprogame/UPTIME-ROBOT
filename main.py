import asyncio
import aiohttp
import time
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.enums import ParseMode
import uvloop  # Optional: for better performance

from config import API_ID, API_HASH, BOT_TOKEN, OWNER_ID, MONITOR_INTERVAL
from database import Database

# Optional: Install uvloop for better performance
try:
    import uvloop
    uvloop.install()
    print("✓ uvloop installed for better performance")
except ImportError:
    print("⚠ uvloop not installed (optional)")

# Initialize database
db = Database()

# Variable to control monitoring
is_monitoring = True

# Owner-only decorator
def owner_only(func):
    async def wrapper(client, message: Message):
        if message.from_user.id != OWNER_ID:
            await message.reply("⛔ No autorizado. Solo el dueño del bot puede usar este comando.")
            return
        return await func(client, message)
    return wrapper

# Create client without starting it yet
app = Client(
    "web_monitor_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

@app.on_message(filters.command("start"))
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

@app.on_message(filters.command("help"))
async def help_command(client, message: Message):
    await start_command(client, message)

@app.on_message(filters.command("add"))
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

@app.on_message(filters.command("remove"))
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

@app.on_message(filters.command("list"))
@owner_only
async def list_websites(client, message: Message):
    websites_list = await db.list_websites()
    await message.reply(websites_list, parse_mode=ParseMode.MARKDOWN)

@app.on_message(filters.command("status"))
@owner_only
async def check_status_now(client, message: Message):
    await message.reply("🔍 Verificando estado de todos los websites...")
    await check_all_websites(client, manual=True)

@app.on_message(filters.command("stop"))
@owner_only
async def stop_monitoring(client, message: Message):
    global is_monitoring
    is_monitoring = False
    await message.reply("⏹️ Monitoreo detenido. Usa /start_monitor para reanudar.")

@app.on_message(filters.command("start_monitor"))
@owner_only
async def start_monitoring(client, message: Message):
    global is_monitoring
    if not is_monitoring:
        is_monitoring = True
        await message.reply("▶️ Monitoreo reanudado.")
        asyncio.create_task(monitoring_loop())
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
                message = f"""
🔔 *¡Cambio de estado detectado!*

*Website:* {result['name']}
*URL:* `{result['url']}`
*Estado:* {status_emoji} {current_status.upper()}
*Tiempo:* {response_time}ms
                """
                
                if result.get("error"):
                    message += f"\n*Error:* {result['error']}"
                
                try:
                    await client.send_message(OWNER_ID, message, parse_mode=ParseMode.MARKDOWN)
                except Exception as e:
                    print(f"Error sending notification: {e}")

async def monitoring_loop():
    """Bucle principal de monitoreo"""
    global is_monitoring
    print("✓ Monitoring loop started")
    
    while is_monitoring:
        try:
            await check_all_websites(app, manual=False)
        except Exception as e:
            print(f"Error en monitoreo: {e}")
            try:
                await app.send_message(OWNER_ID, f"⚠️ Error en monitoreo: {str(e)[:100]}")
            except:
                pass
        
        await asyncio.sleep(MONITOR_INTERVAL)

async def main():
    """Función principal asíncrona"""
    global is_monitoring
    
    print("🚀 Iniciando bot de monitoreo...")
    
    # Iniciar el cliente
    await app.start()
    print("✓ Bot client started")
    
    # Notificar inicio
    try:
        await app.send_message(
            OWNER_ID, 
            "🚀 *Bot de monitoreo iniciado*\nMonitoreando websites cada minuto.", 
            parse_mode=ParseMode.MARKDOWN
        )
        print("✓ Startup notification sent")
    except Exception as e:
        print(f"⚠ Could not send startup notification: {e}")
    
    # Iniciar el bucle de monitoreo
    is_monitoring = True
    monitor_task = asyncio.create_task(monitoring_loop())
    
    # Mantener el bot corriendo
    try:
        # Idle forever
        await asyncio.Event().wait()
    except KeyboardInterrupt:
        print("\n⏹ Stopping bot...")
    finally:
        is_monitoring = False
        monitor_task.cancel()
        await app.stop()

def run_bot():
    """Función para ejecutar el bot"""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⏹ Bot stopped by user")
    except Exception as e:
        print(f"❌ Fatal error: {e}")

if __name__ == "__main__":
    run_bot()
