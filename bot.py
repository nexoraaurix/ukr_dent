import asyncio
import logging
import os
import json
import re
from datetime import datetime, timedelta
from aiohttp import web
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

# ==========================================
# НАСТРОЙКИ
# ==========================================
BOT_TOKEN = "9080785576:AAF3vuF-fK1IhMpp56imPClN3qGXPGhUUhI"
ADMIN_CHAT_ID = 5187923987
GOOGLE_MAPS_REVIEW_URL = "https://maps.google.com/?q=Київ,вул.Хрещатик,15" 

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ==========================================
# БАЗА ДАННЫХ (JSON)
# ==========================================
DB_FILE = "booked.json"
CLOSED_DAYS_FILE = "closed_days.json"
APPOINTMENTS_FILE = "appointments.json"
USERS_FILE = "users.json"

def load_json(filename, default):
    if not os.path.exists(filename):
        return default
    with open(filename, "r", encoding="utf-8") as f:
        return json.load(f)

def save_json(filename, data):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def is_time_booked(date, time):
    booked = load_json(DB_FILE, {})
    return time in booked.get(date, [])

def is_day_closed(date):
    closed = load_json(CLOSED_DAYS_FILE, {})
    return date in closed

def book_time(date, time):
    booked = load_json(DB_FILE, {})
    if date not in booked:
        booked[date] = []
    booked[date].append(time)
    save_json(DB_FILE, booked)

def unbook_time(date, time):
    booked = load_json(DB_FILE, {})
    if date in booked and time in booked[date]:
        booked[date].remove(time)
        save_json(DB_FILE, booked)

def add_appointment(chat_id, name, phone, service, doctor, date, time):
    appointments = load_json(APPOINTMENTS_FILE, [])
    appointments.append({
        "chat_id": chat_id, "name": name, "phone": phone, 
        "service": service, "doctor": doctor, "date": date, "time": time,
        "notified": False, "review_sent": False
    })
    save_json(APPOINTMENTS_FILE, appointments)

def get_user(user_id):
    users = load_json(USERS_FILE, {})
    return users.get(str(user_id))

def save_user(user_id, name, phone):
    users = load_json(USERS_FILE, {})
    users[str(user_id)] = {"name": name, "phone": phone}
    save_json(USERS_FILE, users)

# ==========================================
# СОСТОЯНИЯ (FSM)
# ==========================================
class BookingForm(StatesGroup):
    service = State()
    doctor = State()
    date = State()
    time = State()
    name = State()
    phone = State()
    confirm = State()

class EmergencyForm(StatesGroup):
    phone = State()

