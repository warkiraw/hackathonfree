import os
import asyncio
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from groq import Groq  # Импортируем Groq
import aiohttp
from bs4 import BeautifulSoup
import PyPDF2
import google.generativeai as genai
from google.generativeai import GenerativeModel
import chardet
import re

# Настройка токенов
TELEGRAM_TOKEN = '7987759481:AAH15QEjfrVo0WquQDgN6FiUDNMy1z0RVtY'
GOOGLE_API_KEY = 'AIzaSyC6gyL0t2vzDVNijIMbf1VL-igqPw-PsY4'
SERPER_API_KEY = '2acc6a32f0a821eb77ef33a98134cdc6b8830168'

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Инициализация бота и диспетчера
bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

# Инициализация Gemini
genai.configure(api_key=GOOGLE_API_KEY)
model = GenerativeModel('gemini-pro')

async def search_google(query):
    url = "https://google.serper.dev/search"
    headers = {
        'X-API-KEY': SERPER_API_KEY,
        'Content-Type': 'application/json'
    }
    payload = {
        'q': query,
        'num': 10
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload) as response:
                results = await response.json()
                return results.get('organic', [])
    except Exception as e:
        logger.error(f"Ошибка при поиске: {e}")
        return []

async def get_page_content(url):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    # Пытаемся определить кодировку из заголовков
                    content_type = response.headers.get('content-type', '').lower()
                    charset = None
                    
                    if 'charset=' in content_type:
                        charset = content_type.split('charset=')[-1]
                    
                    # Читаем содержимое как bytes
                    content = await response.read()
                    
                    try:
                        # Пробуем разные кодировки
                        if charset:
                            return content.decode(charset)
                        try:
                            return content.decode('utf-8')
                        except UnicodeDecodeError:
                            try:
                                return content.decode('cp1251')  # Для русских сайтов
                            except UnicodeDecodeError:
                                try:
                                    return content.decode('latin1')
                                except UnicodeDecodeError:
                                    # Используем chardet для определения кодировки
                                    detected = chardet.detect(content)
                                    if detected['encoding']:
                                        return content.decode(detected['encoding'])
                    except Exception as e:
                        logger.error(f"Ошибка декодирования контента: {e}")
                        # Возвращаем хотя бы часть контента, игнорируя проблемные символы
                        return content.decode('utf-8', errors='ignore')
                return None
    except Exception as e:
        logger.error(f"Ошибка при получении контента страницы: {e}")
        return None

async def process_with_chatgpt(query, search_results, user_role):
    try:
        context = "\n\n".join([f"Источник {i+1}:\n{result.get('snippet', '')}"
                               for i, result in enumerate(search_results)])
        
        prompt = f"""Сосредоточься на краткой реально краткой оценке заведения и выявлении ключевых характеристик.

Информация из поиска: {context}
Роль пользователя: {user_role}

Твоя цель:
1. Дай краткое описание заведения (2-3 предложения)
2. Оцени уровень заведения (высокий/средний/низкий)
3. Определи 3-4 ключевых навыка выпускников/сотрудников
4. Дай общий рейтинг от 1 до 10

Результат должен быть кратким, без лишних слов."""
        
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        logger.error(f"Ошибка при обработке через Gemini: {e}")
        return "Извините, произошла ошибка при обработке информации."

async def summarize_analysis(analyses, resume_analysis):
    try:
        prompt = f"""Создай итоговую оценку кандидата на основе:

Анализ резюме:
{resume_analysis}

Анализ организаций:
{analyses}

Структура ответа:
1. ПРОФИЛЬ (опыт, специализация, желаемая позиция)
2. КОМПЕТЕНЦИИ (ключевые навыки и умения)
3. ОЦЕНКА (сильные стороны, области развития)
4. РЕКОМЕНДАЦИЯ (рейтинг 1-10 и краткий вывод)

Ответ должен быть кратким и конкретным."""

        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        logger.error(f"Ошибка при создании итогового анализа: {e}")
        return "Извините, произошла ошибка при создании итогового анализа."

async def extract_info_from_pdf(file_path):
    with open(file_path, 'rb') as pdf_file:
        reader = PyPDF2.PdfReader(pdf_file)
        text = ''
        for page in reader.pages:
            text += page.extract_text() + '\n'
    return text

