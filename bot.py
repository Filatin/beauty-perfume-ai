import os
import sys
import logging
import asyncio
import html
from dotenv import load_dotenv

from aiohttp import web
from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import (
    Message,
    ReplyKeyboardMarkup,
    KeyboardButton
)
from aiogram.client.default import DefaultBotProperties
import google.generativeai as genai

# 1. Загрузка переменных окружения
load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
PORT = int(os.getenv("PORT", 8080))

if not TELEGRAM_BOT_TOKEN or not GEMINI_API_KEY:
    logging.critical("ОШИБКА: Задайте TELEGRAM_BOT_TOKEN и GEMINI_API_KEY")
    sys.exit(1)

TELEGRAM_BOT_TOKEN = TELEGRAM_BOT_TOKEN.strip().strip('"').strip("'")
GEMINI_API_KEY = GEMINI_API_KEY.strip().strip('"').strip("'")

# 2. Настройка Gemini API на актуальную модель
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")

# 3. Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s"
)
logger = logging.getLogger(__name__)

# 4. Инициализация бота
bot = Bot(
    token=TELEGRAM_BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()

# --- ВЕБ-СЕРВЕР ДЛЯ RENDER (HEALTH CHECK) ---

async def handle_ping(request):
    return web.Response(text="Beauty Bot is running 24/7!")

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    logger.info(f"Healthcheck web server started on port {PORT}")

# --- КЛАВИАТУРЫ ---

def get_language_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="🇵🇱 Polski"),
                KeyboardButton(text="🇬🇧 English")
            ]
        ],
        resize_keyboard=True
    )

def get_pl_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="📦 Opis Allegro"),
                KeyboardButton(text="📱 Instagram PL")
            ],
            [
                KeyboardButton(text="🔍 Zamienniki PL"),
                KeyboardButton(text="⬅️ Zmień język")
            ]
        ],
        resize_keyboard=True
    )

def get_en_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="📦 Amazon EN"),
                KeyboardButton(text="📱 Instagram EN")
            ],
            [
                KeyboardButton(text="🔍 Dupes EN"),
                KeyboardButton(text="⬅️ Change language")
            ]
        ],
        resize_keyboard=True
    )

# --- СИСТЕМНЫЙ ПРОМПТ ---

def build_prompt(user_text: str) -> str:
    return f"""Jesteś profesjonalnym copywriterem e-commerce w branży Beauty & Perfumes.

WIADOMOŚĆ OD UŻYTKOWNIKA:
{user_text}

BARDZO WAŻNE ZASADY:
1. Używaj wyłącznie tagów HTML: <b>, <i>, <code>. KATEGORYCZNY ZAKAZ używania tagu <br>.
2. Generuj WYŁĄCZNIE ten format, o który prosi użytkownik. Żadnych dodatkowych sekcji.

---

1. REAKCJA NA PRZYCISKI MENU (Gdy kliknięto sam przycisk):

• "📱 Instagram PL":
📱 <b>Tryb: Post Instagram (PL)</b>

Skopiuj i wyślij z nazwą swoich perfum:
<code>Insta: Nazwa Perfum</code>
<i>(np. kliknij aby skopiować: <code>Insta: Tom Ford Tobacco Vanille</code>)</i>

• "📦 Opis Allegro":
📦 <b>Tryb: Opis Allegro (PL)</b>

Skopiuj i wyślij z nazwą swoich perfum:
<code>Allegro: Nazwa Perfum</code>
<i>(np. kliknij aby skopiować: <code>Allegro: Tom Ford Tobacco Vanille</code>)</i>

• "🔍 Zamienniki PL":
🔍 <b>Tryb: Zamienniki (PL)</b>

Skopiuj i wyślij z nazwą swoich perfum:
<code>Dupes: Nazwa Perfum</code>

• "📦 Amazon EN" ➔ <code>Amazon: Perfume Name</code>
• "📱 Instagram EN" ➔ <code>Insta EN: Perfume Name</code>
• "🔍 Dupes EN" ➔ <code>Dupes EN: Perfume Name</code>

---

2. GENEROWANIE POJEDYNCZYCH FORMATÓW:

A) Jeśli wiadomość zawiera "Insta:" lub "Instagram PL":
📱 <b>POST INSTAGRAM (PL)</b>
[Chwytliwy nagłówek z emoji]
[Emocjonalna recenzja zapachu z językiem korzyści]
👉 <b>Kup teraz przez link w bio!</b>
#perfumy #zapach #beautypl #[markaperfum]

B) Jeśli wiadomość zawiera "Allegro:" lub "Opis Allegro":
📦 <b>OPIS ALLEGRO / SKLEP (PL)</b>
🏷 <b>Tytuł:</b> [SEO Tytuł z marką, modelem i pojemnością]
💎 <b>Opis:</b> [Zmysłowy opis sprzedażowy]
🌿 <b>Nuty zapachowe:</b> Głowa, Serce, Baza.
🎯 <b>Dla kogo:</b> Okazje i profil klienta.

C) Jeśli wiadomość zawiera "Dupes:" lub "Zamienniki":
🔍 <b>ANALIZA ZAMIENNIKÓW (PL)</b>
👑 <b>Oryginał:</b> [Nazwa]
💰 <b>Top 3 Zamienniki:</b> [Marka, orientacyjna cena w PLN, podobieństwo nut]

D) Jeśli podano samą nazwę perfum bez prefiksu:
Zapytaj: "W jakim formacie przygotować treść dla <b>[nazwa]</b>? Wybierz i wyślij: <code>Insta: [nazwa]</code>, <code>Allegro: [nazwa]</code> lub <code>Dupes: [nazwa]</code>"
"""

# --- ОБРАБОТЧИКИ СООБЩЕНИЙ ---

@dp.message(CommandStart())
@dp.message(F.text.in_(["⬅️ Zmień język", "⬅️ Change language"]))
async def handle_start(message: Message):
    text = (
        "✨ <b>BEAUTY E-COMMERCE AI ENGINE</b> ✨\n\n"
        "Wybierz swój język roboczy:\n"
        "Choose your workspace language:"
    )
    await message.answer(text, reply_markup=get_language_keyboard())

@dp.message(F.text == "🇵🇱 Polski")
async def handle_pl_menu(message: Message):
    text = (
        "🇵🇱 <b>Wybrano język polski.</b>\n"
        "Wybierz interesujący Cię format poniżej:"
    )
    await message.answer(text, reply_markup=get_pl_keyboard())

@dp.message(F.text == "🇬🇧 English")
async def handle_en_menu(message: Message):
    text = (
        "🇬🇧 <b>English language selected.</b>\n"
        "Choose your desired format below:"
    )
    await message.answer(text, reply_markup=get_en_keyboard())

@dp.message(F.text)
async def handle_ai_generation(message: Message):
    await bot.send_chat_action(chat_id=message.chat.id, action="typing")
    prompt = build_prompt(message.text)

    try:
        response = await asyncio.to_thread(model.generate_content, prompt)
        reply_text = response.text
        try:
            await message.answer(reply_text, parse_mode=ParseMode.HTML)
        except Exception:
            await message.answer(reply_text, parse_mode=None)
    except Exception as e:
        logger.error(f"Error during AI generation: {e}")
        error_msg = html.escape(str(e))
        await message.answer(
            f"⚠️ <b>Błąd API:</b>\n<code>{error_msg}</code>"
        )

# --- ГЛАВНЫЙ ЗАПУСК ---

async def main():
    logger.info("Starting web server...")
    await start_web_server()
    
    logger.info("Connecting bot to Telegram...")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped.")
