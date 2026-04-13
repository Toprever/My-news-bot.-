import asyncio
import logging
import json
import os
import re
import aiohttp
from datetime import datetime
from flask import Flask
from aiogram import Bot, Dispatcher, types
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties
from aiogram.types import URLInputFile
from bs4 import BeautifulSoup

BOT_TOKEN = "8678003507:AAFBQoHXJ6Mytg2hFj-CLE-sOvr5JPMMtj0"
CHANNEL_ID = "Sam_V_Shocke"
CHANNEL_LINK = "https://t.me/Sam_V_Shocke"

SOURCES = [
    "https://ria.ru/export/rss2/index.xml",
    "https://tass.ru/rss",
]
CHECK_INTERVAL = 5 
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
                description = item.find('description')
                desc_text = description.text if description else ""
                desc_text = re.sub(r'<[^>]+>', '', desc_text)
                desc_text = re.sub(r'\s+', ' ', desc_text).strip()
                if title_text and link_url:
                    items.append({
                        'title': title_text,
                        'description': desc_text[:500],
                        'url': link_url,
                    })
            return items
    except Exception as e:
        logging.error(f"RSS error: {e}")
        return []

def get_emoji(title):
    if re.search(r'путин|трамп|байден|кремль', title.lower()):
        return "💎"
    if re.search(r'войн|арми|украин|дрон', title.lower()):
        return "💥"
    if re.search(r'рубл|доллар|нефт|газ', title.lower()):
        return "💰"
    return "🔺"

def make_post(title, desc):
    emoji = get_emoji(title)
    text = desc if desc and len(desc) > 30 else "Новость без подробностей"
    return f"<b>{emoji} {title.upper()} {emoji}</b>\n\n{text}\n\n⚡<a href='{CHANNEL_LINK}'>СВШ</a>⚡"

async def make_image(title):
    try:
        kw = re.sub(r'[^\w\s]', '', title)[:50]
        return f"https://image.pollinations.ai/prompt/{kw}?width=1080&height=720"
    except:
        return "https://i.postimg.cc/3x6k9q7R/default-news.jpg"

async def main_loop():
    posted = load_posted()
    logging.info("Сбор новостей...")
    news = []
    for src in SOURCES:
        items = await fetch_rss_feed(src)
        news.extend(items)
        await asyncio.sleep(1)
    
    uniq = []
    seen = set()
    for item in news:
        if item['title'][:50] not in seen:
            seen.add(item['title'][:50])
            uniq.append(item)
    
    new_items = [x for x in uniq if x['url'] not in posted]
    new_items = new_items[:POSTS_PER_CHECK]
    
    if not new_items:
        logging.info("Нет новых новостей")
        return
    
    for item in new_items:
        text = make_post(item['title'], item['description'])
        img = await make_image(item['title'])
        try:
            photo = URLInputFile(img)
            await bot.send_photo(chat_id=f"@{CHANNEL_ID}", photo=photo, caption=text, parse_mode="HTML")
            posted.add(item['url'])
            save_posted(posted)
            logging.info("Опубликовано")
            await asyncio.sleep(10)
        except Exception as e:
            logging.error(f"Ошибка: {e}")

async def scheduler():
    while True:
        try:
            await main_loop()
        except Exception as e:
            logging.error(f"Цикл: {e}")
        await asyncio.sleep(CHECK_INTERVAL * 60)

@dp.startup()
async def on_start():
    logging.info("Бот запущен")
    asyncio.create_task(scheduler())

@dp.message()
async def reply(msg: types.Message):
    await msg.answer("Бот работает")

app = Flask(__name__)
@app.route('/')
def health():
    return "OK"

async def main():
    from threading import Thread
    Thread(target=lambda: app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000))), daemon=True).start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())