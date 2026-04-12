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

# ========== НАСТРОЙКИ ==========
BOT_TOKEN = "8678003507:AAHNGDlhq6KJAr7Ifr_QF-NSurCMSbShNaE"
CHANNEL_ID = "@Sami_V_Ahye"
GROQ_API_KEY = "gsk_your_key_here"  # Получи бесплатно на console.groq.com
# ===============================

# Берём новости из RSS этих каналов
SOURCES = [
    "https://telegram-rss-parser-web.vercel.app/rss/nmshhub",
    "https://ria.ru/export/rss2/index.xml",
]

CHECK_INTERVAL = 1
POSTS_PER_CHECK = 2

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
        from bs4 import BeautifulSoup
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
                description = item.find('description')
                desc_text = description.text if description else ""
                if title_text and link_url:
                    items.append({
                        'title': title_text,
                        'description': desc_text[:500],
                        'url': link_url,
                    })
            return items
    except Exception as e:
        logging.error(f"RSS error {url}: {e}")
        return []

async def rewrite_with_groq(title, original_text):
    """Переписывает новость в стиле твоего идеального поста"""
    prompt = f"""Перепиши эту новость в стиле для Telegram-канала. Используй такие же приёмы: 
- ЗАГЛАВНЫЕ БУКВЫ в начале
- Эмодзи 🔺 или другой по смыслу
- Эмоциональный, патриотичный стиль как в примере
- Коротко, ёмко, без воды
- Добавь в конце строку с 📷 СВА 📷

Вот пример:
🔺 СЕГОДНЯ ПОД ТОМСКОМ НЕКИЙ ПАВЕЛ СЕРГЕЕВ СБИЛ 67 БЕСПИЛОТНИКОВ 🔺

Павел Сергеев - житель Томска, увлекающийся созданием аниматронных роботов и БПЛА создал новую технологию с помощью которой сбил ровно 67 хохлятских дронов

📷 СВА 📷

Теперь перепиши эту новость:
Заголовок: {title}
Текст: {original_text}

Только текст поста, без лишних пояснений."""
    
    try:
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": "llama-3.3-70b-versatile",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7,
            "max_tokens": 500
        }
        sess = await get_session()
        async with sess.post(url, json=payload, headers=headers) as resp:
            if resp.status == 200:
                data = await resp.json()
                return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        logging.error(f"Groq error: {e}")
    return None

async def generate_image(prompt):
    """Генерирует картинку через бесплатный Pollinations AI"""
    try:
        # Создаём запрос для картинки на основе заголовка
        image_prompt = f"news illustration, {prompt}, realistic, high quality"
        url = f"https://image.pollinations.ai/prompt/{image_prompt}?width=1080&height=720&nologo=true"
        return url
    except Exception as e:
        logging.error(f"Image generation error: {e}")
        return None

async def process_and_post():
    posted = load_posted()
    
    logging.info("Сбор новостей...")
    all_news = []
    for source in SOURCES:
        news_items = await fetch_rss_feed(source)
        all_news.extend(news_items)
        await asyncio.sleep(1)
    
    # Убираем дубликаты
    unique_news = []
    seen = set()
    for item in all_news:
        if item['title'][:50] not in seen:
            seen.add(item['title'][:50])
            unique_news.append(item)
    
    new_news = [n for n in unique_news if n['url'] not in posted]
    new_news = new_news[:POSTS_PER_CHECK]
    
    if not new_news:
        logging.info("Новых новостей нет")
        return
    
    for news_item in new_news:
        logging.info(f"Обработка: {news_item['title'][:50]}...")
        
        # Переписываем новость через Groq
        post_text = await rewrite_with_groq(news_item['title'], news_item['description'])
        if not post_text:
            post_text = f"🔺 {news_item['title'].upper()} 🔺\n\n{news_item['description']}\n\n📷 СВА 📷"
        
        # Генерируем картинку
        image_url = await generate_image(news_item['title'])
        
        try:
            if image_url:
                photo = URLInputFile(image_url)
                await bot.send_photo(chat_id=CHANNEL_ID, photo=photo, caption=post_text, parse_mode="HTML")
            else:
                await bot.send_message(chat_id=CHANNEL_ID, text=post_text, parse_mode="HTML")
            
            posted.add(news_item['url'])
            save_posted(posted)
            logging.info(f"Опубликовано")
            await asyncio.sleep(10)
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
    await message.answer("Я работаю")

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