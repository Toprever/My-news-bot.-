import asyncio
import logging
import json
import os
import re
import aiohttp
from datetime import datetime
from bs4 import BeautifulSoup
from flask import Flask
from aiogram import Bot, Dispatcher, types
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties
from aiogram.types import BufferedInputFile

# ========== НАСТРОЙКИ (С ТВОИМИ ДАННЫМИ) ==========
BOT_TOKEN = "8678003507:AAHNGDlhq6KJAr7Ifr_QF-NSurCMSbShNaE"
CHANNEL_ID = "@Sami_V_Ahye"
FIRECRAWL_API_KEY = "fc-f01a96f6246949ccb48af5598203a459"
# =================================================

SOURCES = [
    "https://ria.ru/export/rss2/index.xml",
    "https://tass.ru/rss",
    "https://lenta.ru/rss",
]

CHECK_INTERVAL = 1
POSTS_PER_CHECK = 3

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

async def fetch_rss_feed(url):
    try:
        sess = await get_session()
        async with sess.get(url, timeout=15) as resp:
            if resp.status != 200:
                return []
            content = await resp.text()
            soup = BeautifulSoup(content, 'xml')
            items = []
            for item in soup.find_all('item')[:10]:
                title = item.find('title')
                title_text = title.text if title else ""
                link = item.find('link')
                link_url = link.text if link else ""
                if title_text and link_url:
                    items.append({
                        'title': title_text,
                        'url': link_url,
                    })
            return items
    except Exception as e:
        logging.error(f"RSS error {url}: {e}")
        return []

async def scrape_with_firecrawl(url):
    """Отправляет URL в Firecrawl и получает текст + картинку"""
    api_url = "https://api.firecrawl.dev/v1/scrape"
    headers = {
        "Authorization": f"Bearer {FIRECRAWL_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "url": url,
        "formats": ["markdown"],
        "onlyMainContent": True
    }
    
    try:
        sess = await get_session()
        async with sess.post(api_url, json=payload, headers=headers) as resp:
            if resp.status == 200:
                data = await resp.json()
                if data.get("success"):
                    content = data.get("data", {}).get("markdown", "")
                    # Пробуем вытащить первую картинку из markdown
                    img_match = re.search(r'!\[.*?\]\((https?://[^\s)]+)\)', content)
                    image_url = img_match.group(1) if img_match else None
                    # Чистим текст от markdown-разметки
                    clean_text = re.sub(r'!\[.*?\]\(.*?\)', '', content)
                    clean_text = re.sub(r'\[.*?\]\(.*?\)', '', clean_text)
                    clean_text = re.sub(r'#{1,6}\s*', '', clean_text)
                    clean_text = '\n'.join(line for line in clean_text.splitlines() if line.strip())
                    return clean_text[:3000], image_url
                else:
                    logging.error(f"Firecrawl error: {data}")
            else:
                logging.error(f"Firecrawl HTTP {resp.status}: {await resp.text()}")
    except Exception as e:
        logging.error(f"Firecrawl error for {url}: {e}")
    return None, None

def get_emoji_by_title(title):
    """Возвращает эмодзи в зависимости от содержания заголовка"""
    title_lower = title.lower()
    
    # Политика и власть
    if re.search(r'путин|трамп|байден|золотов|шайгу|политик|кремль|белый дом|конгресс|депутат|госдума|выборы', title_lower):
        return "🏛️"
    # Война и конфликты
    if re.search(r'войн|арми|солдат|танк|обстрел|атака|удар|бомб|взрыв|пожар|спецоперация|донбасс|украин|израиль|палестин|иран', title_lower):
        return "💥"
    # Экономика и бизнес
    if re.search(r'рубл|доллар|евро|нефт|газ|цен|денег|бизнес|рынок|акци|крипт|биткоин', title_lower):
        return "💰"
    # Происшествия и ЧП
    if re.search(r'авари|дтп|погиб|смерт|убийств|насили|пострада|спас|пожар|наводн|землетряс', title_lower):
        return "🚨"
    # Технологии и наука
    if re.search(r'айфон|смартфон|компьютер|интернет|нейросет|ии|технолог|гаджет|наук|космос', title_lower):
        return "📱"
    # Спорт
    if re.search(r'футбол|хоккей|теннис|спорт|матч|олимпиад|чемпионат', title_lower):
        return "⚽"
    # Медицина и здоровье
    if re.search(r'медицин|больниц|врач|лекарств|вирус|ковид|эпидеми|здоровь', title_lower):
        return "🏥"
    # Эпичный или важный заголовок
    if re.search(r'сенсац|шок|эксклюзив|впервые|наконец|прорыв|историческ', title_lower):
        return "🔥"
    
    # Если ничего не подошло — молния
    return "⚡️"

async def rewrite_news(news_item):
    title = news_item['title']
    url = news_item['url']
    
    full_text, image_url = await scrape_with_firecrawl(url)
    
    # Выбираем эмодзи по заголовку
    emoji = get_emoji_by_title(title)
    
    post = f"{emoji} <b>{title}</b>\n\n"
    
    if full_text:
        post += f"{full_text}\n\n"
    else:
        post += f"Не удалось загрузить полный текст.\n\n"
    
    post += f'⚡<a href="https://t.me/{CHANNEL_ID[1:]}">СВА</a>⚡'
    
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
                        # Оборачиваем байты в BufferedInputFile для aiogram 3.x
                        photo_file = BufferedInputFile(photo_data, filename="news.jpg")
                        await bot.send_photo(chat_id=CHANNEL_ID, photo=photo_file, caption=post_text, parse_mode="HTML")
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