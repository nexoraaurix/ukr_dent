import asyncio
import logging
import os
import json
from datetime import datetime
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

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ==========================================
# РАБОТА С ЗАНЯТЫМ ВРЕМЕНЕМ (JSON)
# ==========================================
DB_FILE = "booked.json"

def load_booked():
    if not os.path.exists(DB_FILE):
        return {}
    with open(DB_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_booked(data):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def is_time_booked(date, time):
    booked = load_booked()
    return time in booked.get(date, [])

def book_time(date, time):
    booked = load_booked()
    if date not in booked:
        booked[date] = []
    booked[date].append(time)
    save_booked(booked)

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

# ==========================================
# КЛАВИАТУРЫ
# ==========================================
def get_main_menu():
    kb = [
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
    if row:
        kb.append(row)
    
    if not kb:
        kb.append([InlineKeyboardButton(text="❌ На цей день всі місця зайняті", callback_data="no_times")])
        
    kb.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_main")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def get_confirm_inline():
    kb = [
        [InlineKeyboardButton(text="✅ Все вірно, записати", callback_data="confirm_yes")],
        [InlineKeyboardButton(text="❌ Скасувати", callback_data="confirm_no")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

# ==========================================
# ОБРАБОТКА КОМАНД
# ==========================================
@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        f"Вітаємо у стоматології «UkrDent»! 🦷\n\n"
        f"Я — ваш цифровий помічник. Тут ви можете:\n"
        f"• Дізнатися про ціни на послуги\n"
        f"• Познайомитися з нашими лікарями\n"
        f"• Записатися на прийом за 1 хвилину\n\n"
        f"Оберіть потрібний пункт у меню нижче 👇",
        reply_markup=get_main_menu()
    )

# ==========================================
# ИНФО-РАЗДЕЛЫ
# ==========================================
@dp.message(F.text == "💰 Послуги та ціни")
async def show_prices(message: Message):
    await message.answer(
        "💰 <b>Наш прайс-лист (орієнтовно):</b>\n\n"
        "• Консультація — <b>Безкоштовно</b>\n"
        "• Лікування карієсу — <b>від 1200 грн</b>\n"
        "• Професійна чистка — <b>900 грн</b>\n"
        "• Імплантація — <b>від 15000 грн</b>\n"
        "• Брекети — <b>від 25000 грн</b>\n\n"
        "💡 <i>Точну вартість лікар визначить після огляду.</i>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🦷 Записатися", callback_data="start_booking")]])
    )

@dp.message(F.text == "👨‍⚕️ Наші лікарі")
async def show_doctors(message: Message):
    await message.answer(
        "👨‍⚕️ <b>Наша команда:</b>\n\n"
        "1️⃣ <b>Олег Іванов</b> — терапевт. Стаж 8 років. Лікує карієс та канали.\n"
        "2️⃣ <b>Марія Петрівна</b> — ортодонт. Стаж 12 років. Вирівнювання зубів, брекети.\n"
        "3️⃣ <b>Андрій В.</b> — хірург-імплантолог. Стаж 10 років. Імплантація та видалення.\n\n"
        "Оберіть лікаря під час запису!",
        parse_mode="HTML"
    )

@dp.message(F.text == "📍 Як дістатися")
async def show_location(message: Message):
    await message.answer(
        "📍 <b>Наша адреса:</b>\n"
        "м. Київ, вул. Хрещатик, 15 (2 поверх)\n\n"
        "🕐 <b>Графік роботи:</b>\n"
        "Пн–Пт: 09:00 – 19:00\n"
        "Сб: 09:00 – 15:00\n"
        "Нд: Вихідний\n\n"
        "🚇 Метро: Хрещатик (вихід до вул. Інститутська).",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🗺 Відкрити на Google Maps", url="https://maps.google.com/?q=Київ,вул.Хрещатик,15")]
        ])
    )

