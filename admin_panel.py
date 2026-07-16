from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import sqlite3
from datetime import datetime

router = Router()

# 3 ta Super Adminlar ID ro'yxati
SUPER_ADMIN_IDS = [8676940332, 123456789, 987654321]  # O'zingizga kerakli IDlarni yozasiz

def _escape_md(text: str) -> str:
    if text is None:
        return ""
    for ch in ("_", "*", "`", "["):
        text = text.replace(ch, f"\\{ch}")
    return text

class AdminStates(StatesGroup):
    waiting_for_login = State()
    admin_menu = State()
    
    # Super Admin uchun maxsus
    selecting_dept_to_manage = State()
    
    # Ishchi boshqaruvi
    adding_worker = State()
    deleting_worker = State()
    
    # Himoya vositasi boshqaruvi
    adding_tool_name = State()
    adding_tool_expiry = State()
    selecting_tool_to_update = State()
    updating_tool_expiry = State()

def get_admin_keyboard(is_super=False):
    buttons = [
        [KeyboardButton(text="➕ Yangi ishchi qo'shish"), KeyboardButton(text="❌ Ishchini o'chirish")],
        [KeyboardButton(text="🛠 Bo'limga buyum biriktirish"), KeyboardButton(text="🔄 Vosita muddatini yangilash")],
        [KeyboardButton(text="📊 Bo'lim hisoboti"), KeyboardButton(text="🚪 Chiqish")]
    ]
    if is_super:
        buttons.insert(0, [KeyboardButton(text="🏢 Bo'limni o'zgartirish (Super Admin)")])
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_main_keyboard_fallback(user_id):
    buttons = [
        [KeyboardButton(text="👤 Ishchi sifatida kirish")],
        [KeyboardButton(text="🔑 Bo'lim Admini (Login)")],
        [KeyboardButton(text="👁 Mehmon / Tekshiruvchi kirishi")]
    ]
    if int(user_id) in SUPER_ADMIN_IDS:
        buttons.append([KeyboardButton(text="👑 Super Admin Paneli")])
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)


# --- SUPER ADMIN MENYUSI ---
@router.message(F.text == "👑 Super Admin Paneli")
async def super_admin_panel_start(message: Message, state: FSMContext):
    if message.from_user.id not in SUPER_ADMIN_IDS:
        await message.answer("Sizda super admin huquqi yo'q.")
        return
        
    await state.clear()
    
    conn = sqlite3.connect('safety_bot.db')
    cursor = conn.cursor()
    cursor.execute('SELECT id, name FROM departments')
    depts = cursor.fetchall()
    conn.close()
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=name, callback_data=f"manage_dept_{d_id}")] for d_id, name in depts
    ])
    
    await message.answer("👑 **Super Admin Paneli.**\nBoshqarish uchun 7 ta bo'limdan birini tanlang:", reply_markup=keyboard)
    await state.set_state(AdminStates.selecting_dept_to_manage)


