from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import sqlite3

router = Router()

def _escape_md(text: str) -> str:
    if text is None:
        return ""
    for ch in ("_", "*", "`", "["):
        text = text.replace(ch, f"\\{ch}")
    return text

class AdminStates(StatesGroup):
    waiting_for_login = State()
    admin_menu = State()
    adding_worker = State()
    selecting_worker_for_tool = State()
    adding_tool_name = State()
    adding_tool_expiry = State()
    deleting_worker = State()

def get_admin_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Yangi ishchi qo'shish"), KeyboardButton(text="❌ Ishchini o'chirish")],
            [KeyboardButton(text="🛠 Ishchiga buyum biriktirish")],
            [KeyboardButton(text="📊 Bo'lim hisoboti"), KeyboardButton(text="🚪 Chiqish")]
        ],
        resize_keyboard=True
    )

# Bosh menyuga qaytish uchun yordamchi funksiya (Aylanma import xatosini oldini oladi)
def get_main_keyboard_fallback(user_id, super_admin_id=8676940332):
    buttons = [
        [KeyboardButton(text="👤 Ishchi sifatida kirish")],
        [KeyboardButton(text="🔑 Bo'lim Admini (Login)")]
    ]
    if int(user_id) == super_admin_id:
        buttons.append([KeyboardButton(text="🌐 Barcha bo'limlarni ko'rish (Super Admin)")])
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

@router.message(F.text == "🔑 Bo'lim Admini (Login)")
async def admin_login_start(message: Message, state: FSMContext):
    await message.answer("Iltimos, login va parolingizni bo'shliq bilan ajratib yozing.\nMisol: `dep1_admin parol123`", parse_mode="Markdown")
    await state.set_state(AdminStates.waiting_for_login)

@router.message(AdminStates.waiting_for_login)
async def admin_login_verify(message: Message, state: FSMContext):
    try:
        login, password = message.text.split()
    except ValueError:
        await message.answer("Xato format! Login va parolni bitta bo'shliq bilan ajratib yozing:")
        return

    conn = sqlite3.connect('safety_bot.db')
    cursor = conn.cursor()
    cursor.execute('SELECT id, name FROM departments WHERE login=? AND password=?', (login, password))
    dept = cursor.fetchone()

    if dept:
        dept_id, dept_name = dept
        cursor.execute('UPDATE departments SET admin_telegram_id=? WHERE id=?', (message.from_user.id, dept_id))
        conn.commit()
        
        await state.update_data(dept_id=dept_id, dept_name=dept_name)
        await message.answer(f"🔓 Tizimga kirdingiz!\nBo'lim: {dept_name}", reply_markup=get_admin_keyboard())
        await state.set_state(AdminStates.admin_menu)
    else:
        await message.answer("❌ Login yoki parol xato. Qaytadan urinib ko'ring:")
    conn.close()

@router.message(AdminStates.admin_menu, F.text == "➕ Yangi ishchi qo'shish")
async def add_worker_start(message: Message, state: FSMContext):
    await message.answer("Yangi ishchining Ism va Familiyasini kiriting:")
    await state.set_state(AdminStates.adding_worker)

@router.message(AdminStates.adding_worker)
async def add_worker_save(message: Message, state: FSMContext):
    data = await state.get_data()
    dept_id = data.get('dept_id')
    worker_name = message.text
    
    conn = sqlite3.connect('safety_bot.db')
    cursor = conn.cursor()
    cursor.execute('INSERT INTO workers (full_name, department_id) VALUES (?, ?)', (worker_name, dept_id))
    conn.commit()
    conn.close()
    
    await message.answer(f"✅ Ishchi '{worker_name}' muvaffaqiyatli qo'shildi!", reply_markup=get_admin_keyboard())
    await state.set_state(AdminStates.admin_menu)

@router.message(AdminStates.admin_menu, F.text == "❌ Ishchini o'chirish")
async def delete_worker_start(message: Message, state: FSMContext):
    data = await state.get_data()
    dept_id = data.get('dept_id')

    conn = sqlite3.connect('safety_bot.db')
    cursor = conn.cursor()
    cursor.execute('SELECT id, full_name FROM workers WHERE department_id=?', (dept_id,))
    workers = cursor.fetchall()
    conn.close()

    if not workers:
        await message.answer("Bo'limda o'chirish uchun ishchilar yo'q.")
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"❌ {name}", callback_data=f"del_w_{w_id}")] for w_id, name in workers
    ])
    await message.answer("O'chirmoqchi bo'lgan ishchini tanlang (Diqqat: uning barcha vositalari ham o'chib ketadi!):", reply_markup=keyboard)
    await state.set_state(AdminStates.deleting_worker)