# ==========================================
# РАБОЧИЙ ОБРАБОТЧИК КОНТАКТОВ
# ==========================================
@dp.message(F.text == "📞 Контакти")
async def show_contacts(message: Message):
    print("!!! БОТ ПОЛУЧИЛ КОМАНДУ КОНТАКТЫ !!!")
    await message.answer(
        "📞 <b>Контакти:</b>\n\n"
        "Телефон адміністратора: +38 (044) 123-45-67\n"
        "Viber: +38 (067) 123-45-67\n"
        "Telegram: @ukrdent_admin\n\n"
        "Ми завжди раді допомогти!\n"
        "<i>(Щоб зателефонувати, просто натисніть на номер вище)</i>",
        parse_mode="HTML"
    )

# ==========================================
# ЛОГИКА ЗАПИСИ НА ПРИЕМ
# ==========================================
@dp.callback_query(F.data == "start_booking")
async def start_booking_cb(callback: CallbackQuery, state: FSMContext):
    await callback.message.delete()
    await state.set_state(BookingForm.service)
    await callback.message.answer("Крок 1 з 5. Оберіть послугу, яка вас цікавить:", reply_markup=get_services_inline())
    await callback.answer()

@dp.message(F.text == "🦷 Записатися на прийом")
async def start_booking_text(message: Message, state: FSMContext):
    await state.set_state(BookingForm.service)
    await message.answer("Крок 1 з 5. Оберіть послугу, яка вас цікавить:", reply_markup=get_services_inline())

@dp.callback_query(BookingForm.service)
async def process_service(callback: CallbackQuery, state: FSMContext):
    if callback.data == "back_to_main":
        await state.clear()
        await callback.message.delete()
        await callback.message.answer("Головне меню:", reply_markup=get_main_menu())
        return

    services = {
        "srv_consult": "Консультація",
        "srv_caries": "Лікування карієсу",
        "srv_clean": "Професійна чистка",
        "srv_implant": "Імплантація",
        "srv_braces": "Брекети"
    }
    selected = services.get(callback.data)
    await state.update_data(service=selected)
    await callback.message.delete()
    await state.set_state(BookingForm.doctor)
    await callback.message.answer(f"Ви обрали: <b>{selected}</b>.\n\nКрок 2 з 5. До якого лікаря бажаєте потрапити?", parse_mode="HTML", reply_markup=get_doctors_inline())
    await callback.answer()

@dp.callback_query(BookingForm.doctor)
async def process_doctor(callback: CallbackQuery, state: FSMContext):
    if callback.data == "back_to_main":
        await state.clear()
        await callback.message.delete()
        await callback.message.answer("Головне меню:", reply_markup=get_main_menu())
        return

    doctors = {
        "doc_therapist": "Олег Іванов (Терапевт)",
        "doc_ortho": "Марія Петрівна (Ортодонт)",
        "doc_surgeon": "Андрій В. (Хірург)",
        "doc_any": "Будь-який лікар"
    }
    selected = doctors.get(callback.data)
    await state.update_data(doctor=selected)
    await callback.message.delete()
    await state.set_state(BookingForm.date)
    await callback.message.answer(f"Ви обрали лікаря: <b>{selected}</b>.\n\nКрок 3 з 5. Напишіть бажану дату (наприклад: <i>25 жовтня</i>):", parse_mode="HTML", reply_markup=ReplyKeyboardRemove())
    await callback.answer()

@dp.message(BookingForm.date)
async def process_date(message: Message, state: FSMContext):
    date_str = message.text.strip()
    await state.update_data(date=date_str)
    await state.set_state(BookingForm.time)
    
    await message.answer(
        f"Крок 4 з 5. Оберіть бажаний час на <b>{date_str}</b>:\n"
        f"<i>(Зайнятий час приховано)</i>", 
        parse_mode="HTML", 
        reply_markup=get_time_inline(date_str)
    )

@dp.callback_query(BookingForm.time)
async def process_time(callback: CallbackQuery, state: FSMContext):
    if callback.data == "back_to_main":
        await state.clear()
        await callback.message.delete()
        await callback.message.answer("Головне меню:", reply_markup=get_main_menu())
        return
        
    if callback.data == "no_times":
        await callback.answer("На жаль, на цей день всі місця зайняті. Оберіть іншу дату.", show_alert=True)
        return

    selected_time = callback.data.split("_")[1]
    await state.update_data(time=selected_time)
    await callback.message.delete()
    await state.set_state(BookingForm.name)
    await callback.message.answer(f"Час: <b>{selected_time}</b>.\n\nКрок 5 з 5. Як вас звати? (Ім'я та Прізвище)", parse_mode="HTML")
    await callback.answer()

