import os
import asyncio
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
import openai
import requests
from bs4 import BeautifulSoup
import aiohttp
from urllib.parse import quote

# Настройка токенов
TELEGRAM_TOKEN = '7987759481:AAH15QEjfrVo0WquQDgN6FiUDNMy1z0RVtY'
OPENAI_API_KEY = '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'  # Замените на ваш ключ OpenAI
SERPER_API_KEY = '2acc6a32f0a821eb77ef33a98134cdc6b8830168'  # Получите ключ на https://serper.dev

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Инициализация бота и диспетчера
bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

# Инициализация OpenAI
openai.api_key = OPENAI_API_KEY

# Функция для поиска информации через Google (используя Serper API)
async def search_google(query):
    url = "https://google.serper.dev/search"
    headers = {
        'X-API-KEY': SERPER_API_KEY,
        'Content-Type': 'application/json'
    }
    payload = {
        'q': query,
        'num': 10  # Количество результатов
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload) as response:
                results = await response.json()
                return results.get('organic', [])
    except Exception as e:
        logger.error(f"Ошибка при поиске: {e}")
        return []

# Функция для извлечения текста со страницы
async def get_page_content(url):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                html = await response.text()
                soup = BeautifulSoup(html, 'html.parser')
                
                # Удаляем ненужные элементы
                for tag in soup(['script', 'style', 'meta', 'link']):
                    tag.decompose()
                
                # Получаем текст
                text = soup.get_text(separator='\n', strip=True)
                
                # Очищаем текст
                lines = [line.strip() for line in text.splitlines() if line.strip()]
                text = '\n'.join(lines)
                
                return text[:4000]  # Ограничиваем длину текста
    except Exception as e:
        logger.error(f"Ошибка при получении контента страницы: {e}")
        return ""   
async def process_with_chatgpt(query, search_results, user_role):
    try:
        # Собираем контекст из результатов поиска
        context = "\n\n".join([f"Источник {i+1}:\n{result.get('snippet', '')}"
                              for i, result in enumerate(search_results)])
        
        # Формируем промпт для ChatGPT
        prompt = f"""Сосредоточься на краткой оценке заведения и выявлении ключевых характеристик, которые помогут понять, какие качества и навыки могут быть развиты у выпускников или сотрудников.Будь максимально строг к анализу ведь в компанию нужны самые наилучшие и самые потенциальные люди. Используй следующую информацию, чтобы предоставить емкий, структурированный ответ.

Информация из поиска: {context}

Роль пользователя: {user_role}

Твоя цель:

1. Дай краткое описание заведения, включая его репутацию и основные достижения.
2. Оцени уровень заведения (например, "высокий", "средний", "низкий") на основе его репутации, рейтингов и образовательных или профессиональных программ.
3. Определи максимально точно ключевые качества и навыки, основываясь на уровне заведения и роли пользователя. Например, если пользователь был бригадиром в строительной компании, какие качества у него могли развиться? Если он был учителем в университете, какие навыки он мог развить?
4. Присвой общий рейтинг от 1 до 10, исходя из уровня заведения.

Результат анализа должен включать:

- Краткое описание заведения (репутация и основные достижения).
- Вероятные качества кандидатов (ключевые навыки, вероятно, развиваемые у выпускников или сотрудников).
- Общий рейтинг (от 1 до 10) с кратким объяснением.
"""

        # Отправляем запрос к ChatGPT
        completion = openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Ты - эксперт в области анализа образовательных и профессиональных учреждений."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=2000,
            temperature=0.7
        )
        
        return completion.choices[0].message.content
    except Exception as e:
        logger.error(f"Ошибка при обработке через ChatGPT: {e}")
        return "Извините, произошла ошибка при обработке информации."

# Обработчик команды /start
@dp.message(Command('start'))
async def cmd_start(message: types.Message):
    await message.answer(
        "Привет! Я бот, который может искать и анализировать информацию.\n"
        "Просто отправьте мне тему или вопрос, и я постараюсь найти релевантную информацию.\n"
        "Например: 'AlmaU' или 'Что такое искусственный интеллект?'"
    )

# Обработчик текстовых сообщений
async def search_place_info(place_name):
    # Поиск информации о месте, включая отзывы и достижения
    query = f"{place_name} отзывы, рейтинг,новости, репутация"
    return await search_google(query)

# Обработчик текстовых сообщений
@dp.message()
async def process_query(message: types.Message):
    query = message.text
    user_role = 'студент'
    # Отправляем сообщение о начале поиска
    processing_msg = await message.answer("🔍 Ищу информацию... Пожалуйста, подождите.")
    
    try:
        # Поиск информации о месте
        search_results = await search_place_info(query)
        
        if not search_results:
            await processing_msg.edit_text("😔 К сожалению, я не смог найти информацию по вашему запросу. Попробуйте переформулировать запрос.")
            return
        
        # Обработка информации через ChatGPT
        response = await process_with_chatgpt(query, search_results,user_role)
        
        # Добавляем источники
        sources = "\n\nИсточники:\n" + "\n".join([f"🔗 {result.get('title', 'Источник')}: {result.get('link', '#')}" for result in search_results[:3]])
        
        # Формируем итоговый ответ
        final_response = f"{response}\n{sources}"
        
        # Разбиваем ответ на части, если он слишком длинный
        if len(final_response) > 4096:
            for x in range(0, len(final_response), 4096):
                part = final_response[x:x+4096]
                if x == 0:
                    await processing_msg.edit_text(part)
                else:
                    await message.answer(part)
        else:
            await processing_msg.edit_text(final_response)
            
    except Exception as e:
        logger.error(f"Ошибка при обработке запроса: {e}")
        await processing_msg.edit_text("😔 Произошла ошибка при обработке вашего запроса. Пожалуйста, попробуйте позже.")
# Функция для запуска бота
async def main():
    logging.info("Бот запущен")
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())