@router.callback_query(AdminStates.deleting_worker, F.data.startswith("del_w_"))
async def delete_worker_confirm(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    worker_id = int(callback.data.split("_")[2])
    
    conn = sqlite3.connect('safety_bot.db')
    cursor = conn.cursor()
    cursor.execute('DELETE FROM safety_tools WHERE worker_id=?', (worker_id,))
    cursor.execute('DELETE FROM workers WHERE id=?', (worker_id,))
    conn.commit()
    conn.close()

    await callback.message.edit_text("✅ Ishchi va unga tegishli barcha vositalar tizimdan o'chirildi!")
    await state.set_state(AdminStates.admin_menu)

@router.message(AdminStates.admin_menu, F.text == "🛠 Ishchiga buyum biriktirish")
async def select_worker_for_tool(message: Message, state: FSMContext):
    data = await state.get_data()
    dept_id = data.get('dept_id')

    conn = sqlite3.connect('safety_bot.db')
    cursor = conn.cursor()
    cursor.execute('SELECT id, full_name FROM workers WHERE department_id=?', (dept_id,))
    workers = cursor.fetchall()
    conn.close()

    if not workers:
        await message.answer("Bo'limingizda hali biror bir ishchi yo'q. Avval ishchi qo'shing!")
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=name, callback_data=f"select_w_{w_id}")] for w_id, name in workers
    ])
    await message.answer("Qaysi ishchiga buyum biriktirmoqchisiz? Tanlang:", reply_markup=keyboard)
    await state.set_state(AdminStates.selecting_worker_for_tool)

@router.callback_query(AdminStates.selecting_worker_for_tool, F.data.startswith("select_w_"))
async def get_tool_name_prompt(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    worker_id = int(callback.data.split("_")[2])
    await state.update_data(selected_worker_id=worker_id)
    await callback.message.edit_text("Ushbu ishchiga beriladigan xavfsizlik vositasi nomini kiriting:")
    await state.set_state(AdminStates.adding_tool_name)

@router.message(AdminStates.adding_tool_name)
async def get_tool_expiry_prompt(message: Message, state: FSMContext):
    await state.update_data(tool_name=message.text)
    await message.answer("Ushbu vositaning amal qilish muddatini kiriting:\nFormat: **YYYY-MM-DD** (Masalan: `2026-12-25`)", parse_mode="Markdown")
    await state.set_state(AdminStates.adding_tool_expiry)

@router.message(AdminStates.adding_tool_expiry)
async def save_tool(message: Message, state: FSMContext):
    expiry_date = message.text.strip()
    try:
        from datetime import datetime
        datetime.strptime(expiry_date, '%Y-%m-%d')
    except ValueError:
        await message.answer("⚠️ Sana formati noto'g'ri! Iltimos, **YYYY-MM-DD** shaklida kiriting:")
        return

    data = await state.get_data()
    worker_id = data.get('selected_worker_id')
    tool_name = data.get('tool_name')

    conn = sqlite3.connect('safety_bot.db')
    cursor = conn.cursor()
    cursor.execute('INSERT INTO safety_tools (worker_id, tool_name, expiry_date) VALUES (?, ?, ?)', (worker_id, tool_name, expiry_date))
    conn.commit()
    conn.close()

    await message.answer(f"✅ '{tool_name}' vositasi muvaffaqiyatli biriktirildi!", reply_markup=get_admin_keyboard())
    await state.set_state(AdminStates.admin_menu)

@router.message(AdminStates.admin_menu, F.text == "📊 Bo'lim hisoboti")
async def view_report(message: Message, state: FSMContext):
    data = await state.get_data()
    dept_id = data.get('dept_id')
    
    conn = sqlite3.connect('safety_bot.db')
    cursor = conn.cursor()
    cursor.execute('''
        SELECT w.full_name, t.tool_name, t.expiry_date 
        FROM workers w
        LEFT JOIN safety_tools t ON w.id = t.worker_id
        WHERE w.department_id = ?
    ''', (dept_id,))
    rows = cursor.fetchall()
    conn.close()
    
    if not rows:
        await message.answer("Bu bo'limda hali ishchilar mavjud emas.")
        return
        
    report = "📋 **Bo'lim bo'yicha xavfsizlik vositalari hisoboti:**\n"
    current_worker = ""
    for worker_name, tool, expiry in rows:
        if current_worker != worker_name:
            current_worker = worker_name
            report += f"\n👤 **{_escape_md(current_worker)}**:\n"
        if tool:
            report += f"  - {_escape_md(tool)} (Muddati: {expiry})\n"
        else:
            report += "  - Biriktirilgan buyumlar yo'q\n"
            
    await message.answer(report, parse_mode="Markdown")

@router.message(AdminStates.admin_menu, F.text == "🚪 Chiqish")
async def exit_admin(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Admin paneldan chiqdingiz. Bosh menyu.",
        reply_markup=get_main_keyboard_fallback(message.from_user.id)
    )