# ==========================================
# КЛАВИАТУРЫ
# ==========================================
def get_main_menu():
    kb = [
        [KeyboardButton(text="🚨 У мене гострий біль!")],
        [KeyboardButton(text="🤔 Допоможіть обрати послугу")],
        [KeyboardButton(text="🦷 Записатися на прийом")],
        [KeyboardButton(text="💰 Послуги та ціни"), KeyboardButton(text="👨‍⚕️ Наші лікарі")],
        [KeyboardButton(text="📍 Як дістатися"), KeyboardButton(text="📞 Контакти")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_services_inline():
    kb = [
        [InlineKeyboardButton(text="Консультація (Безкоштовно)", callback_data="srv_consult")],
        [InlineKeyboardButton(text="Лікування карієсу (від 1200 грн)", callback_data="srv_caries")],
        [InlineKeyboardButton(text="Професійна чистка (900 грн)", callback_data="srv_clean")],
        [InlineKeyboardButton(text="Імплантація (від 15000 грн)", callback_data="srv_implant")],
        [InlineKeyboardButton(text="Брекети (від 25000 грн)", callback_data="srv_braces")],
        [InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="back_to_main")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def get_doctors_inline():
    kb = [
        [InlineKeyboardButton(text="Терапевт (Олег Іванов)", callback_data="doc_therapist")],
        [InlineKeyboardButton(text="Ортодонт (Марія Петрівна)", callback_data="doc_ortho")],
        [InlineKeyboardButton(text="Хірург-імплантолог (Андрій В.)", callback_data="doc_surgeon")],
        [InlineKeyboardButton(text="Будь-який лікар", callback_data="doc_any")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_main")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def get_dates_inline():
    kb = []
    today = datetime.now()
    months = ["Січ", "Лют", "Бер", "Кві", "Тра", "Чер", "Лип", "Сер", "Вер", "Жов", "Лис", "Гру"]
    weekdays = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Нд"]
    for i in range(1, 8):
        date = today + timedelta(days=i)
        date_str = date.strftime("%d.%m.%Y")
        if is_day_closed(date_str): continue
        wd = weekdays[date.weekday()]
        month = months[date.month - 1]
        kb.append([InlineKeyboardButton(text=f"{wd}, {date.day} {month}", callback_data=f"date_{date_str}")])
    if not kb:
         kb.append([InlineKeyboardButton(text="❌ Немає вільних днів", callback_data="no_times")])
    kb.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_main")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def get_time_inline(date):
    times = ["09:00", "10:00", "11:00", "12:00", "14:00", "15:00", "16:00", "17:00"]
    kb = []
    row = []
    for t in times:
        if not is_time_booked(date, t):
            row.append(InlineKeyboardButton(text=t, callback_data=f"time_{t}"))
            if len(row) == 2:
                kb.append(row)
                row = []
    if row: kb.append(row)
    if not kb:
        kb.append([InlineKeyboardButton(text="❌ На цей день всі місця зайняті", callback_data="no_times")])
    kb.append([InlineKeyboardButton(text="⬅️ Назад до дат", callback_data="back_to_dates")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def get_confirm_inline():
    kb = [
        [InlineKeyboardButton(text="✅ Все вірно, записати", callback_data="confirm_yes")],
        [InlineKeyboardButton(text="❌ Скасувати", callback_data="confirm_no")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def get_phone_keyboard():
    kb = [[KeyboardButton(text="📱 Поділитися номером", request_contact=True)]]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True, one_time_keyboard=True)

def get_saved_user_inline(name):
    kb = [
        [InlineKeyboardButton(text=f"✅ Я {name}, все вірно", callback_data="user_yes")],
        [InlineKeyboardButton(text="✏️ Ввести інші дані", callback_data="user_no")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def get_quiz_inline():
    kb = [
        [InlineKeyboardButton(text="😣 Біль або запалення", callback_data="quiz_pain")],
        [InlineKeyboardButton(text="😬 Естетика (колір, форма)", callback_data="quiz_aesthetic")],
        [InlineKeyboardButton(text="🔧 Відсутність зуба", callback_data="quiz_missing")],
        [InlineKeyboardButton(text="🦷 Нерівні зуби", callback_data="quiz_uneven")],
        [InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="back_to_main")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

# ==========================================
# УМНЫЙ КОНСУЛЬТАНТ (КВИЗ)
# ==========================================
@dp.message(F.text == "🤔 Допоможіть обрати послугу")
async def start_quiz(message: Message, state: FSMContext):
    await message.answer(
        "Давайте підберемо оптимальне рішення!\n\nЩо вас турбує найбільше?",
        reply_markup=get_quiz_inline()
    )

@dp.callback_query(F.data.startswith("quiz_"))
async def process_quiz(callback: CallbackQuery, state: FSMContext):
    quiz_type = callback.data.split("_")[1]
    await callback.message.delete()

    if quiz_type == "pain":
        text = "Зрозуміло. Найкраще рішення — <b>Консультація терапевта</b>.\nЛікар огляне, визначить причину болю та складе план лікування.\n\nБажаєте записатися до терапевта Олега Іванова?"
        await state.update_data(service="Консультація", doctor="Олег Іванов (Терапевт)")
    elif quiz_type == "aesthetic":
        text = "Зрозуміло. Для покращення естетики рекомендуємо <b>Професійну чистку</b> та консультацію терапевта.\nЦе видалить наліт, поверне природній колір та свіжість.\n\nБажаєте записатися на чистку?"
        await state.update_data(service="Професійна чистка", doctor="Будь-який лікар")
    elif quiz_type == "missing":
        text = "Зрозуміло. Найкращим рішенням буде <b>Імплантація</b>.\nЦе дозволить відновити жувальну функцію та захистити сусідні зуби.\nУ нас цим займається хірург-імплантолог Андрій В. (стаж 10 років).\n\nБажаєте записатися на консультацію до Андрія?"
        await state.update_data(service="Імплантація", doctor="Андрій В. (Хірург)")
    elif quiz_type == "uneven":
        text = "Зрозуміло. Для вирівнювання зубів рекомендуємо <b>Брекети</b>.\nНаш ортодонт Марія Петрівна (стаж 12 років) підбере оптимальну систему.\n\nБажаєте записатися на консультацію до Марії?"
        await state.update_data(service="Брекети", doctor="Марія Петрівна (Ортодонт)")

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Записатися", callback_data="quiz_confirm")],
        [InlineKeyboardButton(text="⬅️ Назад до вибору", callback_data="quiz_back")]
    ])
    await callback.message.answer(text, parse_mode="HTML", reply_markup=kb)
    await callback.answer()

@dp.callback_query(F.data == "quiz_back")
async def quiz_back(callback: CallbackQuery):
    await callback.message.delete()
    await callback.message.answer("Що вас турбує найбільше?", reply_markup=get_quiz_inline())
    await callback.answer()

@dp.callback_query(F.data == "quiz_confirm")
async def quiz_confirm(callback: CallbackQuery, state: FSMContext):
    await callback.message.delete()
    
    # ВАЖНО: Переводим бота в состояние выбора даты, чтобы он ждал нажатия на кнопку!
    await state.set_state(BookingForm.date)
    
    data = await state.get_data()
    await callback.message.answer(
        f"Ви обрали: <b>{data['service']}</b> (Лікар: {data['doctor']}).\n\n"
        f"Крок 1 з 3. Оберіть бажану дату:",
        parse_mode="HTML",
        reply_markup=get_dates_inline()
    )
    await callback.answer()

# ==========================================
# АДМИН-ПАНЕЛЬ
# ==========================================
@dp.message(Command("admin"))
async def cmd_admin(message: Message):
    if message.from_user.id != ADMIN_CHAT_ID:
        return
    kb = [
        [InlineKeyboardButton(text="📊 Записи на сьогодні", callback_data="admin_today")],
        [InlineKeyboardButton(text="📅 Закрити день (вихідний)", callback_data="admin_close_day")]
    ]
    await message.answer("👋 Вітаю, Адміне!", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data == "admin_today")
async def admin_today(callback: CallbackQuery):
    today = datetime.now().strftime("%d.%m.%Y")
    appointments = load_json(APPOINTMENTS_FILE, [])
    today_apps = [a for a in appointments if a["date"] == today]
    if not today_apps:
        await callback.message.answer(f"На {today} записів немає.")
        return
    text = f"📊 <b>Записи на {today}:</b>\n\n"
    for a in today_apps:
        text += f"🕐 {a['time']} — {a['name']} ({a['service']})\n📱 {a['phone']}\n\n"
    await callback.message.answer(text, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "admin_close_day")
async def admin_close_day(callback: CallbackQuery):
    kb = []
    today = datetime.now()
    months = ["Січ", "Лют", "Бер", "Кві", "Тра", "Чер", "Лип", "Сер", "Вер", "Жов", "Лис", "Гру"]
    weekdays = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Нд"]
    for i in range(1, 8):
        date = today + timedelta(days=i)
        date_str = date.strftime("%d.%m.%Y")
        if is_day_closed(date_str): continue
        wd = weekdays[date.weekday()]
        month = months[date.month - 1]
        kb.append([InlineKeyboardButton(text=f"{wd}, {date.day} {month}", callback_data=f"close_{date_str}")])
    await callback.message.edit_text("Оберіть день, який хочете закрити:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await callback.answer()

@dp.callback_query(F.data.startswith("close_"))
async def process_close_day(callback: CallbackQuery):
    date_str = callback.data.split("_")[1]
    closed = load_json(CLOSED_DAYS_FILE, {})
    closed[date_str] = True
    save_json(CLOSED_DAYS_FILE, closed)
    await callback.message.edit_text(f"✅ День {date_str} закрито.")
    await callback.answer()

# ==========================================
# СРОЧНАЯ ПОМОЩЬ (С ВОЗМОЖНОСТЬЮ ВВОДА ТЕКСТОМ)
# ==========================================
@dp.message(F.text == "🚨 У мене гострий біль!")
async def start_emergency(message: Message, state: FSMContext):
    await state.set_state(EmergencyForm.phone)
    await message.answer(
        "Зрозуміло! Залиште свій номер телефону (натисніть кнопку нижче або напишіть вручну), і адміністратор зателефонує вам протягом 5 хвилин.",
        reply_markup=get_phone_keyboard()
    )

@dp.message(EmergencyForm.phone, F.contact)
async def process_emergency_contact(message: Message, state: FSMContext):
    phone = message.contact.phone_number
    if not phone.startswith("+"): phone = "+" + phone
    await state.clear()
    admin_text = f"🚨🚨🚨 <b>ТЕРМІНОВА ЗАЯВКА!</b> 🚨🚨🚨\n\nПацієнт скаржиться на <b>гострий біль</b>!\n📱 Телефон: <b>{phone}</b>\n👤 Telegram: @{message.from_user.username}"
    await bot.send_message(ADMIN_CHAT_ID, admin_text, parse_mode="HTML")
    await message.answer("✅ <b>Ваш номер передано адміністратору!</b>\n\nМи зателефонуємо вам найближчим часом.", parse_mode="HTML", reply_markup=get_main_menu())

@dp.message(EmergencyForm.phone, F.text)
async def process_emergency_text(message: Message, state: FSMContext):
    # Если пациент ввел номер текстом (проверяем, чтобы было хотя бы 10 цифр)
    text = message.text.strip()
    if len(re.sub(r'\D', '', text)) < 10:
        await message.answer("❌ Будь ласка, введіть коректний номер телефону (наприклад, +380991234567) або натисніть кнопку.")
        return
        
    await state.clear()
    admin_text = f"🚨🚨🚨 <b>ТЕРМІНОВА ЗАЯВКА!</b> 🚨🚨🚨\n\nПацієнт скаржиться на <b>гострий біль</b>!\n📱 Телефон: <b>{text}</b>\n👤 Telegram: @{message.from_user.username}"
    await bot.send_message(ADMIN_CHAT_ID, admin_text, parse_mode="HTML")
    await message.answer("✅ <b>Ваш номер передано адміністратору!</b>\n\nМи зателефонуємо вам найближчим часом.", parse_mode="HTML", reply_markup=get_main_menu())

# ==========================================
# ОБРАБОТКА КОМАНД И МЕНЮ
# ==========================================
@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(f"Вітаємо у стоматології «UkrDent»! 🦷\n\nОберіть потрібний пункт у меню нижче 👇", reply_markup=get_main_menu())

@dp.message(F.text == "💰 Послуги та ціни")
async def show_prices(message: Message):
    await message.answer("💰 <b>Наш прайс-лист:</b>\n\n• Консультація — <b>Безкоштовно</b>\n• Лікування карієсу — <b>від 1200 грн</b>\n• Професійна чистка — <b>900 грн</b>\n• Імплантація — <b>від 15000 грн</b>\n• Брекети — <b>від 25000 грн</b>", parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🦷 Записатися", callback_data="start_booking")]]))

@dp.message(F.text == "👨‍⚕️ Наші лікарі")
async def show_doctors(message: Message):
    await message.answer("👨‍⚕️ <b>Наша команда:</b>\n\n1️⃣ <b>Олег Іванов</b> — терапевт.\n2️⃣ <b>Марія Петрівна</b> — ортодонт.\n3️⃣ <b>Андрій В.</b> — хірург-імплантолог.", parse_mode="HTML")

@dp.message(F.text == "📍 Як дістатися")
async def show_location(message: Message):
    await message.answer("📍 м. Київ, вул. Хрещатик, 15 (2 поверх)\n🕐 Пн–Пт: 09:00 – 19:00", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🗺 Google Maps", url=GOOGLE_MAPS_REVIEW_URL)]]))

@dp.message(F.text.contains("Контакти") | F.text.contains("📞"))
async def show_contacts(message: Message):
    await message.answer("📞 <b>Контакти:</b>\n\nТелефон адміністратора: +38 (044) 123-45-67\nViber: +38 (067) 123-45-67", parse_mode="HTML")

# ==========================================
# ЛОГИКА ЗАПИСИ
# ==========================================
@dp.callback_query(F.data == "start_booking")
async def start_booking_cb(callback: CallbackQuery, state: FSMContext):
    await callback.message.delete()
    user = get_user(callback.from_user.id)
    if user:
        await state.update_data(saved_name=user['name'], saved_phone=user['phone'])
        await callback.message.answer(f"Вітаємо знову, <b>{user['name']}</b>! Бажаєте записатися знову на ці ж дані?", parse_mode="HTML", reply_markup=get_saved_user_inline(user['name']))
    else:
        await state.set_state(BookingForm.service)
        await callback.message.answer("Крок 1 з 5. Оберіть послугу:", reply_markup=get_services_inline())
    await callback.answer()

@dp.message(F.text == "🦷 Записатися на прийом")
async def start_booking_text(message: Message, state: FSMContext):
    user = get_user(message.from_user.id)
    if user:
        await state.update_data(saved_name=user['name'], saved_phone=user['phone'])
        await message.answer(f"Вітаємо знову, <b>{user['name']}</b>! Бажаєте записатися знову?", parse_mode="HTML", reply_markup=get_saved_user_inline(user['name']))
    else:
        await state.set_state(BookingForm.service)
        await message.answer("Крок 1 з 5. Оберіть послугу:", reply_markup=get_services_inline())

@dp.callback_query(F.data == "user_yes")
async def process_user_yes(callback: CallbackQuery, state: FSMContext):
    await callback.message.delete()
    await state.set_state(BookingForm.service)
    await callback.message.answer("Крок 1 з 5. Оберіть послугу:", reply_markup=get_services_inline())
    await callback.answer()

@dp.callback_query(F.data == "user_no")
async def process_user_no(callback: CallbackQuery, state: FSMContext):
    await state.update_data(saved_name=None, saved_phone=None)
    await callback.message.delete()
    await state.set_state(BookingForm.service)
    await callback.message.answer("Крок 1 з 5. Оберіть послугу:", reply_markup=get_services_inline())
    await callback.answer()

@dp.callback_query(BookingForm.service)
async def process_service(callback: CallbackQuery, state: FSMContext):
    if callback.data == "back_to_main":
        await state.clear()
        await callback.message.delete()
        await callback.message.answer("Головне меню:", reply_markup=get_main_menu())
        return
    services = {"srv_consult": "Консультація", "srv_caries": "Лікування карієсу", "srv_clean": "Професійна чистка", "srv_implant": "Імплантація", "srv_braces": "Брекети"}
    selected = services.get(callback.data)
    await state.update_data(service=selected)
    await callback.message.delete()
    await state.set_state(BookingForm.doctor)
    await callback.message.answer(f"Ви обрали: <b>{selected}</b>.\n\nКрок 2 з 5. Оберіть лікаря:", parse_mode="HTML", reply_markup=get_doctors_inline())
    await callback.answer()

@dp.callback_query(BookingForm.doctor)
async def process_doctor(callback: CallbackQuery, state: FSMContext):
    if callback.data == "back_to_main":
        await state.clear()
        await callback.message.delete()
        await callback.message.answer("Головне меню:", reply_markup=get_main_menu())
        return
    doctors = {"doc_therapist": "Олег Іванов (Терапевт)", "doc_ortho": "Марія Петрівна (Ортодонт)", "doc_surgeon": "Андрій В. (Хірург)", "doc_any": "Будь-який лікар"}
    selected = doctors.get(callback.data)
    await state.update_data(doctor=selected)
    await callback.message.delete()
    await state.set_state(BookingForm.date)
    await callback.message.answer(f"Ви обрали лікаря: <b>{selected}</b>.\n\nКрок 3 з 5. Оберіть дату:", parse_mode="HTML", reply_markup=get_dates_inline())
    await callback.answer()

@dp.callback_query(BookingForm.date, F.data == "back_to_dates")
async def back_to_dates(callback: CallbackQuery, state: FSMContext):
    await callback.message.delete()
    await callback.message.answer("Крок 3 з 5. Оберіть дату:", reply_markup=get_dates_inline())
    await callback.answer()

@dp.callback_query(BookingForm.date)
async def process_date(callback: CallbackQuery, state: FSMContext):
    if callback.data == "back_to_main":
        await state.clear()
        await callback.message.delete()
        await callback.message.answer("Головне меню:", reply_markup=get_main_menu())
        return
    date_str = callback.data.split("_")[1]
    await state.update_data(date=date_str)
    await callback.message.delete()
    await state.set_state(BookingForm.time)
    await callback.message.answer(f"Ви обрали дату: <b>{date_str}</b>.\n\nКрок 4 з 5. Оберіть час:", parse_mode="HTML", reply_markup=get_time_inline(date_str))
    await callback.answer()

@dp.callback_query(BookingForm.time, F.data == "no_times")
async def no_times(callback: CallbackQuery):
    await callback.answer("На жаль, на цей день всі місця зайняті.", show_alert=True)

@dp.callback_query(BookingForm.time)
async def process_time(callback: CallbackQuery, state: FSMContext):
    if callback.data == "back_to_dates":
        await callback.message.delete()
        await callback.message.answer("Крок 3 з 5. Оберіть дату:", reply_markup=get_dates_inline())
        return
    if callback.data == "back_to_main":
        await state.clear()
        await callback.message.delete()
        await callback.message.answer("Головне меню:", reply_markup=get_main_menu())
        return
    selected_time = callback.data.split("_")[1]
    await state.update_data(time=selected_time)
    await callback.message.delete()
    data = await state.get_data()
    if data.get('saved_name') and data.get('saved_phone'):
        await state.set_state(BookingForm.confirm)
        summary = f"📋 <b>Перевірте ваші дані:</b>\n\n👤 Ім'я: {data['saved_name']}\n📱 Телефон: {data['saved_phone']}\n🦷 Послуга: {data['service']}\n👨‍⚕️ Лікар: {data['doctor']}\n📅 Дата: {data['date']}\n🕐 Час: {data['time']}\n\nВсе вірно?"
        await callback.message.answer(summary, parse_mode="HTML", reply_markup=get_confirm_inline())
    else:
        await state.set_state(BookingForm.name)
        await callback.message.answer(f"Час: <b>{selected_time}</b>.\n\nКрок 5 з 5. Як вас звати? (Ім'я та Прізвище)", parse_mode="HTML")
    await callback.answer()

@dp.message(BookingForm.name)
async def process_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text)
    await state.set_state(BookingForm.phone)
    await message.answer(f"Дякую, {message.text}!\n\nТепер поділіться своїм номером телефону (натисніть кнопку нижче або напишіть вручну) 👇", reply_markup=get_phone_keyboard())

@dp.message(BookingForm.phone, F.contact)
async def process_phone_contact(message: Message, state: FSMContext):
    phone = message.contact.phone_number
    if not phone.startswith("+"): phone = "+" + phone
    await state.update_data(phone=phone)
    data = await state.get_data()
    await state.set_state(BookingForm.confirm)
    summary = f"📋 <b>Перевірте ваші дані:</b>\n\n👤 Ім'я: {data['name']}\n📱 Телефон: {data['phone']}\n🦷 Послуга: {data['service']}\n👨‍⚕️ Лікар: {data['doctor']}\n📅 Дата: {data['date']}\n🕐 Час: {data['time']}\n\nВсе вірно?"
    await message.answer(summary, parse_mode="HTML", reply_markup=get_confirm_inline())

@dp.message(BookingForm.phone, F.text)
async def process_phone_text(message: Message, state: FSMContext):
    # Проверяем, похоже ли это на номер телефона
    text = message.text.strip()
    if len(re.sub(r'\D', '', text)) < 10:
        await message.answer("❌ Будь ласка, введіть коректний номер телефону (наприклад, +380991234567) або натисніть кнопку.")
        return
    
    await state.update_data(phone=text)
    data = await state.get_data()
    await state.set_state(BookingForm.confirm)
    summary = f"📋 <b>Перевірте ваші дані:</b>\n\n👤 Ім'я: {data['name']}\n📱 Телефон: {data['phone']}\n🦷 Послуга: {data['service']}\n👨‍⚕️ Лікар: {data['doctor']}\n📅 Дата: {data['date']}\n🕐 Час: {data['time']}\n\nВсе вірно?"
    await message.answer(summary, parse_mode="HTML", reply_markup=get_confirm_inline())

@dp.callback_query(BookingForm.confirm)
async def process_confirm(callback: CallbackQuery, state: FSMContext):
    if callback.data == "confirm_no":
        await state.clear()
        await callback.message.delete()
        await callback.message.answer("❌ Запис скасовано.", reply_markup=get_main_menu())
        await callback.answer()
        return
    data = await state.get_data()
    if is_time_booked(data['date'], data['time']):
        await callback.message.delete()
        await callback.message.answer("❌ На жаль, цей час щойно зайняли.", reply_markup=get_main_menu())
        await state.clear()
        await callback.answer()
        return
    name = data.get('saved_name') or data.get('name')
    phone = data.get('saved_phone') or data.get('phone')
    book_time(data['date'], data['time'])
    add_appointment(callback.from_user.id, name, phone, data['service'], data['doctor'], data['date'], data['time'])
    save_user(callback.from_user.id, name, phone)
    await state.clear()
    await callback.message.delete()
    admin_text = f"🚨 <b>НОВА ЗАЯВКА</b> 🚨\n\n👤 Пацієнт: {name}\n📱 Телефон: {phone}\n🦷 Послуга: {data['service']}\n👨‍⚕️ Лікар: {data['doctor']}\n📅 Дата: {data['date']}\n🕐 Час: {data['time']}"
    await bot.send_message(ADMIN_CHAT_ID, admin_text, parse_mode="HTML")
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Скасувати запис", callback_data=f"cancel_{data['date']}_{data['time']}")]])
    await callback.message.answer(
        f"✅ <b>Дякуємо, {name}!</b>\n\n"
        f"Ви успішно записані:\n🦷 {data['service']}\n📅 {data['date']} о {data['time']}\n\n"
        f"Якщо ваші плани зміняться, натисніть кнопку нижче.",
        parse_mode="HTML",
        reply_markup=kb
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("cancel_"))
async def process_cancel(callback: CallbackQuery):
    parts = callback.data.split("_")
    date = parts[1]
    time = parts[2]
    unbook_time(date, time)
    appointments = load_json(APPOINTMENTS_FILE, [])
    for appt in appointments:
        if appt["chat_id"] == callback.from_user.id and appt["date"] == date and appt["time"] == time:
            appt["notified"] = True
            appt["review_sent"] = True
    save_json(APPOINTMENTS_FILE, appointments)
    await callback.message.edit_text("❌ Ваш візит скасовано. Ви можете записатися на інший час.")
    await bot.send_message(ADMIN_CHAT_ID, f"⚠️ <b>Пацієнт скасував запис!</b>\nДата: {date}\nЧас: {time}", parse_mode="HTML")
    await callback.answer()

# ==========================================
# ФОНОВЫЕ ЗАДАЧИ
# ==========================================
async def scheduled_tasks():
    while True:
        try:
            appointments = load_json(APPOINTMENTS_FILE, [])
            now = datetime.now()
            changed = False
            
            for appt in appointments:
                try:
                    appt_datetime = datetime.strptime(f"{appt['date']} {appt['time']}", "%d.%m.%Y %H:%M")
                except ValueError:
                    continue
                
                time_diff = appt_datetime - now
                
                # Напоминание за 2 часа
                if not appt["notified"] and timedelta(0) < time_diff <= timedelta(hours=2):
                    try:
                        msg_text = (
                            f"🔔 <b>Нагадування!</b>\n\n"
                            f"Сьогодні о <b>{appt['time']}</b> у вас прийом.\n"
                            f"Послуга: {appt['service']}"
                        )
                        await bot.send_message(
                            appt["chat_id"], 
                            msg_text, 
                            parse_mode="HTML"
                        )
                        appt["notified"] = True
                        changed = True
                    except Exception as e:
                        logging.error(f"Ошибка напоминания: {e}")
                
                # Отзыв через 3 часа после визита
                if not appt["review_sent"] and time_diff < timedelta(hours=-3):
                    try:
                        review_text = (
                            f"Добрий день, {appt['name']}! 🦷\n\n"
                            f"Сподіваємося, ваш візит пройшов добре. "
                            f"Будемо дуже вдячні, якщо ви залишите відгук!"
                        )
                        kb = InlineKeyboardMarkup(inline_keyboard=[
                            [InlineKeyboardButton(text="⭐ Залишити відгук", url=GOOGLE_MAPS_REVIEW_URL)]
                        ])
                        await bot.send_message(
                            appt["chat_id"], 
                            review_text, 
                            parse_mode="HTML",
                            reply_markup=kb
                        )
                        appt["review_sent"] = True
                        changed = True
                    except Exception as e:
                        logging.error(f"Ошибка отправки отзыва: {e}")
            
            if changed:
                save_json(APPOINTMENTS_FILE, appointments)
                
        except Exception as e:
            logging.error(f"Ошибка в фоновой задаче: {e}")
            
        # Проверяем каждые 5 минут
        await asyncio.sleep(300)

# ==========================================
# ОБРАБОТКА НЕИЗВЕСТНЫХ СООБЩЕНИЙ
# ==========================================
@dp.message()
async def unknown_message(message: Message):
    await message.answer(
        "🤖 Я вас не зрозумів. Скористайтеся кнопками меню 👇", 
        reply_markup=get_main_menu()
    )

# ==========================================
# ЗАПУСК
# ==========================================
async def main():
    print("Бот запущен...")
    
    # Запускаем фоновую задачу для напоминаний и отзывов
    asyncio.create_task(scheduled_tasks())
    
    # Фейковый веб-сервер для Render (чтобы сервис не падал)
    app = web.Application()
    app.router.add_get("/", lambda r: web.Response(text="UkrDent Bot is alive!"))
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    
    # Запуск самого бота
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
if __name__ == "__main__":
    asyncio.run(main())
