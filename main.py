import os
import asyncio
import sqlite3
from datetime import datetime
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext
from admin_panel import router as admin_router, SUPER_ADMIN_IDS
from database import init_db
from aiohttp import web

BOT_TOKEN = "8885718773:AAE2KwDnnYKEUR7QNymmGR1Vz_1SlDX5CiE"[cite: 4]

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

def escape_md(text: str) -> str:
    if text is None:
        return ""
    for ch in ("_", "*", "`", "["):
        text = text.replace(ch, f"\\{ch}")
    return text

def get_main_keyboard(user_id):
    # Ishchi sifatida kirish tugmasi olib tashlandi
    buttons = [
        [KeyboardButton(text="🔑 Bo'lim Admini (Login)")],
        [KeyboardButton(text="👁 Mehmon / Tekshiruvchi kirishi")]
    ]
    if int(user_id) in SUPER_ADMIN_IDS:
        buttons.append([KeyboardButton(text="👑 Super Admin Paneli")])
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

@dp.message(F.text == "/start")
async def send_welcome(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    
    welcome_text = (
        f"Salom! Xavfsizlik vositalarini nazorat qilish botiga xush kelibsiz.\n"
        f"Sizning Telegram ID: `{user_id}`\n\n"
        "Iltimos, quyidagi bo'limlardan birini tanlang:"
    )
    await message.answer(welcome_text, reply_markup=get_main_keyboard(user_id), parse_mode="Markdown")


# --- MEHMON / TEKSHIRUVCHILAR TIZIMI (FAQAT KO'RISH) ---
@dp.message(F.text == "👁 Mehmon / Tekshiruvchi kirishi")
async def guest_view(message: Message):
    conn = sqlite3.connect('safety_bot.db')
    cursor = conn.cursor()
    cursor.execute('SELECT id, name FROM departments')
    depts = cursor.fetchall()
    
    report = "👁 **Mehmon/Tekshiruvchi rejimi:**\nTashkilot bo'yicha barcha ma'lumotlar bilan tanishing (O'zgartirish ruxsati yo'q):\n"
    
    for dept_id, dept_name in depts:
        report += f"\n🏢 **{escape_md(dept_name)}**\n"
        # Bo'limdagi asboblar
        cursor.execute('SELECT tool_name, expiry_date FROM safety_tools WHERE department_id=?', (dept_id,))
        tools = cursor.fetchall()
        report += "  🛠 *Xavfsizlik vositalari:*\n"
        if not tools:
            report += "    - Vositalar biriktirilmagan\n"
        else:
            for t_name, exp in tools:
                report += f"    • {escape_md(t_name)} ({exp})\n"
    
    conn.close()
    
    if len(report) > 4000:
        for i in range(0, len(report), 4000):
            await message.answer(report[i:i+4000], parse_mode="Markdown")
    else:
        await message.answer(report, parse_mode="Markdown")


# =====================================================================
# 🚀 MUDDATLARNI AVTOMATIK TEKSHIRISH VA OGOHLANTIRISH XIZMATI
# =====================================================================
async def check_expirations_loop(bot: Bot):
    """Har 24 soatda har bir bo'limning asbob-uskunalarini tekshiradi va
    amal qilish muddati tugayotgan bo'lsa, o'sha bo'limdagi ro'yxatdan o'tgan
    adminlarni ogohlantiradi."""
    while True:
        try:
            conn = sqlite3.connect('safety_bot.db')
            cursor = conn.cursor()
            cursor.execute('SELECT id, name, admin_telegram_id FROM departments')
            departments = cursor.fetchall()

            today = datetime.now().date()

            for dept_id, dept_name, admin_tg_id in departments:
                cursor.execute('SELECT tool_name, expiry_date FROM safety_tools WHERE department_id=?', (dept_id,))
                tools = cursor.fetchall()

                for tool_name, expiry_str in tools:
                    try:
                        expiry_date = datetime.strptime(expiry_str.strip(), '%Y-%m-%d').date()
                        days_left = (expiry_date - today).days

                        msg_admin = ""

                        # Bildirishnoma shartlari
                        if days_left in [10, 5, 1]:
                            msg_admin = f"⚠️ *Bo'lim asbobi ogohlantirishi!*\n\n*{dept_name}* bo'limidagi *{tool_name}* asbobining muddati tugashiga *{days_left} kun* qoldi.\n🗓 Muddat: `{expiry_str}`"
                        elif days_left == 0:
                            msg_admin = f"🚨 *MUHIM OGOHLANTIRISH!*\n\n*{dept_name}* bo'limidagi *{tool_name}* asbobining muddati *BUGUN TUGADI*!"
                        elif days_left < 0:
                            msg_admin = f"❌ *MUDDAT O'TIB KETGAN!*\n\n*{dept_name}* bo'limidagi *{tool_name}* asbobi muddati *{abs(days_left)} kun oldin tugagan!*"

                        if msg_admin and admin_tg_id:
                            try:
                                await bot.send_message(chat_id=admin_tg_id, text=msg_admin, parse_mode="Markdown")
                            except Exception:
                                pass

                    except ValueError:
                        continue

            conn.close()
        except Exception as err:
            print(f"Tekshirish loopida xatolik: {err}")

        await asyncio.sleep(86400)


# =====================================================================
# 🌐 VEB SERVER VA MAIN START
# =====================================================================
async def handle_ping(request):
    return web.Response(text="Bot is running smoothly without worker logics!")

async def start_web_server():
    app = web.Application()
    app.router.add_get('/', handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    
    port = int(os.environ.get("PORT", 8000))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

async def main():
    init_db()
    dp.include_router(admin_router)
    
    await start_web_server()
    asyncio.create_task(check_expirations_loop(bot))
    
    print("Bot muvaffaqiyatli ishga tushdi...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