@router.callback_query(AdminStates.selecting_dept_to_manage, F.data.startswith("manage_dept_"))
async def super_admin_dept_selected(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    dept_id = int(callback.data.split("_")[2])
    
    conn = sqlite3.connect('safety_bot.db')
    cursor = conn.cursor()
    cursor.execute('SELECT name FROM departments WHERE id=?', (dept_id,))
    dept_name = cursor.fetchone()[0]
    conn.close()
    
    await state.update_data(dept_id=dept_id, dept_name=dept_name, is_super=True)
    await callback.message.answer(
        f"⚙️ Siz **{dept_name}** bo'limi boshqaruvchisiz (Super Admin vakolati bilan).", 
        reply_markup=get_admin_keyboard(is_super=True)
    )
    await state.set_state(AdminStates.admin_menu)


@router.message(AdminStates.admin_menu, F.text == "🏢 Bo'limni o'zgartirish (Super Admin)")
async def change_dept_super(message: Message, state: FSMContext):
    data = await state.get_data()
    if not data.get('is_super'):
        await message.answer("Sizda bunday ruxsat yo'q.")
        return
    await super_admin_panel_start(message, state)


# --- ODDIY ADMIN LOGIN JARAYONI ---
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
        
        await state.update_data(dept_id=dept_id, dept_name=dept_name, is_super=False)
        await message.answer(f"🔓 Tizimga kirdingiz!\nBo'lim: {dept_name}", reply_markup=get_admin_keyboard(is_super=False))
        await state.set_state(AdminStates.admin_menu)
    else:
        await message.answer("❌ Login yoki parol xato. Qaytadan urinib ko'ring:")
    conn.close()


# --- ISHCHI QO'SHISH ---
@router.message(AdminStates.admin_menu, F.text == "➕ Yangi ishchi qo'shish")
async def add_worker_start(message: Message, state: FSMContext):
    await message.answer("Yangi ishchining Ism va Familiyasini kiriting:")
    await state.set_state(AdminStates.adding_worker)

@router.message(AdminStates.adding_worker)
async def add_worker_save(message: Message, state: FSMContext):
    data = await state.get_data()
    dept_id = data.get('dept_id')
    is_super = data.get('is_super', False)
    worker_name = message.text
    
    conn = sqlite3.connect('safety_bot.db')
    cursor = conn.cursor()
    cursor.execute('INSERT INTO workers (full_name, department_id) VALUES (?, ?)', (worker_name, dept_id))
    conn.commit()
    conn.close()
    
    await message.answer(f"✅ Ishchi '{worker_name}' muvaffaqiyatli qo'shildi!", reply_markup=get_admin_keyboard(is_super))
    await state.set_state(AdminStates.admin_menu)


# --- ISHCHINI O'CHIRISH ---
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
        await message.answer("Ushbu bo'limda o'chirish uchun ishchilar yo'q.")
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"❌ {name}", callback_data=f"del_w_{w_id}")] for w_id, name in workers
    ])
    await message.answer("O'chirmoqchi bo'lgan ishchini tanlang:", reply_markup=keyboard)
    await state.set_state(AdminStates.deleting_worker)

@router.callback_query(AdminStates.deleting_worker, F.data.startswith("del_w_"))
async def delete_worker_confirm(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    worker_id = int(callback.data.split("_")[2])
    data = await state.get_data()
    is_super = data.get('is_super', False)
    
    conn = sqlite3.connect('safety_bot.db')
    cursor = conn.cursor()
    cursor.execute('DELETE FROM workers WHERE id=?', (worker_id,))
    conn.commit()
    conn.close()

    await callback.message.edit_text("✅ Ishchi tizimdan muvaffaqiyatli o'chirildi!")
    await state.set_state(AdminStates.admin_menu)


# --- BO'LIMGA BUYUM BIRIKTIRISH (YANGI LOGIKA) ---
@router.message(AdminStates.admin_menu, F.text == "🛠 Bo'limga buyum biriktirish")
async def add_tool_to_dept_start(message: Message, state: FSMContext):
    await message.answer("Ushbu bo'limga biriktiriladigan xavfsizlik vositasi nomini kiriting (Masalan: `Kaska`, `Kabel`):")
    await state.set_state(AdminStates.adding_tool_name)

@router.message(AdminStates.adding_tool_name)
async def add_tool_to_dept_expiry(message: Message, state: FSMContext):
    await state.update_data(tool_name=message.text)
    await message.answer("Ushbu vositaning amal qilish muddatini kiriting:\nFormat: **YYYY-MM-DD** (Masalan: `2026-12-25`)", parse_mode="Markdown")
    await state.set_state(AdminStates.adding_tool_expiry)

@router.message(AdminStates.adding_tool_expiry)
async def save_tool_to_dept(message: Message, state: FSMContext):
    expiry_date = message.text.strip()
    try:
        datetime.strptime(expiry_date, '%Y-%m-%d')
    except ValueError:
        await message.answer("⚠️ Sana formati noto'g'ri! Iltimos, **YYYY-MM-DD** shaklida kiriting:")
        return

    data = await state.get_data()
    dept_id = data.get('dept_id')
    tool_name = data.get('tool_name')
    is_super = data.get('is_super', False)

    conn = sqlite3.connect('safety_bot.db')
    cursor = conn.cursor()
    cursor.execute('INSERT INTO safety_tools (department_id, tool_name, expiry_date) VALUES (?, ?, ?)', (dept_id, tool_name, expiry_date))
    conn.commit()
    conn.close()

    await message.answer(f"✅ '{tool_name}' vositasi butun bo'limga muvaffaqiyatli biriktirildi!", reply_markup=get_admin_keyboard(is_super))
    await state.set_state(AdminStates.admin_menu)


# --- VOSITA MUDDATINI YANGILASH ---
@router.message(AdminStates.admin_menu, F.text == "🔄 Vosita muddatini yangilash")
async def update_tool_expiry_start(message: Message, state: FSMContext):
    data = await state.get_data()
    dept_id = data.get('dept_id')

    conn = sqlite3.connect('safety_bot.db')
    cursor = conn.cursor()
    cursor.execute('SELECT id, tool_name, expiry_date FROM safety_tools WHERE department_id=?', (dept_id,))
    tools = cursor.fetchall()
    conn.close()

    if not tools:
        await message.answer("Ushbu bo'limda hech qanday vosita yo'q. Avval buyum biriktiring!")
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🔄 {name} (Eski: {exp})", callback_data=f"up_t_{t_id}")] for t_id, name, exp in tools
    ])
    await message.answer("Qaysi xavfsizlik vositasining muddatini yangilamoqchisiz? Tanlang:", reply_markup=keyboard)
    await state.set_state(AdminStates.selecting_tool_to_update)