@dp.message(BookingForm.name)
async def process_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text)
    await state.set_state(BookingForm.phone)
    await message.answer(f"Дякую, {message.text}!\n\nТепер вкажіть ваш номер телефону у форматі <b>+380XXXXXXXXX</b>:", parse_mode="HTML")

@dp.message(BookingForm.phone)
async def process_phone(message: Message, state: FSMContext):
    phone = message.text.strip()
    if not phone.startswith("+380") or len(phone) != 13:
        await message.answer("❌ Будь ласка, введіть номер у форматі +380XXXXXXXXX (12 цифр після +).")
        return

    await state.update_data(phone=phone)
    data = await state.get_data()
    await state.set_state(BookingForm.confirm)

    summary = (
        f"📋 <b>Перевірте ваші дані:</b>\n\n"
        f"👤 Ім'я: {data['name']}\n"
        f"📱 Телефон: {data['phone']}\n"
        f"🦷 Послуга: {data['service']}\n"
        f"👨‍⚕️ Лікар: {data['doctor']}\n"
        f"📅 Дата: {data['date']}\n"
        f"🕐 Час: {data['time']}\n\n"
        f"Все вірно?"
    )
    await message.answer(summary, parse_mode="HTML", reply_markup=get_confirm_inline())

@dp.callback_query(BookingForm.confirm)
async def process_confirm(callback: CallbackQuery, state: FSMContext):
    if callback.data == "confirm_no":
        await state.clear()
        await callback.message.delete()
        await callback.message.answer("❌ Запис скасовано. Якщо захочете повернутися — натисніть /start", reply_markup=get_main_menu())
        await callback.answer()
        return

    data = await state.get_data()
    
    if is_time_booked(data['date'], data['time']):
        await callback.message.delete()
        await callback.message.answer("❌ На жаль, цей час щойно зайняли. Будь ласка, оберіть інший.", reply_markup=get_main_menu())
        await state.clear()
        await callback.answer()
        return

    book_time(data['date'], data['time'])
    await state.clear()
    await callback.message.delete()

    admin_text = (
        f"🚨 <b>НОВА ЗАЯВКА НА ПРИЙОМ</b> 🚨\n\n"
        f"👤 Пацієнт: {data['name']}\n"
        f"📱 Телефон: {data['phone']}\n"
        f"🦷 Послуга: {data['service']}\n"
        f"👨‍⚕️ Лікар: {data['doctor']}\n"
        f"📅 Дата: {data['date']}\n"
        f"🕐 Час: {data['time']}\n\n"
        f"👤 Telegram: @{callback.from_user.username} (ID: {callback.from_user.id})"
    )
    await bot.send_message(ADMIN_CHAT_ID, admin_text, parse_mode="HTML")

    await callback.message.answer(
        f"✅ <b>Дякуємо, {data['name']}!</b>\n\n"
        f"Вашу заявку на <b>{data['service']}</b> прийнято.\n"
        f"Ми зв'яжемося з вами найближчим часом для підтвердження.\n\n"
        f"Гарного дня! 🦷",
        parse_mode="HTML",
        reply_markup=get_main_menu()
    )
    await callback.answer()

# ==========================================
# ОБРАБОТКА НЕИЗВЕСТНЫХ СООБЩЕНИЙ
# ==========================================
@dp.message()
async def unknown_message(message: Message):
    await message.answer(
        "🤖 Я вас не зрозумів. Скористайтеся кнопками меню нижче 👇",
        reply_markup=get_main_menu()
    )

# ==========================================
# ЗАПУСК
# ==========================================
async def main():
    print("Бот запущен...")
    app = web.Application()
    app.router.add_get("/", lambda r: web.Response(text="UkrDent Bot is alive!"))
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