async def analyze_resume(resume_text):
    try:
        prompt = """Проанализируй резюме и предоставь структурированную информацию в следующем формате:

ОСНОВНЫЕ_ДАННЫЕ
- ФИО:
- Возраст:
- Локация:

ОПЫТ_РАБОТЫ
- Компания:
- Должность:
- Период:
(для каждого места работы)

ОБРАЗОВАНИЕ
- Учебное заведение:
- Специальность:
- Период:
(для каждого места учебы)

НАВЫКИ
- Технические:
- Soft skills:

ДОСТИЖЕНИЯ
- (список достижений)

ОРГАНИЗАЦИИ
[START_ORG]
(список всех компаний и учебных заведений)
[END_ORG]"""

        response = model.generate_content(prompt + "\n\nРезюме:\n" + resume_text)
        return response.text
    except Exception as e:
        logger.error(f"Ошибка при анализе резюме: {e}")
        return None

async def analyze_organization(org_name):
    try:
        # Поиск информации
        search_results = await search_google(f"{org_name} отзывы рейтинг")
        
        # Собираем текст со всех найденных страниц
        texts = []
        for result in search_results[:3]:  # Ограничиваем до 3 результатов
            if content := await get_page_content(result.get('link', '')):
                texts.append(content)
        
        combined_text = "\n".join(texts)
        
        # Анализ организации через Gemini
        prompt = f"""Проанализируй организацию {org_name} на основе следующей информации:
{combined_text}

Предоствь краткий анализ в формате:
1. Уровень организации (высокий/средний/низкий)
2. Ключевые компетенции выпускников/сотрудников
3. Рейтинг (1-10)
4. Краткий вывод (1-2 предложения)"""

        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        logger.error(f"Ошибка при анализе организации {org_name}: {e}")
        return None

async def analyze_organization_details(org_name, org_type):
    try:
        # Формируем запрос в зависимости от типа организации
        query = f"{org_name} "
        if "университет" in org_name.lower() or "институт" in org_name.lower():
            query += "отзывы выпускников рейтинг образование"
        else:
            query += "отзывы сотрудников условия работы проекты"

        # Поиск информации
        search_results = await search_google(query)
        
        # Собираем текст с первых 3 результатов
        texts = []
        for result in search_results[:3]:
            if content := await get_page_content(result.get('link', '')):
                texts.append(content)
        
        combined_text = "\n".join(texts)
        
        # Анализ через Gemini с учетом типа организации
        if "университет" in org_name.lower() or "институт" in org_name.lower():
            prompt = f"""На основе информации об учебном заведении {org_name}:
{combined_text}

Предоставь краткий анализ:
1. Уровень учебного заведения (высокий/средний/низкий)
2. Основные компетенции выпускников
3. Сильные стороны образовательной программы
4. Рейтинг вуза (1-10)"""
        else:
            prompt = f"""На основе информации о компании {org_name}:
{combined_text}

Предоставь краткий анализ:
1. Уровень компании на рынке (высокий/средний/низкий)
2. Основные проекты и направления
3. Требуемые компетенции сотрудников
4. Рейтинг как работодателя (1-10)"""

        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        logger.error(f"Ошибка при анализе организации {org_name}: {e}")
        return f"Не удалось получить информацию о {org_name}"

async def create_final_analysis(resume_analysis, org_analyses, style_analysis, career_analysis):
    try:
        prompt = f"""Создай итоговую оценку кандидата на основе:

Анализ резюме:
{resume_analysis}

Анализ мест работы и учебы:
{org_analyses}

Анализ стиля и характера:
{style_analysis}

Анализ карьерной прогрессии:
{career_analysis}

Сформируй ответ в виде:

**Карточка кандидата**

**1. ОСНОВНАЯ ИНФОРМАЦИЯ**
(ФИО, возраст, локация)

**2. ОБРАЗОВАНИЕ**
(учебные заведения с анализом их уровня)

**3. ПРОФЕССИОНАЛЬНЫЙ ОПЫТ**
(места работы с анализом компаний)

**4. КАРЬЕРНАЯ ПРОГРЕССИЯ**
(анализ карьерного роста, стабильности и лояльности)

**5. КЛЮЧЕВЫЕ НАВЫКИ**
(технические и soft skills)

**6. ЛИЧНОСТНЫЙ ПРОФИЛЬ**
- Тип личности и стиль работы
- Эмоциональный интеллект
- Коммуникативные особенности
- Подход к решению задач

**7. ПРОФЕССИОНАЛЬНЫЕ ДОСТИЖЕНИЯ**
- Реальные достижения
- Потенциальные достижения на основе опыта
- Влияние на бизнес-процессы

**8. МОТИВАЦИЯ И СТРЕМЛЕНИЯ**
- Карьерные интересы
- Направления развития
- Потенциальные цели

**9. КОРПОРАТИВНАЯ СОВМЕСТИМОСТЬ**
- Предпочтительный тип организации
- Адаптивность к корпоративной культуре
- Опыт работы в разных средах

**10. РЕКОМЕНДУЕМЫЕ ПОЗИЦИИ**
(список из 5-7 должностей с процентом соответствия)

**11. КАРЬЕРНЫЙ ПЛАН**
- Краткосрочные рекомендации (1-2 года)
- Среднесрочные перспективы (3-5 лет)
- Рекомендуемые направления развития

**12. ОБЩИЙ РЕЙТИНГ**
(оценка из 100 баллов с детальным обоснованием)

В заключении добавь:
1. Ключевые преимущества кандидата
2. Зоны роста и развития
3. Конкретные рекомендации по развитию
4. Потенциальные риски и способы их минимизации"""

        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        logger.error(f"Ошибка при создании итогового анализа: {e}")
        return None