@router.callback_query(AdminStates.selecting_tool_to_update, F.data.startswith("up_t_"))
async def update_tool_expiry_prompt(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    tool_id = int(callback.data.split("_")[2])
    await state.update_data(selected_tool_id=tool_id)
    await callback.message.edit_text("Yangi muddatni kiriting:\nFormat: **YYYY-MM-DD** (Masalan: `2027-06-15`)")
    await state.set_state(AdminStates.updating_tool_expiry)

@router.message(AdminStates.updating_tool_expiry)
async def update_tool_expiry_save(message: Message, state: FSMContext):
    new_expiry = message.text.strip()
    try:
        datetime.strptime(new_expiry, '%Y-%m-%d')
    except ValueError:
        await message.answer("⚠️ Sana formati noto'g'ri! Iltimos, **YYYY-MM-DD** shaklida kiriting:")
        return

    data = await state.get_data()
    tool_id = data.get('selected_tool_id')
    is_super = data.get('is_super', False)

    conn = sqlite3.connect('safety_bot.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE safety_tools SET expiry_date=? WHERE id=?', (new_expiry, tool_id))
    conn.commit()
    conn.close()

    await message.answer("✅ Vosita muddati muvaffaqiyatli yangilandi!", reply_markup=get_admin_keyboard(is_super))
    await state.set_state(AdminStates.admin_menu)


# --- BO'LIM HISOBOTI ---
@router.message(AdminStates.admin_menu, F.text == "📊 Bo'lim hisoboti")
async def view_report(message: Message, state: FSMContext):
    data = await state.get_data()
    dept_id = data.get('dept_id')
    dept_name = data.get('dept_name')
    
    conn = sqlite3.connect('safety_bot.db')
    cursor = conn.cursor()
    cursor.execute('SELECT full_name FROM workers WHERE department_id=?', (dept_id,))
    workers = cursor.fetchall()
    cursor.execute('SELECT tool_name, expiry_date FROM safety_tools WHERE department_id=?', (dept_id,))
    tools = cursor.fetchall()
    conn.close()
    
    report = f"📋 **{_escape_md(dept_name)} - Bo'limi Hisoboti:**\n\n"
    
    # Bo'limdagi barcha vositalar
    report += "🛠 **Bo'limga biriktirilgan xavfsizlik vositalari:**\n"
    if not tools:
        report += "  - Biriktirilgan vositalar yo'q\n"
    else:
        for t_name, exp in tools:
            report += f"  • {t_name} (Muddat: `{exp}`)\n"
            
    report += "\n👤 **Bo'lim ishchilari ro'yxati:**\n"
    if not workers:
        report += "  - Bo'limda ishchilar ro'yxatdan o'tmagan\n"
    else:
        for w in workers:
            report += f"  - {w[0]}\n"
            
    await message.answer(report, parse_mode="Markdown")


# --- CHIQUVCHI ---
@router.message(AdminStates.admin_menu, F.text == "🚪 Chiqish")
async def exit_admin(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Admin paneldan chiqdingiz. Bosh menyu.",
        reply_markup=get_main_keyboard_fallback(message.from_user.id)
    )
