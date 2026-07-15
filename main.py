import os
import asyncio
import sqlite3
from datetime import datetime
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from admin_panel import router as admin_router
from database import init_db

# Veb-server portini band qilish uchun aiohttp import qilamiz
from aiohttp import web

# Siz taqdim etgan Telegram Bot Tokeni
BOT_TOKEN = "8885718773:AAE2KwDnnYKEUR7QNymmGR1Vz_1SlDX5CiE"
SUPER_ADMIN_ID = 8676940332

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
        [KeyboardButton(text="🔑 Bo'lim Admini (Login)")]
    ]
    if int(user_id) == SUPER_ADMIN_ID:
        buttons.append([KeyboardButton(text="🌐 Barcha bo'limlarni ko'rish (Super Admin)")])
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

# --- ISHCHI YO'LI ---
@dp.message(F.text == "👤 Ishchi sifatida kirish")
async def worker_start(message: Message, state: FSMContext):
    await state.clear()
    
    conn = sqlite3.connect('safety_bot.db')
    cursor = conn.cursor()
    cursor.execute('SELECT id, name FROM departments')
    depts = cursor.fetchall()
    conn.close()

    if not depts:
        await message.answer("Tizimda bo'limlar topilmadi.")
        return

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
        [InlineKeyboardButton(text=name, callback_data=f"work_id_{w_id}")] for w_id, name in workers
    ])
    
    await callback.message.edit_text("Ism-familiyangizni tanlang (Profil avtomatik tarzda bog'lanadi):", reply_markup=keyboard)
    await state.set_state(WorkerStates.selecting_name)