async def search_place_info(place_name):
    query = f"{place_name} отзывы, рейтинг, новости"
    return await search_google(query)

def extract_places(analysis_result):
    try:
        # Ищем список организаций между маркерами
        start_marker = "[START_ORG]"
        end_marker = "[END_ORG]"
        org_section = analysis_result[analysis_result.find(start_marker):analysis_result.find(end_marker)]
        
        # Разбираем на отдельные организации
        organizations = []
        for line in org_section.split('\n'):
            if line.strip() and not line.startswith('[') and not line.endswith(']'):
                organizations.append(line.strip())
        
        return list(set(organizations))  # Удаляем дубликаты
    except:
        return []

@dp.message(Command('start')) 
async def cmd_start(message: types.Message): 
    await message.answer( 
        "Привет! Я бот, который может анализировать резюме и оценивать квалификацию кандидатов.\n" 
        "Отправьте мне PDF файл с резюме, и я проведу анализ." 
    )
def extract_education_info(text):
    education_lines = []
    capture = False
    for line in text.split('\n'):
        if "Образование:" in line:
            capture = True
        elif capture and line.strip() == "":
            break
        elif capture:
            education_lines.append(line.strip())
    return "\n".join(education_lines)

def extract_organizations_from_analysis(analysis_text):
    organizations = []
    
    # Ищем учебные заведения
    education_section = re.search(r'\*\*2\.\s*ОБРАЗОВАНИЕ\*\*\n(.*?)(?=\*\*3\.)', analysis_text, re.DOTALL)
    if education_section:
        edu_text = education_section.group(1)
        # Ищем названия учебных заведений
        edu_orgs = re.findall(r'-\s*(.*?)(?:\(|,|\d|$)', edu_text)
        organizations.extend([org.strip() for org in edu_orgs if org.strip()])

    # Ищем места работы
    work_section = re.search(r'\*\*3\.\s*ПРОФЕССИОНАЛЬНЫЙ ОПЫТ\*\*\n(.*?)(?=\*\*4\.)', analysis_text, re.DOTALL)
    if work_section:
        work_text = work_section.group(1)
        # Ищем названия компаний
        work_orgs = re.findall(r'(?:ТОО|АО)\s*[«"]([^»"]+)[»"]|(?:Филиал|Компания)\s+([^,\n]+)', work_text)
        for matches in work_orgs:
            org = next((match for match in matches if match), None)
            if org:
                organizations.append(org.strip())

    # Убираем дубликаты и пустые значения
    organizations = list(set(filter(None, organizations)))
    
    # Очищаем названия от лишних символов
    cleaned_organizations = []
    for org in organizations:
        # Убираем указания на форму собственности и лишние пробелы
        cleaned = re.sub(r'^(ТОО|АО)\s*[«"]?\s*|\s*[»"]$', '', org)
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        if cleaned and len(cleaned) > 2:  # Проверяем, что название не слишком короткое
            cleaned_organizations.append(cleaned)
    
    return cleaned_organizations

async def analyze_resume_style(resume_text):
    try:
        prompt = """Проанализируй стиль написания резюме и определи характер человека. Обрати внимание на:

1. СТИЛЬ КОММУНИКАЦИИ
- Формальность/неформальность изложения
- Структурированность информации
- Использование профессиональной терминологии
- Эмоциональная окраска текста

2. ЭМОЦИОНАЛЬНЫЙ ИНТЕЛЛЕКТ
- Способ описания достижений
- Отношение к коллегам/руководству
- Умение презентовать свой опыт
- Уровень самопрезентации

3. ПРОФЕССИОНАЛЬНАЯ ЗРЕЛОСТЬ
- Глубина описания опыта
- Акценты в карьерных достижениях
- Понимание бизнес-процессов
- Уровень ответственности

4. МОТИВАЦИЯ И СТРЕМЛЕНИЯ
- Указания на саморазвитие
- Карьерные амбиции
- Профессиональные интересы
- Готовность к изменениям

Сформируй развернутый анализ личности, включая:
1. Тип личности и стиль работы
2. Уровень эмоционального интеллекта
3. Подход к решению задач
4. Коммуникативные особенности
5. Потенциальные сильные стороны
6. Возможные зоны роста"""

        response = model.generate_content(prompt + "\n\nТекст резюме:\n" + resume_text)
        return response.text
    except Exception as e:
        logger.error(f"Ошибка при анализе стиля резюме: {e}")
        return None

