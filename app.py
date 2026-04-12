import asyncio
import logging
import json
import os
import re
import random
import aiohttp
from datetime import datetime
from bs4 import BeautifulSoup
from flask import Flask
from aiogram import Bot, Dispatcher, types
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties
from aiogram.types import InputFile
import tempfile

# ========== НАСТРОЙКИ ==========
BOT_TOKEN = "8678003507:AAHNGDlhq6KJAr7Ifr_QF-NSurCMSbShNaE"
CHANNEL_ID = "@Sami_V_Ahye"
UNSPLASH_ACCESS_KEY = "AqS8-eoVpvoTexWP85LIaf-vEf6kSZajprjUeJBTdb8"
# ===============================

SOURCES = [
    "https://ria.ru/export/rss2/index.xml",
    "https://tass.ru/rss",
    "https://lenta.ru/rss",
]

CHECK_INTERVAL = 1
POSTS_PER_CHECK = 3
MAX_TEXT_LENGTH = 1100

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher(storage=MemoryStorage())
session = None

POSTED_FILE = "posted_news.json"

def load_posted():
    if os.path.exists(POSTED_FILE):
        try:
            with open(POSTED_FILE, 'r') as f:
                return set(json.load(f))
        except:
            return set()
    return set()

def save_posted(posted_set):
    with open(POSTED_FILE, 'w') as f:
        json.dump(list(posted_set), f)

async def get_session():
    global session
    if session is None:
        session = aiohttp.ClientSession()
    return session

async def search_unsplash_image(keywords):
    try:
        url = "https://api.unsplash.com/search/photos"
        params = {"query": keywords, "per_page": 3, "orientation": "landscape"}
        headers = {"Authorization": f"Client-ID {UNSPLASH_ACCESS_KEY}"}
        sess = await get_session()
        async with sess.get(url, params=params, headers=headers) as resp:
            if resp.status == 200:
                data = await resp.json()
                if data["results"]:
                    img = random.choice(data["results"])
                    return img["urls"]["regular"]
    except Exception as e:
        logging.error(f"Unsplash error: {e}")
    return None

async def fetch_rss_feed(url):
    try:
        sess = await get_session()
        async with sess.get(url, timeout=15) as resp:
            if resp.status != 200:
                return []
            content = await resp.text()
            soup = BeautifulSoup(content, 'xml')
            items = []
            for item in soup.find_all('item')[:15]:
                title = item.find('title')
                title_text = title.text if title else ""
                description = item.find('description')
                desc_text = description.text if description else ""
                desc_text = re.sub(r'<[^>]+>', '', desc_text)
                desc_text = re.sub(r'\s+', ' ', desc_text).strip()
                link = item.find('link')
                link_url = link.text if link else ""
                if title_text and link_url:
                    items.append({
                        'title': title_text,
                        'description': desc_text,
                        'url': link_url,
                    })
            return items
    except Exception as e:
        logging.error(f"RSS error {url}: {e}")
        return []

def clean_text(text):
    """Убирает мусор из текста"""
    # Убираем лишние пробелы и переносы
    text = re.sub(r'\s+', ' ', text)
    # Убираем фразы типа "Читать ria.ru в", "Архивное фото" и т.д.
    garbage_phrases = [
        r'Читать \w+\.ru в',
        r'Архивное фото',
        r'Чтобы оставить реакцию.*',
        r'Обсудить',
        r'Рекомендуем',
        r'Лента новостей',
        r'Заголовок открываемого материала',
        r'Доступ к чату заблокирован.*',
        r'Обсуждение закрыто.*',
        r'Telegram',
        r'ВКонтакте',
        r'Одноклассники',
        r'X',
        r'loader',
        r'просмотров',
        r'Отправить еще раз',
    ]
    for phrase in garbage_phrases:
        text = re.sub(phrase, '', text, flags=re.IGNORECASE)
    # Убираем множественные пробелы
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def get_emoji_by_title(title):
    title_lower = title.lower()
    if re.search(r'путин|трамп|байден|политик|кремль|депутат|госдума|выборы|пезешкиан', title_lower):
        return "🏛️"
    if re.search(r'войн|арми|солдат|танк|обстрел|атака|взрыв|украин|израиль|палестин|иран', title_lower):
        return "💥"
    if re.search(r'рубл|доллар|евро|нефт|газ|денег|бизнес|крипт|биткоин', title_lower):
        return "💰"
    if re.search(r'авари|дтп|погиб|смерт|убийств|пожар|наводн|землетряс', title_lower):
        return "🚨"
    if re.search(r'пасх|рождеств|праздник', title_lower):
        return "🐣"
    return "⚡️"

