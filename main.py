import asyncio
import logging
import uuid
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from yookassa import Configuration, Payment

from config import API_TOKEN, SHOP_ID, SECRET_KEY

logging.basicConfig(level=logging.INFO)

# ИНИЦИАЛИЗАЦИЯ
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# КОНФИГУРАЦИЯ ЮKASSA
Configuration.account_id = SHOP_ID
Configuration.secret_key = SECRET_KEY

TARIFF_PRICES = {
    "1month": "100.00",
    "3months": "250.00",
    "6months": "475.00",
    "1year": "900.00"
}

# FSM СОСТОЯНИЯ
class VPNOrder(StatesGroup):
    waiting_for_service = State()
    waiting_for_tariff = State()
    waiting_for_payment = State()
    waiting_for_os = State()

# ФУНКЦИИ БАНКОВСКОГО API
def create_yookassa_payment(amount, description):
    idempotence_key = str(uuid.uuid4())
    payment = Payment.create({
        "amount": {
            "value": amount,
            "currency": "RUB"
        },
        "confirmation": {
            "type": "redirect",
            "return_url": "https://t.me/yns_vpn_bot"
        },
        "capture": True,
        "description": description
    }, idempotence_key)
    return payment

def check_yookassa_payment(payment_id):
    return Payment.find_one(payment_id)

# ХЭНДЛЕРЫ
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    
    photo = FSInputFile("приветственная.png")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌐 VPN-сервис", callback_data="service_vpn")],
        [InlineKeyboardButton(text="🖥 Собственный VPN-сервер", callback_data="service_server")],
        [InlineKeyboardButton(text="📦 Роутер с обходом блокировок", callback_data="service_router")]
    ])
    
    await message.answer_photo(
        photo=photo,
        caption="Доброго времени суток! Система готова к работе.\n\nВыберите необходимую услугу:",
        reply_markup=kb
    )
    await state.set_state(VPNOrder.waiting_for_service)

@dp.callback_query(VPNOrder.waiting_for_service, F.data.startswith("service_"))
async def process_service_choice(callback: types.CallbackQuery, state: FSMContext):
    service = callback.data.split("_")[1]
    
    if service == "vpn":
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Месяц — 100₽", callback_data="tariff_1month")],
            [InlineKeyboardButton(text="3 Месяца - 250₽", callback_data="tariff_3months")],
            [InlineKeyboardButton(text="6 Месяцев - 475₽", callback_data="tariff_6months")],
            [InlineKeyboardButton(text="Год — 900₽", callback_data="tariff_1year")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_main")]
        ])
        await callback.message.edit_caption(
            caption="Вы выбрали VPN-сервис. Выбирайте период:",
            reply_markup=kb
        )
        await state.set_state(VPNOrder.waiting_for_tariff)
        
    elif service in ["server", "router"]:
        await callback.answer("Эта услуга в разработке, скоро всё заработает!", show_alert=True)

@dp.callback_query(F.data == "back_to_main")
async def back_to_start(callback: types.CallbackQuery, state: FSMContext):
    await cmd_start(callback.message, state)
    await callback.message.delete()

@dp.callback_query(VPNOrder.waiting_for_tariff, F.data.startswith("tariff_"))
async def process_tariff(callback: types.CallbackQuery, state: FSMContext):
    tariff = callback.data.split("_")[1]
    price = TARIFF_PRICES.get(tariff, "100.00")
    
    await callback.message.edit_caption(caption="Генерирую защищенный шлюз...")
    
    payment = await asyncio.to_thread(create_yookassa_payment, price, f"Оплата тарифа: {tariff}")
    await state.update_data(chosen_tariff=tariff, payment_id=payment.id)
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Оплатить", url=payment.confirmation.confirmation_url)],
        [InlineKeyboardButton(text="Я оплатил! ✅", callback_data="check_payment")]
    ])
    
    await callback.message.answer(
        f"Отлично, выбор сделан.\nК оплате: **{price} ₽**\n\nЖми на кнопку ниже для перехода к оплате.",
        reply_markup=kb,
        parse_mode="Markdown"
    )
    await callback.message.delete()
    await state.set_state(VPNOrder.waiting_for_payment)

@dp.callback_query(VPNOrder.waiting_for_payment, F.data == "check_payment")
async def check_payment(callback: types.CallbackQuery, state: FSMContext):
    user_data = await state.get_data()
    payment_id = user_data.get("payment_id")
    
    if not payment_id:
        await callback.answer("Ошибка: ID платежа не найден.", show_alert=True)
        return

    payment_info = await asyncio.to_thread(check_yookassa_payment, payment_id)
    
    if payment_info.status == 'succeeded':
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="iOS", callback_data="os_ios")],
            [InlineKeyboardButton(text="Android", callback_data="os_android")],
            [InlineKeyboardButton(text="Windows/PC", callback_data="os_pc")]
        ])
        await callback.message.edit_text(
            "⚡️ Транзакция зафиксирована!\n\nВыберите вашу ОС:",
            reply_markup=kb
        )
        await state.set_state(VPNOrder.waiting_for_os)
    else:
        await callback.answer(f"Статус: {payment_info.status}. Подождите пару секунд.", show_alert=True)

@dp.callback_query(VPNOrder.waiting_for_os, F.data.startswith("os_"))
async def final_step(callback: types.CallbackQuery, state: FSMContext):
    os_type = callback.data.split("_")[1]
    vpn_key = "vless://uuid###########@ip:port?security=reality"
    
    instructions = {
        "ios": "Скачай V2RayTun в AppStore, нажми '+' и вставь ключ.",
        "android": "Скачай v2rayNG в PlayMarket, нажми плюс и импортируй.",
        "pc": "Скачай v2rayN с GitHub, 'Servers' -> 'Import from clipboard'."
    }
    
    await callback.message.answer(
        f"Твой ключ готов к иннервации:\n`{vpn_key}`\n\n**Инструкция для {os_type}:**\n{instructions.get(os_type)}",
        parse_mode="Markdown"
    )
    await state.clear() 

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Система ушла на отдых.")