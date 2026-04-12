from newspaper import Article  # добавь эту строку в самое начало файла, где остальные импорты

# ... (весь остальной код бота)

async def rewrite_news(news_item):
    title = news_item['title']
    url = news_item['url']
    full_text = ""
    
    # Пробуем вытащить полную статью через newspaper3k
    try:
        article = Article(url)
        article.download()
        article.parse()
        full_text = article.text
        logging.info(f"Успешно загружена полная статья: {url}")
    except Exception as e:
        # Если что-то пошло не так, используем короткое описание из RSS
        logging.error(f"Ошибка загрузки статьи {url}: {e}. Использую RSS-описание.")
        full_text = news_item.get('description', '')
    
    # Формируем пост
    post = f"🔥 <b>НОВОСТЬ</b>\n\n"
    post += f"<b>{title}</b>\n\n"
    
    if full_text:
        # Берём первые 3000 символов (можешь увеличить или убрать лимит)
        post += f"{full_text[:3000]}\n\n"
    else:
        # Если и здесь ничего нет
        post += f"Не удалось загрузить текст статьи.\n\n"
    
    # Добавляем кликабельное СВА в конце
    post += f'\n<a href="https://t.me/Sami_V_Ahye">СВА</a>'
    
    return post