async def analyze_career_progression(resume_analysis):
    try:
        prompt = f"""Проанализируй карьерный путь кандидата на основе резюме:

{resume_analysis}

Предоставь анализ по следующим параметрам:

1. КАРЬЕРНАЯ ПРОГРЕССИЯ
- Скорость роста (быстрая/средняя/медленная)
- Качество переходов (повышения/горизонтальные переходы)
- Логика карьерного пути

2. СТАБИЛЬНОСТЬ
- Средняя продолжительность работы
- Причины смены работы (если видны)
- Оценка лояльности

3. ТЕНДЕНЦИИ
- Направление развития карьеры
- Потенциал роста
- Рекомендации по развитию

Сделай акцент на динамике роста и стабильности."""

        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        logger.error(f"Ошибка при анализе карьерной прогрессии: {e}")
        return None

@dp.message()
async def handle_document(message: types.Message):
    if not (message.document and message.document.mime_type == "application/pdf"):
        await message.reply("Пожалуйста, отправьте PDF файл с резюме.")
        return

    processing_msg = await message.reply("📄 Начинаю обработку резюме...")
    
    try:
        # Получаем текст из PDF
        await processing_msg.edit_text("📄 Извлечение текста из PDF... (10%)")
        file = await bot.get_file(message.document.file_id)
        await bot.download_file(file.file_path, 'temp.pdf')
        resume_text = await extract_info_from_pdf('temp.pdf')
        
        # Анализируем резюме
        await processing_msg.edit_text("🔍 Анализ основной информации резюме... (25%)")
        resume_analysis = await analyze_resume(resume_text)
        
        # Анализируем стиль и характер
        await processing_msg.edit_text("👤 Анализ стиля написания и характера... (35%)")
        style_analysis = await analyze_resume_style(resume_text)
        
        # Анализируем карьерную прогрессию
        await processing_msg.edit_text("📈 Анализ карьерной прогрессии... (45%)")
        career_analysis = await analyze_career_progression(resume_analysis)
        
        # Извлекаем организации
        await processing_msg.edit_text("🏢 Поиск и анализ организаций... (55%)")
        organizations = extract_organizations_from_analysis(resume_analysis)
        
        # Анализируем организации
        org_analyses = []
        total_orgs = len(organizations)
        for idx, org in enumerate(organizations, 1):
            progress = 55 + (25 * idx / total_orgs)
            await processing_msg.edit_text(f"🔍 Анализ организации {idx}/{total_orgs}... ({int(progress)}%)")
            try:
                await asyncio.sleep(1)
                if org_analysis := await analyze_organization_details(org, "unknown"):
                    org_analyses.append(f"\n### {org}:\n{org_analysis}")
            except Exception as e:
                logger.error(f"Ошибка при анализе организации {org}: {e}")
                continue
        
        # Создаем итоговый анализ
        await processing_msg.edit_text("📊 Формирование итогового анализа... (90%)")
        final_analysis = await create_final_analysis(
            resume_analysis,
            "\n".join(org_analyses),
            style_analysis,
            career_analysis
        )
        
        # Отправляем результат
        await processing_msg.edit_text("✅ Завершение анализа... (100%)")
        if final_analysis:
            if len(final_analysis) > 4096:
                for x in range(0, len(final_analysis), 4096):
                    part = final_analysis[x:x+4096]
                    await message.answer(part)
            else:
                await processing_msg.edit_text(final_analysis)
        else:
            raise Exception("Не удалось создать итоговый анализ")
            
        os.remove('temp.pdf')
        
    except Exception as e:
        logger.error(f"Ошибка при обработке PDF: {e}")
        await processing_msg.edit_text("😔 Произошла ошибка при обработке. Пожалуйста, попробуйте еще раз.")

# Вспомогательная функция для извлечения информации из анализа резюме
def extract_info(text, key):
    lines = text.split('\n')
    for line in lines:
        if key in line:
            return line.split(key)[1].strip()
    return "[Информация отсутствует]"
# Функция для получения краткого анализа от GPT
async def get_brief_analysis(full_analysis):
    try:
        prompt = f"Сократи следующий анализ до 2-3 ключевых предложений:\n\n{full_analysis}"
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        logger.error(f"Ошибка при создании краткого анализа: {e}")
        return "Извините, произошла ошибка при создании краткого анализа."

async def main(): 
    logging.info("Бот запущен") 
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())