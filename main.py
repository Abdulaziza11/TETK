import os
import asyncio
import sqlite3
from datetime import datetime
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from admin_panel import router as admin_router, SUPER_ADMIN_IDS
from database import init_db
from aiohttp import web

BOT_TOKEN = "8885718773:AAE2KwDnnYKEUR7QNymmGR1Vz_1SlDX5CiE"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

def escape_md(text: str) -> str:
    if text is None:
        return ""
    for ch in ("_", "*", "`", "["):
        text = text.replace(ch, f"\\{ch}")
    return text

class WorkerStates(StatesGroup):
    selecting_department = State()
    selecting_name = State()

def get_main_keyboard(user_id):
    buttons = [
        [KeyboardButton(text="👤 Ishchi sifatida kirish")],
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


# --- ISHCHI YO'LI (BO'LIMDAN VOSITALARNI OLADI) ---
@dp.message(F.text == "👤 Ishchi sifatida kirish")
async def worker_start(message: Message, state: FSMContext):
    await state.clear()
    conn = sqlite3.connect('safety_bot.db')
    cursor = conn.cursor()
    cursor.execute('SELECT id, name FROM departments')
    depts = cursor.fetchall()
    conn.close()

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=name, callback_data=f"work_dept_{d_id}")] for d_id, name in depts
    ])
    await message.answer("Qaysi bo'limda ishlaysiz? Tanlang:", reply_markup=keyboard)
    await state.set_state(WorkerStates.selecting_department)

@dp.callback_query(F.data.startswith("work_dept_"))
async def worker_select_name(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    dept_id = int(callback.data.split("_")[2])
    
    conn = sqlite3.connect('safety_bot.db')
    cursor = conn.cursor()
    cursor.execute('SELECT id, full_name FROM workers WHERE department_id=?', (dept_id,))
    workers = cursor.fetchall()
    conn.close()

    if not workers:
        await callback.message.edit_text("Ushbu bo'limda hali ishchilar ro'yxati mavjud emas. Admin orqali qo'shish kerak.")
        await state.clear()
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=name, callback_data=f"work_id_{w_id}_{dept_id}")] for w_id, name in workers
    ])
    await callback.message.edit_text("Ism-familiyangizni tanlang (Profil avtomatik tarzda bog'lanadi):", reply_markup=keyboard)
    await state.set_state(WorkerStates.selecting_name)

@dp.callback_query(F.data.startswith("work_id_"))
async def worker_show_tools(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    parts = callback.data.split("_")
    worker_id = int(parts[2])
    dept_id = int(parts[3])
    telegram_id = callback.from_user.id

    conn = sqlite3.connect('safety_bot.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE workers SET telegram_id=? WHERE id=?', (telegram_id, worker_id))
    cursor.execute('SELECT full_name FROM workers WHERE id=?', (worker_id,))
    worker_name = cursor.fetchone()[0]
    
    # Endi buyumlar to'g'ridan to'g'ri bo'limdan olinadi
    cursor.execute('SELECT tool_name, expiry_date FROM safety_tools WHERE department_id=?', (dept_id,))
    tools = cursor.fetchall()
    conn.commit()
    conn.close()

    await state.clear()

    response = f"🤝 Rahmat, **{escape_md(worker_name)}**!\nProfilingiz muvaffaqiyatli bog'landi va endi sizga tegishli bo'limga oid bildirishnomalar sizga shaxsan keladi.\n\n"
    if not tools:
        response += "Sizning bo'limingizga hozircha hech qanday xavfsizlik vositasi kiritilmagan."
    else:
        response += "🛠 **Bo'limingizga biriktirilgan asboblar va muddatlari:**\n"
        for name, expiry in tools:
            response += f"• {escape_md(name)} — Muddati: {expiry} gacha\n"
            
    await callback.message.edit_text(response, parse_mode="Markdown")


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
                
        # Bo'limdagi ishchilar
        cursor.execute('SELECT full_name FROM workers WHERE department_id=?', (dept_id,))
        workers = cursor.fetchall()
        report += "  👤 *Ishchilar ro'yxati:*\n"
        if not workers:
            report += "    - Ishchilar kiritilmagan\n"
        else:
            for w in workers:
                report += f"    - {escape_md(w[0])}\n"
    
    conn.close()
    
    # 4000 belgidan oshsa bo'lib yuborish
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
    barcha ishchilarni va adminlarni ogohlantiradi."""
    while True:
        try:
            conn = sqlite3.connect('safety_bot.db')
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, name, admin_telegram_id FROM departments
            ''')
            departments = cursor.fetchall()

            today = datetime.now().date()

            for dept_id, dept_name, admin_tg_id in departments:
                # Bo'limga tegishli barcha vositalarni olamiz
                cursor.execute('SELECT tool_name, expiry_date FROM safety_tools WHERE department_id=?', (dept_id,))
                tools = cursor.fetchall()
                
                # Bo'limdagi barcha ro'yxatdan o'tgan ishchilarni olamiz (telegram_id is not NULL)
                cursor.execute('SELECT telegram_id, full_name FROM workers WHERE department_id=? AND telegram_id IS NOT NULL', (dept_id,))
                workers = cursor.fetchall()

                for tool_name, expiry_str in tools:
                    try:
                        expiry_date = datetime.strptime(expiry_str.strip(), '%Y-%m-%d').date()
                        days_left = (expiry_date - today).days

                        msg_worker = ""
                        msg_admin = ""

                        # Bildirishnoma shartlari
                        if days_left in [10, 5, 1]:
                            msg_worker = f"⚠️ *Yaqinda muddat tugaydi!*\n\nBo'limingizga tegishli *{tool_name}* vositasi muddati tugashiga *{days_left} kun* qoldi.\n🗓 Muddat: `{expiry_str}`"
                            msg_admin = f"⚠️ *Bo'lim asbobi ogohlantirishi!*\n\n*{dept_name}* bo'limidagi *{tool_name}* asbobining muddati tugashiga *{days_left} kun* qoldi.\n🗓 Muddat: `{expiry_str}`"
                        elif days_left == 0:
                            msg_worker = f"🚨 *MUHIM DIQQAT!*\n\nBo'limingizga tegishli *{tool_name}* vositasining amal qilish muddati *BUGUN TUGADI*! Undan foydalanmang va tezda yangilanishini kuting."
                            msg_admin = f"🚨 *MUHIM OGOHLANTIRISH!*\n\n*{dept_name}* bo'limidagi *{tool_name}* asbobining muddati *BUGUN TUGADI*!"
                        elif days_left < 0:
                            msg_worker = f"❌ *XAVFLI VAZIYAT!*\n\nBo'limingizga tegishli *{tool_name}* asbobi muddati *{abs(days_left)} kun oldin o'tib ketgan!* Ishlatish taqiqlanadi."
                            msg_admin = f"❌ *MUDDAT O'TIB KETGAN!*\n\n*{dept_name}* bo'limidagi *{tool_name}* asbobi muddati *{abs(days_left)} kun oldin tugagan!*"

                        # Xabarlarni tarqatish
                        if msg_worker and workers:
                            for worker_tg_id, w_name in workers:
                                try:
                                    await bot.send_message(chat_id=worker_tg_id, text=msg_worker, parse_mode="Markdown")
                                except Exception:
                                    pass

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

        # Tekshiruv har 24 soatda ishlaydi (86400 soniya)
        await asyncio.sleep(86400)


# =====================================================================
# 🌐 RENDER PORTINI TINGLOVCHI VEB SERVER
# =====================================================================
async def handle_ping(request):
    return web.Response(text="Bot is running smoothly with multi-super-admin!")

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