@dp.callback_query(F.data.startswith("work_id_"))
async def worker_show_tools(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    worker_id = int(callback.data.split("_")[2])
    telegram_id = callback.from_user.id

    conn = sqlite3.connect('safety_bot.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE workers SET telegram_id=? WHERE id=?', (telegram_id, worker_id))
    cursor.execute('SELECT full_name FROM workers WHERE id=?', (worker_id,))
    worker_name = cursor.fetchone()[0]
    cursor.execute('SELECT tool_name, expiry_date FROM safety_tools WHERE worker_id=?', (worker_id,))
    tools = cursor.fetchall()
    conn.commit()
    conn.close()

    await state.clear()

    response = f"🤝 Rahmat, **{escape_md(worker_name)}**!\nProfilingiz muvaffaqiyatli bog'landi va endi bildirishnomalar sizga shaxsan keladi.\n\n"
    if not tools:
        response += "Sizga hozircha hech qanday xavfsizlik vositasi biriktirilmagan."
    else:
        response += "🛠 **Sizga biriktirilgan asboblar va muddatlari:**\n"
        for name, expiry in tools:
            response += f"• {escape_md(name)} — Muddati: {expiry} gacha\n"
            
    await callback.message.edit_text(response, parse_mode="Markdown")

# --- SUPER ADMIN YO'LI ---
@dp.message(F.text == "🌐 Barcha bo'limlarni ko'rish (Super Admin)")
async def super_admin_view(message: Message):
    if message.from_user.id != SUPER_ADMIN_ID:
        await message.answer("Sizda ushbu amalni bajarish uchun ruxsat yo'q.")
        return

    conn = sqlite3.connect('safety_bot.db')
    cursor = conn.cursor()
    cursor.execute('''
        SELECT d.name, w.full_name, t.tool_name, t.expiry_date 
        FROM departments d
        LEFT JOIN workers w ON d.id = w.department_id
        LEFT JOIN safety_tools t ON w.id = t.worker_id
        ORDER BY d.name, w.full_name
    ''')
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        await message.answer("Tizimda hech qanday ma'lumot topilmadi.")
        return

    report = "🌐 **Tashkilot bo'yicha umumiy xavfsizlik vositalari hisoboti:**\n"
    current_dept = ""
    current_worker = ""
    
    for dept_name, worker_name, tool, expiry in rows:
        if current_dept != dept_name:
            current_dept = dept_name
            report += f"\n🏢 **{escape_md(current_dept)}**\n"
            current_worker = ""
            
        if worker_name:
            if current_worker != worker_name:
                current_worker = worker_name
                report += f"  👤 {escape_md(current_worker)}:\n"
            if tool:
                report += f"    - {escape_md(tool)} (Muddati: {expiry})\n"
            else:
                report += "    - Biriktirilgan buyumlar yo'q\n"
        else:
            report += "  - Bo'limda ishchilar yo'q\n"

    if len(report) > 4000:
        chunks = []
        current = ""
        for line in report.split("\n"):
            if len(current) + len(line) + 1 > 4000:
                chunks.append(current)
                current = ""
            current += line + "\n"
        if current:
            chunks.append(current)
        for chunk in chunks:
            await message.answer(chunk, parse_mode="Markdown")
    else:
        await message.answer(report, parse_mode="Markdown")


# =====================================================================
# 🚀 MUDDATLARNI AVTOMATIK TEKSHIRISH VA OGOHLANTIRISH XIZMATI (SCHEDULER)
# =====================================================================
async def check_expirations_loop(bot: Bot):
    """Har 24 soatda ishchilarning asbob-uskunalarini tekshiradi va
    amal qilish muddati tugashiga 10, 5, 1 kun qolganda yoki tugagan kuni
    hamda o'tib ketgan bo'lsa ishchi va adminga shaxsiy xabar yuboradi."""
    while True:
        try:
            conn = sqlite3.connect('safety_bot.db')
            cursor = conn.cursor()
            cursor.execute('''
                SELECT t.tool_name, t.expiry_date, w.full_name, w.telegram_id, d.admin_telegram_id, d.name 
                FROM safety_tools t 
                JOIN workers w ON t.worker_id = w.id 
                JOIN departments d ON w.department_id = d.id
            ''')
            tools = cursor.fetchall()
            conn.close()

            today = datetime.now().date()

            for tool_name, expiry_str, worker_name, worker_tg_id, admin_tg_id, dept_name in tools:
                try:
                    expiry_date = datetime.strptime(expiry_str.strip(), '%Y-%m-%d').date()
                    days_left = (expiry_date - today).days

                    msg_worker = ""
                    msg_admin = ""

                    # Bildirishnoma shartlari
                    if days_left in [10, 5, 1]:
                        msg_worker = f"⚠️ *Yaqinda muddat tugaydi!*\n\nHurmatli *{worker_name}*, sizga biriktirilgan *{tool_name}* vositasi muddati tugashiga *{days_left} kun* qoldi.\n🗓 Muddat: `{expiry_str}`"
                        msg_admin = f"⚠️ *Xavfsizlik vositasi ogohlantirishi!*\n\n*{dept_name}* bo'limi ishchisi *{worker_name}* ga tegishli *{tool_name}* asbobining muddati tugashiga *{days_left} kun* qoldi.\n🗓 Muddat: `{expiry_str}`"
                    elif days_left == 0:
                        msg_worker = f"🚨 *MUHIM DIQQAT!*\n\nHurmatli *{worker_name}*, sizga biriktirilgan *{tool_name}* vositasining amal qilish muddati *BUGUN TUGADI*! Iltimos, undan foydalanmang va yangilang."
                        msg_admin = f"🚨 *MUHIM OGOHLANTIRISH!*\n\n*{dept_name}* bo'limi ishchisi *{worker_name}* ga tegishli *{tool_name}* asbobining muddati *BUGUN TUGADI*!"
                    elif days_left < 0:
                        # Muddat o'tib ketgan bo'lsa
                        msg_worker = f"❌ *XAVFLI VAZIYAT!*\n\nHurmatli *{worker_name}*, sizga tegishli *{tool_name}* asbobi muddati *{abs(days_left)} kun oldin o'tib ketgan!* Tezkorlik bilan almashtiring."
                        msg_admin = f"❌ *MUDDAT O'TIB KETGAN!*\n\n*{dept_name}* bo'limi ishchisi *{worker_name}* ga tegishli *{tool_name}* asbobi muddati *{abs(days_left)} kun oldin tugagan!*"

                    # Agar xabar shakllangan bo'lsa, uni yuboramiz
                    if msg_worker and worker_tg_id:
                        try:
                            await bot.send_message(chat_id=worker_tg_id, text=msg_worker, parse_mode="Markdown")
                        except Exception as e:
                            print(f"Ishchiga yuborishda xato ({worker_name}): {e}")

                    if msg_admin and admin_tg_id:
                        try:
                            await bot.send_message(chat_id=admin_tg_id, text=msg_admin, parse_mode="Markdown")
                        except Exception as e:
                            print(f"Adminga yuborishda xato ({dept_name}): {e}")

                except ValueError:
                    # Baza ichidagi sana formati YYYY-MM-DD bo'lmasa, xatoni o'tkazib yuborish
                    continue

        except Exception as err:
            print(f"Tekshirish loopida xatolik: {err}")

        # Tekshiruv kuniga 1 marta ishlaydi (86400 soniya)
        await asyncio.sleep(86400)


# =====================================================================
# 🌐 RENDER PORTINI TINGLOVCHI VEB SERVER (PORT BINDING)
# =====================================================================
async def handle_ping(request):
    """Render platformasi server yoniqligini tekshirish uchun yuboradigan so'rovga javob"""
    return web.Response(text="Bot is running smoothly!")

async def start_web_server():
    """Loyiha fonda Render talab qiladigan portni eshitib turishi uchun veb-server"""
    app = web.Application()
    app.router.add_get('/', handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    
    # Render avtomatik ravishda muhitdan PORT o'zgaruvchisini taqdim etadi (bepul tarifda odatda 10000 bo'ladi)
    port = int(os.environ.get("PORT", 8000))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"Veb-server muvaffaqiyatli ishga tushdi: http://0.0.0.0:{port}")


# =====================================================================
# 🏁 MAIN
# =====================================================================
async def main():
    init_db()
    dp.include_router(admin_router)
    
    # 1. Render portni yopib, loyihani Timed Out qilib tashlamasligi uchun veb serverni ishga tushiramiz
    await start_web_server()
    
    # 2. Orqa fonda avtomatik tekshiruvchini (scheduler) ishga tushirish
    asyncio.create_task(check_expirations_loop(bot))
    
    print("Bot va Avtomatik ogohlantirish xizmati muvaffaqiyatli ishga tushdi...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