async def rewrite_news(news_item):
    title = news_item['title']
    raw_desc = news_item['description']
    
    # Чистим текст
    clean_desc = clean_text(raw_desc)
    
    # Обрезаем до лимита
    if len(clean_desc) > MAX_TEXT_LENGTH:
        clean_desc = clean_desc[:MAX_TEXT_LENGTH] + "..."
    
    emoji = get_emoji_by_title(title)
    
    # Формируем пост
    post = f"{emoji} <b>{title}</b>\n\n"
    
    if clean_desc and len(clean_desc) > 20:
        post += f"{clean_desc}\n\n"
    else:
        post += f"Подробнее по ссылке\n\n"
    
    post += f'⚡<a href="https://t.me/{CHANNEL_ID[1:]}">СВА</a>⚡'
    
    # Ищем картинку по заголовку
    keywords = ' '.join(title.split()[:5])
    image_url = await search_unsplash_image(keywords)
    
    return post, image_url

async def collect_news():
    all_news = []
    for source in SOURCES:
        news_items = await fetch_rss_feed(source)
        all_news.extend(news_items)
        await asyncio.sleep(1)
    
    unique_news = []
    seen_titles = set()
    for item in all_news:
        title_short = item['title'][:50]
        if title_short not in seen_titles:
            seen_titles.add(title_short)
            unique_news.append(item)
    return unique_news

async def process_and_post():
    posted = load_posted()
    
    logging.info("Сбор новостей...")
    all_news = await collect_news()
    logging.info(f"Найдено {len(all_news)} уникальных новостей")
    
    new_news = [n for n in all_news if n['url'] not in posted]
    new_news = new_news[:POSTS_PER_CHECK]
    
    if not new_news:
        logging.info("Новых новостей нет")
        return
    
    for news_item in new_news:
        post_text, image_url = await rewrite_news(news_item)
        
        try:
            if image_url:
                sess = await get_session()
                async with sess.get(image_url) as img_resp:
                    if img_resp.status == 200:
                        photo_data = await img_resp.read()
                        with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp_file:
                            tmp_file.write(photo_data)
                            tmp_path = tmp_file.name
                        
                        photo_file = InputFile(tmp_path)
                        await bot.send_photo(chat_id=CHANNEL_ID, photo=photo_file, caption=post_text, parse_mode="HTML")
                        os.unlink(tmp_path)
                    else:
                        await bot.send_message(chat_id=CHANNEL_ID, text=post_text, parse_mode="HTML")
            else:
                await bot.send_message(chat_id=CHANNEL_ID, text=post_text, parse_mode="HTML")
            
            posted.add(news_item['url'])
            save_posted(posted)
            logging.info(f"Опубликовано: {news_item['title'][:50]}...")
            await asyncio.sleep(5)
        except Exception as e:
            logging.error(f"Ошибка публикации: {e}")

async def start_posting():
    while True:
        try:
            await process_and_post()
        except Exception as e:
            logging.error(f"Ошибка в цикле: {e}")
        await asyncio.sleep(CHECK_INTERVAL * 60)

@dp.startup()
async def on_startup():
    logging.info("Бот запущен")
    asyncio.create_task(start_posting())

@dp.message()
async def echo(message: types.Message):
    await message.answer("Я работаю в фоне и пощу новости в канал")

app = Flask(__name__)

@app.route('/')
@app.route('/health')
def health():
    return "OK", 200

def run_flask():
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))

async def main():
    from threading import Thread
    Thread(target=run_flask, daemon=True).start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())