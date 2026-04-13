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

# ========== НАСТРОЙКИ ==========
BOT_TOKEN = "8678003507:AAFBQoHXJ6Mytg2hFj-CLE-sOvr5JPMMtj0"
CHANNEL_ID = "testbotatestbotanewstest"
# ===============================

SOURCES = [
    "https://ria.ru/export/rss2/index.xml",
    "https://tass.ru/rss",
    "https://lenta.ru/rss",
    "https://naked-science.ru/allrss",
]

CHECK_INTERVAL = 1
POSTS_PER_CHECK = 5

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher(storage=MemoryStorage())
session = None

POSTED_FILE = "posted_news.json"

def load_posted():
    if os.path.exists(POSTED_FILE):
        with open(POSTED_FILE, 'r') as f:
            return set(json.load(f))
    return set()

def save_posted(posted_set):
    with open(POSTED_FILE, 'w') as f:
        json.dump(list(posted_set), f)

async def get_session():
    global session
    if session is None:
        session = aiohttp.ClientSession()
    return session

def get_emoji_and_hashtag(title):
    t = title.lower()
    if re.search(r'путин|трамп|байден|кремль|выборы|депутат', t):
        return "🏛️", "#политика"
    if re.search(r'война|армия|солдат|танк|обстрел|атака|взрыв|украина|дрон|всу', t):
        return "💥", "#война"
    if re.search(r'рубль|доллар|евро|нефть|газ|цена|деньги|бизнес|санкции', t):
        return "💰", "#экономика"
    if re.search(r'авария|дтп|пожар|наводнение|землетрясение|погиб|спасение', t):
        return "🚨", "#чп"
    if re.search(r'наука|исследование|ученые|космос|технология|открытие', t):
        return "🔬", "#наука"
    if re.search(r'спорт|футбол|хоккей|олимпиада|чемпионат|матч', t):
        return "⚽", "#спорт"
    return "📰", "#новости"

async def fetch_rss_feed(url):
    try:
        sess = await get_session()
        async with sess.get(url, timeout=15) as resp:
            if resp.status != 200:
                return []
            content = await resp.text()
            soup = BeautifulSoup(content, 'xml')
            items = []
            for item in soup.find_all('item')[:5]:
                title = item.find('title')
                title_text = title.text if title else ""
                link = item.find('link')
                link_url = link.text if link else ""
                desc = item.find('description')
                desc_text = desc.text if desc else ""
                desc_text = re.sub(r'<[^>]+>', '', desc_text)
                desc_text = re.sub(r'\s+', ' ', desc_text).strip()
                # Пробуем вытащить картинку из description или enclosure
                img = None
                enclosure = item.find('enclosure')
                if enclosure and enclosure.get('url'):
                    img = enclosure.get('url')
                elif 'img' in desc_text:
                    img_match = re.search(r'https?://[^\s]+\.(jpg|jpeg|png|webp)', desc_text)
                    if img_match:
                        img = img_match.group(0)
                if title_text and link_url:
                    items.append({
                        'title': title_text,
                        'description': desc_text[:400],
                        'url': link_url,
                        'image': img,
                    })
            return items
    except Exception as e:
        logging.error(f"RSS error {url}: {e}")
        return []

def make_post(item):
    emoji, tag = get_emoji_and_hashtag(item['title'])
    text = f"{emoji} <b>{item['title']}</b>\n\n"
    if item['description']:
        text += f"{item['description']}\n\n"
    text += f"{tag}"
    return text, item['image']

async def main_loop():
    posted = load_posted()
    
    logging.info("Сбор новостей...")
    all_news = []
    for src in SOURCES:
        news = await fetch_rss_feed(src)
        all_news.extend(news)
        await asyncio.sleep(1)
    
    unique = []
    seen = set()
    for item in all_news:
        if item['title'][:50] not in seen:
            seen.add(item['title'][:50])
            unique.append(item)
    
    new_items = [x for x in unique if x['url'] not in posted]
    new_items = new_items[:POSTS_PER_CHECK]
    
    if not new_items:
        logging.info("Нет новых новостей")
        return
    
    for item in new_items:
        text, img = make_post(item)
        try:
            if img:
                photo = URLInputFile(img)
                await bot.send_photo(chat_id=f"@{CHANNEL_ID}", photo=photo, caption=text, parse_mode="HTML")
            else:
                await bot.send_message(chat_id=f"@{CHANNEL_ID}", text=text, parse_mode="HTML")
            posted.add(item['url'])
            save_posted(posted)
            logging.info(f"Опубликовано: {item['title'][:50]}...")
            await asyncio.sleep(5)
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