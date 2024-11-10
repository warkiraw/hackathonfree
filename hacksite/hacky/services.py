import os
import logging
import google.generativeai as genai
import PyPDF2
import aiohttp
from bs4 import BeautifulSoup
import chardet
import re
from google.generativeai import GenerativeModel
import requests
from asgiref.sync import sync_to_async
import json
from typing import List, Dict, Optional, Any
import google.generativeai as genai
from django.conf import settings
from django.db.models import Q
import json
from django.core.cache import cache
import hashlib
from .models import Resume

# Конфигурация API ключей
GOOGLE_API_KEY = 'AIzaSyC6gyL0t2vzDVNijIMbf1VL-igqPw-PsY4'
SERPER_API_KEY = '2acc6a32f0a821eb77ef33a98134cdc6b8830168'

# Инициализация Gemini
genai.configure(api_key=GOOGLE_API_KEY)
model = GenerativeModel('gemini-pro')

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_cache_key(query: str, filters: Dict[str, Any]) -> str:
    """Генерирует ключ кэша для поискового запроса"""
    cache_data = f"{query}:{sorted(filters.items())}"
    return f"search_results:{hashlib.md5(cache_data.encode()).hexdigest()}"

def get_analysis_cache_key(query: str) -> str:
    """Генерирует ключ кэша для анализа запроса"""
    return f"query_analysis:{hashlib.md5(query.encode()).hexdigest()}"

def analyze_search_query(query: str) -> Dict:
    """Анализирует поисковый запрос с помощью Gemini"""
    cache_key = get_analysis_cache_key(query)
    cached_result = cache.get(cache_key)
    
    if cached_result:
        return cached_result
        
    try:
        prompt = f"""Проанализируй поисковый запрос для поиска кандидатов и верни структурированный JSON:
        Запрос: {query}
        
        Формат ответа:
        {{
            "position": "название позиции",
            "required_skills": ["навык1", "навык2"],
            "similar_positions": ["похожая позиция1", "похожая позиция2"],
            "keywords": ["ключевое слово1", "ключевое слово2"]
        }}
        """
        
        response = model.generate_content(prompt)
        result = json.loads(response.text)
        
        # Кэшируем результат
        cache.set(cache_key, result, timeout=3600)
        return result
    except Exception as e:
        logger.error(f"Ошибка анализа запроса: {e}")
        return {}

def calculate_candidate_relevance(candidate: Resume, search_criteria: Dict) -> Dict[str, Any]:
    """Рассчитывает релевантность кандидата для поискового запроса"""
    try:
        relevance_score = 0
        matching_skills = []
        missing_skills = []
        
        # Проверяем рекомендуемые позиции
        if candidate.recommended_positions:
            try:
                recommended = json.loads(candidate.recommended_positions)
                search_position = search_criteria['position'].lower()
                similar_positions = [pos.lower() for pos in search_criteria.get('similar_positions', [])]
                
                # Проверяем каждую рекомендуемую позицию
                for position in recommended:
                    position_title = position['position'].lower()
                    
                    # Прямое совпадение
                    if search_position in position_title:
                        relevance_score = position['match_percentage']
                        break
                    
                    # Проверка похожих позиций
                    for similar in similar_positions:
                        if similar in position_title:
                            relevance_score = max(relevance_score, position['match_percentage'] * 0.9)
                    
                    # Проверка по ключевым словам
                    keywords = [kw.lower() for kw in search_criteria.get('keywords', [])]
                    for keyword in keywords:
                        if keyword in position_title:
                            relevance_score = max(relevance_score, position['match_percentage'] * 0.8)
            
            except json.JSONDecodeError:
                # Если recommended_positions не в JSON формате, пробуем искать по тексту
                text = candidate.recommended_positions.lower()
                if search_criteria['position'].lower() in text:
                    relevance_score = 80
        
        # Проверяем навыки
        candidate_skills = set()
        if candidate.technical_skills:
            candidate_skills.update(s.strip().lower() for s in candidate.technical_skills.split(','))
        if candidate.soft_skills:
            candidate_skills.update(s.strip().lower() for s in candidate.soft_skills.split(','))
        
        required_skills = set(s.strip().lower() for s in search_criteria.get('required_skills', []))
        
        # Находим совпадающие и недостающие навыки
        for skill in required_skills:
            if skill in candidate_skills:
                matching_skills.append(skill)
                relevance_score += 5  # Уменьшаем вес навыков
            else:
                missing_skills.append(skill)
        
        # Проверяем опыт работы
        if candidate.work_experience and search_criteria['position'].lower() in candidate.work_experience.lower():
            relevance_score += 10
        
        # Нормализуем оценку
        relevance_score = min(100, relevance_score)
        
        return {
            'relevance_score': relevance_score,
            'matching_skills': matching_skills,
            'missing_skills': missing_skills
        }
        
    except Exception as e:
        logger.error(f"Ошибка при расчете релевантности: {e}")
        return {
            'relevance_score': 0,
            'matching_skills': [],
            'missing_skills': []
        }

def search_candidates(query: str, filters: Dict[str, Any], page: int = 1, per_page: int = 10) -> Dict[str, Any]:
    """Поиск кандидатов с кэшированием и пагинацией"""
    try:
        logger.info(f"Поисковый запрос: {query}")
        logger.info(f"Фильтры: {filters}")
        
        search_criteria = analyze_search_query(query)
        logger.info(f"Критерии поиска: {search_criteria}")
        
        candidates = Resume.objects.all()
        
        # Применяем фильтры
        if filters.get('min_rating'):
            candidates = candidates.filter(rating__gte=filters['min_rating'])
        if filters.get('location'):
            candidates = candidates.filter(location__icontains=filters['location'])
        
        logger.info(f"Найдено кандидатов: {candidates.count()}")
        
        # Рассчитываем релевантность
        results = []
        for candidate in candidates:
            relevance = calculate_candidate_relevance(candidate, search_criteria)
            logger.info(f"Релевантность для кандидата {candidate.id}: {relevance}")
            
            if relevance.get('relevance_score', 0) >= filters.get('min_relevance', 0):
                results.append({
                    'candidate': candidate,
                    'relevance': relevance
                })
        
        # Сортируем результаты
        results.sort(key=lambda x: x['relevance']['relevance_score'], reverse=True)
        
        return {
            'total': len(results),
            'results': results[(page-1)*per_page:page*per_page]
        }
        
    except Exception as e:
        logger.error(f"Ошибка поиска кандидатов: {e}")
        return {'total': 0, 'results': []}

def search_google(query):
    """Синхронная версия поиска в Google"""
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
        response = requests.post(url, headers=headers, json=payload)
        results = response.json()
        return results.get('organic', [])
    except Exception as e:
        logger.error(f"Ошибка при поиске: {e}")
        return []

def get_page_content(url):
    """Синхронная версия получения контента страницы"""
    try:
        response = requests.get(url)
        if response.status_code == 200:
            content = response.content
            try:
                # Пробуем разные кодировки
                try:
                    return content.decode('utf-8')
                except UnicodeDecodeError:
                    try:
                        return content.decode('cp1251')
                    except UnicodeDecodeError:
                        try:
                            return content.decode('latin1')
                        except UnicodeDecodeError:
                            detected = chardet.detect(content)
                            if detected['encoding']:
                                return content.decode(detected['encoding'])
            except Exception as e:
                logger.error(f"Ошибка декодирования контента: {e}")
                return content.decode('utf-8', errors='ignore')
        return None
    except Exception as e:
        logger.error(f"Ошибка при получении контента страницы: {e}")
        return None

def extract_text_from_pdf(file_path):
    """Извлекает текст из PDF файла"""
    try:
        with open(file_path, 'rb') as pdf_file:
            reader = PyPDF2.PdfReader(pdf_file)
            text = ''
            for page in reader.pages:
                text += page.extract_text() + '\n'
        return text
    except Exception as e:
        logger.error(f"Ошибка при чтении PDF: {e}")
        return None

def analyze_resume(resume):
    """Анализирует загруженное резюме"""
    try:
        resume_text = extract_text_from_pdf(resume.file.path)
        if not resume_text:
            raise Exception("Не удалось извлечь текст из PDF")

        # Получаем структурированный анализ
        resume_analysis = process_with_chatgpt(resume_text, [], "HR")
        if not resume_analysis:
            raise Exception("Ошибка при анализе содержания")

        # Анализируем стиль и карьеру
        style_analysis = analyze_resume_style(resume_text)
        career_analysis = analyze_career_progression(resume_analysis)
        
        # Создаем итоговый анализ
        final_analysis = create_final_analysis(
            resume_analysis=resume_analysis,
            org_analyses=[],  # Пустой список, так как анализ организаций не критичен
            style_analysis=style_analysis,
            career_analysis=career_analysis
        )

        if not final_analysis:
            raise Exception("Не удалось создать итоговый анализ")

        return final_analysis

    except Exception as e:
        logger.error(f"Ошибка при анализе резюме: {str(e)}")
        return None

def analyze_organization(org_name):
    """Анализирует организацию"""
    try:
        search_results = search_google(f"{org_name} отзывы рейтинг")
        texts = []
        for result in search_results[:3]:
            if content := get_page_content(result.get('link', '')):
                texts.append(content)
        
        combined_text = "\n".join(texts)
        
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

def analyze_organization_details(org_name, org_type):
    """Анализирует детали организации"""
    try:
        query = f"{org_name} "
        if "университет" in org_name.lower() or "институт" in org_name.lower():
            query += "отзывы выпускников рейтинг образование"
        else:
            query += "отзывы сотрудников условия работы проекты"

        search_results = search_google(query)
        texts = []
        for result in search_results[:3]:
            if content := get_page_content(result.get('link', '')):
                texts.append(content)
        
        combined_text = "\n".join(texts)
        
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
1. Уровень компании на рынке (высокий/средний/никий)
2. Основные проекты и направления
3. Требуемые компетенции сотрудников
4. Рейтинг как работодателя (1-10)"""

        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        logger.error(f"Ошибка при анализе организации {org_name}: {e}")
        return f"Не удалось получить информацию о {org_name}"

def analyze_resume_style(resume_text):
    """Анализируют стиль написания резюме"""
    try:
        prompt = """Проанализируй стиль написания резюме и определи характер человека. Обрати внимание на:

1. СТИЛЬ КОММУНИКАЦИИ
- Формальность/неформальность изложения
- Структурированность информации
- Использование профессиональной терминологии
- Эмоциональная окраска текста

2. ЭМОЦИОНАЛЬНЫЙ ИНТЕЛЛЕКТ
- Способ описания достижений
- Отношение к коллегам/руковоству
- Умение презентовать свой опыт
- Уровень самопрезентации

3. ПРОФЕССИОНАЛЬНАЯ ЗРЕЛОСТЬ
- Глубина описания опыта
- Акценты в карьерных достижениях
- Понимание бизнес-процессов
- Уровень ответственности

4. МОТИВАЦИЯ И СТРЕМЛЕНИЯ
- Указания на самоазвитие
- Карьерные амбиции
- Профсиональные интересы
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
        logger.error(f"Ошибка при анализе тиля резюме: {e}")
        return None

def analyze_career_progression(resume_analysis):
    """Анализирует карьерную прогрессию"""
    try:
        prompt = f"""Проанализируй карьерный путь кандидата на основе резюме(все пункты обязательно должны быть заполнены):

{resume_analysis}

Предоставь анализ по следующим параметрам:

1. КАРЬЕРНАЯ ПРОГРЕССИЯ
- Скорость роста (быстрая/средняя/медленная)
- Качество переходов (повышения/горизонтаьные переходы)
- Логика карьерного пути

2. СТАБИЛЬНОСТЬ
- Средняя продолжительность работы
- Причины смены работы (если видны)
- Оценка лояльности

3. ТЕНДЕНЦИИ
- Направление развития каьеры
- Потенциал роста
- Рекомендации по развитию

Сделай акцент на динамике роста и стабильности."""

        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        logger.error(f"Ошибка при анализе карьерной прогрессии: {e}")
        return None

def calculate_rating(basic_info, skills, experience, style_analysis, career_analysis):
    """Рассчитывает общий рейтинг на основе всех параметров"""
    try:
        score = 0
        
        # Оценка базовой информации (максимум 15 баллов)
        if isinstance(basic_info, dict):
            if basic_info.get('full_name'): score += 5
            if basic_info.get('age'): score += 5
            if basic_info.get('location'): score += 5
        
        # Оценка навыков (максимум 45 баллов)
        if isinstance(skills, dict):
            technical_skills_count = len(skills.get('technical', []))
            soft_skills_count = len(skills.get('soft', []))
            score += min(technical_skills_count * 3, 30)  # Максимум 30 баллов за технические навыки
            score += min(soft_skills_count * 3, 15)  # Максимум 15 баллов за soft skills
        
        # Оценка опыта (максимум 25 баллов)
        if isinstance(experience, list):
            experience_years = 0
            for exp in experience:
                if isinstance(exp, dict) and exp.get('period'):
                    # Примерный подсчет лет из периода
                    period = exp['period'].lower()
                    if 'год' in period or 'лет' in period:
                        try:
                            years = int(''.join(filter(str.isdigit, period.split()[0])))
                            experience_years += years
                        except:
                            pass
            score += min(experience_years * 2, 25)
        
        # Оценка стиля и карьерного роста (максимум 15 баллов)
        if style_analysis: score += 10
        if career_analysis: score += 5
        
        # Нормализация оценки
        final_score = min(max(score, 0), 100)
        
        logger.info(f"Рассчитанный рейтинг: {final_score}")
        return final_score

    except Exception as e:
        logger.error(f"Ошибка при расчете рейтинга: {e}")
        return 0

def create_final_analysis(resume_analysis, org_analyses, style_analysis, career_analysis):
    """Создает итоговый анализ резюме"""
    try:
        # Извлекаем всю необходимую информацию
        basic_info = extract_basic_info(resume_analysis) or {}
        skills = extract_skills_from_analysis(resume_analysis) or {'technical': [], 'soft': []}
        experience = extract_work_experience(resume_analysis) or []
        
        # Рассчитываем рейтинг
        rating_score = calculate_rating(
            basic_info=basic_info,
            skills=skills,
            experience=experience,
            style_analysis=style_analysis,
            career_analysis=career_analysis
        )

        # Формируем итоговый анализ
        final_data = {
            'basic_info': {
                'full_name': basic_info.get('full_name', 'Не указано'),
                'age': basic_info.get('age', 'Не указано'),
                'location': basic_info.get('location', 'Не указано')
            },
            'education': basic_info.get('education', []),
            'work_experience': experience,
            'skills': {
                'technical': skills.get('technical', []),
                'soft': skills.get('soft', [])
            },
            'career_progression': {
                'growth_speed': 'Не определено',
                'transitions': 'Не определено',
                'path_logic': 'Не определено'
            },
            'rating': {
                'score': rating_score,
                'advantages': extract_advantages(resume_analysis) or 'Не указано',
                'growth_zones': extract_growth_zones(resume_analysis) or 'Не указано',
                'recommendations': extract_recommendations(resume_analysis) or 'Не указано',
                'risks': extract_risks(resume_analysis) or 'Не указано'
            }
        }

        return json.dumps(final_data, ensure_ascii=False)

    except Exception as e:
        logger.error(f"Ошибка при создании итогового анализа: {e}")
        return None

def format_data_for_admin(data):
    """Форматирует данные для красивого отображения в админке"""
    try:
        # Форматируем образование
        education = data.get('education', [])
        if isinstance(education, list):
            education_formatted = "\n".join([
                f"🎓 {edu['institution']}\n"
                f"📚 {edu['degree']}\n"
                f"📅 {edu['period']}\n"
                for edu in education
            ])
        else:
            education_formatted = education

        # Форматируем опыт работы
        work_experience = data.get('work_experience', [])
        if isinstance(work_experience, list):
            work_formatted = "\n".join([
                f"👔 {work['position']}\n"
                f"🏢 {work['company']}\n"
                f"📅 {work['period']}\n"
                f"📋 {', '.join(work['responsibilities'])}\n"
                for work in work_experience
            ])
        else:
            work_formatted = work_experience

        # Форматируем навыки
        skills = data.get('skills', {})
        technical_skills = "\n".join([f"💻 {skill}" for skill in skills.get('technical', [])])
        soft_skills = "\n".join([f"🤝 {skill}" for skill in skills.get('soft', [])])

        # Форматируем остижения
        achievements = data.get('achievements', [])
        if isinstance(achievements, list):
            achievements_formatted = "\n".join([
                f"🏆 {ach['category']}: {ach['description']}"
                for ach in achievements if isinstance(ach, dict)
            ])
        else:
            achievements_formatted = achievements

        return {
            'full_name': data['basic_info']['full_name'],
            'age': data['basic_info']['age'],
            'location': data['basic_info']['location'],
            'education': education_formatted,
            'work_experience': work_formatted,
            'career_progression': (
                f"📈 Скорость роста: {data['career_progression']['growth_speed']}\n"
                f"🔄 Переходы: {data['career_progression']['transitions']}\n"
                f"🛣️ Логика пути: {data['career_progression']['path_logic']}"
            ),
            'technical_skills': technical_skills,
            'soft_skills': soft_skills,
            'personality_profile': (
                f"👤 Тип личности: {data['personality_profile']['type']}\n"
                f"🧠 Эмоциональный интеллект: {data['personality_profile']['emotional_intelligence']}\n"
                f"💬 Коммуникация: {data['personality_profile']['communication']}\n"
                f"🎯 Решение задач: {data['personality_profile']['problem_solving']}"
            ),
            'achievements': achievements_formatted,
            'rating': data['rating']['score'],
            'advantages': "\n".join([f"✅ {adv}" for adv in data['rating']['advantages']]),
            'growth_zones': "\n".join([f"📈 {zone}" for zone in data['rating']['growth_zones']]),
            'recommendations': "\n".join([f"💡 {rec}" for rec in data['rating']['recommendations']]),
            'risks': "\n".join([f"⚠️ {risk}" for risk in data['rating']['risks']])
        }

    except Exception as e:
        logger.error(f"Ошибка при форматировании данных: {e}")
        return {}

def extract_organizations_from_analysis(analysis_text):
    """Извлекает организации из анализа"""
    try:
        organizations = []
        
        # Ищем учебные заведения
        education_section = re.search(r'\*\*2\.\s*ОБРАЗОВАНИЕ\*\*\n(.*?)(?=\*\*3\.)', analysis_text, re.DOTALL)
        if education_section:
            edu_text = education_section.group(1)
            edu_orgs = re.findall(r'-\s*(.*?)(?:\(|,|\d|$)', edu_text)
            organizations.extend([org.strip() for org in edu_orgs if org.strip()])

        # Ищм места работы
        work_section = re.search(r'\*\*3\.\s*ПРОФЕССИОНАЛЬНЫЙ ОПЫТ\*\*\n(.*?)(?=\*\*4\.)', analysis_text, re.DOTALL)
        if work_section:
            work_text = work_section.group(1)
            work_orgs = re.findall(r'(?:ТОО|АО)\s*[«"]([^»"]+)[»"]|(?:Филиал|Компания)\s+([^,\n]+)', work_text)
            for matches in work_orgs:
                org = next((match for match in matches if match), None)
                if org:
                    organizations.append(org.strip())

        return list(set(organizations))  # Удаляем дубликаты
    except Exception as e:
        logger.error(f"Ошибка при извлечении организаций: {e}")
        return []

def get_brief_analysis(full_analysis):
    """Получает краткий анализ"""
    try:
        prompt = f"Сократи следующий анализ до 2-3 ключевых предложений:\n\n{full_analysis}"
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        logger.error(f"Ошибка при создании краткого анализа: {e}")
        return "Извините, произошла ошибка при создании краткого анализа."

def process_with_chatgpt(text, history, role):
    """Обрабатывает текст с помощью ChatGPT"""
    try:
        prompt = f"""Проанализируй резюме и предоставь структурированный анализ в следующем формате:

1. ОСНОВНАЯ ИНФОРМАЦИЯ
ФИО: 
Возраст:
Локация:

2. ОБРАЗОВАНИЕ
(подробное описание образования)

3. ПРОФЕССИОНАЛЬНЫЙ ОПЫТ
(подробное описание опыта работы)

4. КАРЬЕРНАЯ ПРОГРЕССИЯ
(анализ карьерного роста)

5. КЛЮЧЕВЫЕ НАВЫКИ
Технические: (через запятую)
Soft skills: (через запятую)

6. ЛИЧНОСТНЫЙ ПРОФИЛЬ
(анализ личностных качеств)

7. ПРОФЕССИОНАЛЬНЫЕ ДОСТИЖЕНИЯ
(ключевые достижения)

8. МОТИВАЦИЯ И СТРЕМЛЕНИЯ
(анализ мотивации)

9. КОРПОРАТИВНАЯ СОВМЕСТИМОСТЬ
(оценка совместимости)

10. РЕКОМЕНДУЕМЫЕ ПОЗИЦИИ
(список подходящих позиций)

11. КАРЬЕРНЫЙ ПЛАН
(рекомендации по развитию)

12. ОБЩИЙ РЕЙТИНГ
(оценка в баллах от 0 до 100)
Ключевые преимущества:
Зоны роста:
Конкретные рекомендации:
Потенциальные риски:

Текст резюме:
{text}"""

        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        logger.error(f"Ошибка при обработке текста: {e}")
        return None

def search_place_info(place_name):
    """Поиск информации о месте"""
    query = f"{place_name} отзывы, рейтинг, новости"
    return search_google(query)

def extract_skills_from_analysis(analysis_text):
    """Извлекает навыки из анализа"""
    try:
        if isinstance(analysis_text, str):
            skills_section = re.search(r'5\. КЛЮЧЕВЫЕ НАВЫКИ(.*?)(?=\d+\.|$)', analysis_text, re.DOTALL)
            if skills_section:
                skills_text = skills_section.group(1)
                technical = re.search(r'Технические:(.*?)(?=Soft skills:|$)', skills_text, re.DOTALL)
                soft = re.search(r'Soft skills:(.*?)(?=\d+\.|$)', skills_text, re.DOTALL)
                
                return {
                    'technical': [s.strip() for s in (technical.group(1) if technical else '').split(',') if s.strip()],
                    'soft': [s.strip() for s in (soft.group(1) if soft else '').split(',') if s.strip()]
                }
        return {'technical': [], 'soft': []}
    except Exception as e:
        logger.error(f"Ошибка при извлечении навыков: {e}")
        return {'technical': [], 'soft': []}

def extract_education_info(text):
    """Извлекает информацию об образовании"""
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

def generate_recommended_positions(data):
    """Генерирует рекомендуемые позиции на основе опыта и навыков"""
    try:
        # Собираем всю релевантную информацию
        experience = [work.get('position', '') for work in data.get('work_experience', [])]
        technical_skills = data.get('skills', {}).get('technical', [])
        soft_skills = data.get('skills', {}).get('soft', [])
        industry_experience = data.get('corporate_compatibility', {}).get('experience', [])

        # Определяем уровень управленческого опыта
        management_positions = sum(1 for pos in experience if any(title in pos.lower() 
            for title in ['директор', 'рководитель', 'менеджер', 'начальник']))
        
        # Определяем основные области компетенций
        retail_experience = any('розничн' in str(exp).lower() for exp in experience + industry_experience)
        sales_experience = any('прода' in str(exp).lower() for exp in experience + industry_experience)
        marketing_experience = any('маркетинг' in str(exp).lower() for exp in experience + soft_skills)
        
        recommended_positions = []
        
        # Генерируем рекомендаии на основе опыта  навыков
        if management_positions >= 2:
            if retail_experience:
                recommended_positions.append({
                    "position": "Директор по развитию розничной сети",
                    "match_percentage": 90,
                    "reasoning": "Богатый опыт управления в розничной торговле"
                })
            
            if sales_experience:
                recommended_positions.append({
                    "position": "Коммерческий директор",
                    "match_percentage": 85,
                    "reasoning": "Опыт в продажах и управлении"
                })
                
            recommended_positions.append({
                "position": "Генеральный директор среднего бизнеса",
                "match_percentage": 80,
                "reasoning": "Обширный управленческий опыт"
            })

        if marketing_experience:
            recommended_positions.append({
                "position": "Директор по маркетингу",
                "match_percentage": 75,
                "reasoning": "Опыт в маркетинге и управлении"
            })

        if retail_experience:
            recommended_positions.append({
                "position": "Руководитель направления розничных продаж",
                "match_percentage": 85,
                "reasoning": "Специализация в розничной торговле"
            })

        # Добавляем позиции на основе последнего опыта
        latest_position = experience[0] if experience else ""
        if latest_position:
            recommended_positions.append({
                "position": f"Senior {latest_position}",
                "match_percentage": 95,
                "reasoning": "Прямое развитие текущей карьерной траектории"
            })

        # Сортируем по проценту соответствия
        recommended_positions.sort(key=lambda x: x['match_percentage'], reverse=True)
        
        # Берем топ-5 позиций
        return recommended_positions[:5]

    except Exception as e:
        logger.error(f"Ошибка при генерации рекомендуемых позиций: {e}")
        return []

def process_analysis_for_admin(analysis_text):
    """Обрабатывает анализ для удобного отображения в админке"""
    try:
        if not analysis_text:
            return {}

        # Пробуем распарсить JSON
        try:
            data = json.loads(analysis_text)
            
            # Если рекомендуемые позиции пустые, генерируем их
            if not data.get('recommended_positions'):
                data['recommended_positions'] = generate_recommended_positions(data)
            
            formatted_data = format_data_for_admin(data)
            
            # Фрматируем рекомендуемые позиции для отображения
            if data.get('recommended_positions'):
                formatted_data['recommended_positions'] = "\n".join([
                    f"👔 {pos['position']}\n"
                    f"📊 Соответствие: {pos['match_percentage']}%\n"
                    f"💡 Причина: {pos['reasoning']}\n"
                    for pos in data['recommended_positions']
                ])
            
            return formatted_data

        except json.JSONDecodeError:
            logger.warning("Не удалось распарсить JSON, используем старый метод парсинга")
            return process_analysis_old_method(analysis_text)

    except Exception as e:
        logger.error(f"Ошибка при обработке анализа для админки: {e}")
        return {}

def process_analysis_old_method(analysis_text):
    """Старый метод парсинга текстового анализа"""
    try:
        data = {}
        sections = analysis_text.split('**')
        
        for section in sections:
            section = section.strip()
            
            # Основная информация
            if '1. ОСНОВНАЯ ИНФОРМАЦИЯ' in section:
                for line in section.split('\n'):
                    if 'ФИО:' in line:
                        data['full_name'] = line.split('ФИО:')[1].strip()
                    elif 'Возраст:' in line:
                        data['age'] = line.split('Возраст:')[1].strip()
                    elif 'Локация:' in line:
                        data['location'] = line.split('Локация:')[1].strip()
            
            # Образование
            elif '2. ОБРАЗОВАНИЕ' in section:
                data['education'] = section.split('2. ОБРАЗОВАНИЕ')[1].strip()
            
            # Опт работы
            elif '3. ПРОФЕССИОНАЛЬНЫЙ ОПЫТ' in section:
                data['work_experience'] = section.split('3. ПРОФЕССИОНАЛЬНЫЙ ОПЫТ')[1].strip()
            
            # Карьерная прогрессия
            elif '4. КАРЬЕРНАЯ ПРОГРЕССИЯ' in section:
                data['career_progression'] = section.split('4. КАРЬЕРНАЯ ПРОГРЕССИЯ')[1].strip()
            
            # Навыки
            elif '5. КЛЮЧЕВЫЕ НАВЫКИ' in section:
                skills_text = section.split('5. КЛЮЧЕВЫЕ НАВЫКИ')[1]
                technical_skills = []
                soft_skills = []
                
                for line in skills_text.split('\n'):
                    if 'Технические:' in line:
                        technical_skills = [s.strip() for s in line.split('Технические:')[1].split(',')]
                    elif 'Soft skills:' in line:
                        soft_skills = [s.strip() for s in line.split('Soft skills:')[1].split(',')]
                
                data['technical_skills'] = '\n'.join(technical_skills)
                data['soft_skills'] = '\n'.join(soft_skills)
            
            # Личностный профиль
            elif '6. ЛИЧНОСТНЫЙ ПРОФИЛЬ' in section:
                data['personality_profile'] = section.split('6. ЛИЧНОСТНЫЙ ПРОФИЛЬ')[1].strip()
            
            # Достижения
            elif '7. ПРОФЕССИОНАЛЬНЫЕ ДОСТИЖЕНИЯ' in section:
                data['achievements'] = section.split('7. ПРОФЕССИОНАЛЬНЫЕ ДОСТИЖЕНИЯ')[1].strip()
            
            # Мотивация
            elif '8. МОТИВАЦИЯ И СТРЕМЛЕНИЯ' in section:
                data['motivation'] = section.split('8. МОТИВАЦИЯ И СТРЕМЛЕНИЯ')[1].strip()
            
            # Корпоративная совместимость
            elif '9. КОРПОРАТИВНАЯ СОВМЕСТИМОСТЬ' in section:
                data['corporate_compatibility'] = section.split('9. КОРПОРАТИВНАЯ СОВМЕСТИМОСТЬ')[1].strip()
            
            # Рекомендуемые позиции
            elif '10. РЕКОМЕНДУЕМЫЕ ПОЗИЦИИ' in section:
                data['recommended_positions'] = section.split('10. РЕКОМЕНДУЕМЫЕ ПОЗИЦИИ')[1].strip()
            
            # Карьерный план
            elif '11. КАРЬЕРНЫЙ ПЛАН' in section:
                data['career_plan'] = section.split('11. КАРЬЕРНЫЙ ПЛАН')[1].strip()
            
            # Рейтинг и дополнительная информация
            elif '12. ОБЩИЙ РЕЙТИНГ' in section:
                rating_text = section.split('12. ОБЩИЙ РЕЙТИНГ')[1]
                
                # Извлекаем рейтинг
                rating_match = re.search(r'(\d+)\s*баллов', rating_text)
                if rating_match:
                    data['rating'] = int(rating_match.group(1))
                else:
                    data['rating'] = 0
                
                # Извлекаем дополнительную информацию используя регулярные выражения
                advantages_match = re.search(r'Ключевые преимущества:(.*?)(?=Зоны роста:|$)', rating_text, re.DOTALL)
                if advantages_match:
                    data['advantages'] = advantages_match.group(1).strip()
                
                growth_zones_match = re.search(r'Зоны роста:(.*?)(?=Конкретные рекомендации:|$)', rating_text, re.DOTALL)
                if growth_zones_match:
                    data['growth_zones'] = growth_zones_match.group(1).strip()
                
                recommendations_match = re.search(r'Конкретные рекомендации:(.*?)(?=Потенциальные риски:|$)', rating_text, re.DOTALL)
                if recommendations_match:
                    data['recommendations'] = recommendations_match.group(1).strip()
                
                risks_match = re.search(r'Потенциальные риски:(.*?)$', rating_text, re.DOTALL)
                if risks_match:
                    data['risks'] = risks_match.group(1).strip()
                
                # Устанавливаем значения по умолчанию, если данные не найдены
                data.setdefault('advantages', 'Не указано')
                data.setdefault('growth_zones', 'Не указано')
                data.setdefault('recommendations', 'Не указано')
                data.setdefault('risks', 'Не указано')

        logger.info(f"Данные после обработки: {data}")
        return data
        
    except Exception as e:
        logger.error(f"Ошибка в методе парсинга: {e}")
        return {
            'advantages': 'Ошибка при обработке',
            'growth_zones': 'Ошибка при обработке',
            'recommendations': 'Ошибка при обработке',
            'risks': 'Ошибка при обработке',
            'rating': 0
        }

def extract_basic_info(analysis_text):
    """Извлекает основную информацию из анализа"""
    try:
        info = {}
        if isinstance(analysis_text, str):
            # Поиск ФИО
            name_match = re.search(r'ФИО:?\s*([^\n]+)', analysis_text)
            if name_match:
                info['full_name'] = name_match.group(1).strip()
            
            # Поиск возраста
            age_match = re.search(r'Возраст:?\s*([^\n]+)', analysis_text)
            if age_match:
                info['age'] = age_match.group(1).strip()
            
            # Поиск локации
            location_match = re.search(r'Локация:?\s*([^\n]+)', analysis_text)
            if location_match:
                info['location'] = location_match.group(1).strip()
            
            # Поис образования
            education_match = re.search(r'Образование:?\s*([^\n]+(?:\n[^\n]+)*)', analysis_text)
            if education_match:
                info['education'] = education_match.group(1).strip()
        
        return info
    except Exception as e:
        logger.error(f"Ошибка при извлечении основной информации: {e}")
        return {}

def extract_advantages(analysis_text):
    """Извлекает преимущества из анализа"""
    try:
        if isinstance(analysis_text, str):
            match = re.search(r'Ключевые преимущества:?\s*([^\n]+(?:\n[^\n]+)*?)(?=\n\s*(?:Зоны роста|$))', analysis_text)
            if match:
                return match.group(1).strip()
        return "Не указано"
    except Exception as e:
        logger.error(f"Ошибка при извлечении преимуществ: {e}")
        return "Не указано"

def extract_growth_zones(analysis_text):
    """Извлекает зоны роста из анализа"""
    try:
        if isinstance(analysis_text, str):
            match = re.search(r'Зоны роста:?\s*([^\n]+(?:\n[^\n]+)*?)(?=\n\s*(?:Конкретные рекомендации|$))', analysis_text)
            if match:
                return match.group(1).strip()
        return "Не указано"
    except Exception as e:
        logger.error(f"Ошибка при извлечении зон роста: {e}")
        return "Не указано"

def extract_recommendations(analysis_text):
    """Извлекает рекомендации из анализа"""
    try:
        if isinstance(analysis_text, str):
            match = re.search(r'Конкретные рекомендации:?\s*([^\n]+(?:\n[^\n]+)*?)(?=\n\s*(?:Потенциальные риски|$))', analysis_text)
            if match:
                return match.group(1).strip()
        return "Не указано"
    except Exception as e:
        logger.error(f"Ошибка при извлечении рекомендаций: {e}")
        return "Не указано"

def extract_risks(analysis_text):
    """Извлекает риски из анализа"""
    try:
        if isinstance(analysis_text, str):
            match = re.search(r'Потенциальные риски:?\s*([^\n]+(?:\n[^\n]+)*?)(?=\n\s*|$)', analysis_text)
            if match:
                return match.group(1).strip()
        return "Не указано"
    except Exception as e:
        logger.error(f"Ошибка при извлечении рисков: {e}")
        return "Не указано"

def extract_personality_info(style_analysis):
    """Извлекает информацию о личности из анализа стиля"""
    try:
        if not style_analysis:
            return "Не указано"
        
        # Извлекаем основные характеристики личности
        personality_info = re.search(r'Тип личности.*?(?=\n\n|\Z)', style_analysis, re.DOTALL)
        if personality_info:
            return personality_info.group(0).strip()
        return "Не указано"
    except Exception as e:
        logger.error(f"Ошибка при извлечении информации о личности: {e}")
        return "Не указано"

def extract_work_experience(analysis_text):
    """Извлекает опыт работы из анализа"""
    try:
        if not isinstance(analysis_text, str):
            return []
        
        # Ищем секцию с опытом работы
        experience_section = re.search(
            r'Опыт работы:?\s*([^\n]+(?:\n[^\n]+)*?)(?=\n\s*(?:[А-Я]|$))', 
            analysis_text, 
            re.DOTALL
        )
        
        if not experience_section:
            return []

        experience_text = experience_section.group(1).strip()
        
        # Разбиваем на отдельные места работы
        experiences = []
        current_experience = {}
        
        # Ищем паттерны для каждого места работы
        experience_patterns = re.finditer(
            r'(?:Компания|Организация):\s*([^\n]+)\s*'
            r'(?:Должность|Позиция):\s*([^\n]+)\s*'
            r'(?:Период|Время работы):\s*([^\n]+)\s*'
            r'(?:Обязанности|Достижения)?:?\s*([^\n]+(?:\n(?!\s*(?:Компания|Организация)).*)*)',
            experience_text,
            re.DOTALL
        )

        for match in experience_patterns:
            experiences.append({
                'company': match.group(1).strip(),
                'position': match.group(2).strip(),
                'period': match.group(3).strip(),
                'responsibilities': match.group(4).strip().split('\n') if match.group(4) else []
            })

        # Если не удалось разбить по шаблону, возвращаем весь текст как один опыт
        if not experiences:
            experiences = [{
                'company': 'Не указано',
                'position': 'Не указано',
                'period': 'Не указано',
                'responsibilities': [line.strip() for line in experience_text.split('\n') if line.strip()]
            }]

        return experiences

    except Exception as e:
        logger.error(f"Ошибка при извлечении опыта работы: {e}")
        return [{
            'company': 'Ошибка при обработке',
            'position': 'Ошибка при обработке',
            'period': 'Не указано',
            'responsibilities': []
        }]

def extract_career_info(career_analysis):
    """Извлекает информацию о карьерной прогрессии"""
    try:
        if not isinstance(career_analysis, str):
            return {
                'growth_speed': 'Не определено',
                'transitions': 'Не определено',
                'path_logic': 'Не определено',
                'progression': 'Не определено',
                'achievements': []
            }
        
        # Ищем секцию с карьерной прогрессией
        career_section = re.search(
            r'4\. КАРЬЕРНАЯ ПРОГРЕССИЯ(.*?)(?=\d+\.|$)',
            career_analysis,
            re.DOTALL
        )
        
        if not career_section:
            return {
                'growth_speed': 'Не определено',
                'transitions': 'Не определено',
                'path_logic': 'Не определено',
                'progression': 'Не определено',
                'achievements': []
            }

        career_text = career_section.group(1).strip()
        
        # Извлекаем различные аспекты карьерной прогрессии
        growth_speed = re.search(r'Скорость роста:?\s*([^\n]+)', career_text)
        transitions = re.search(r'Переходы:?\s*([^\n]+)', career_text)
        path_logic = re.search(r'Логика пути:?\s*([^\n]+)', career_text)
        progression = re.search(r'Прогрессия:?\s*([^\n]+)', career_text)
        achievements = re.findall(r'•\s*([^\n]+)', career_text)

        return {
            'growth_speed': growth_speed.group(1).strip() if growth_speed else 'Не определено',
            'transitions': transitions.group(1).strip() if transitions else 'Не определено',
            'path_logic': path_logic.group(1).strip() if path_logic else 'Не определено',
            'progression': progression.group(1).strip() if progression else 'Не определено',
            'achievements': [ach.strip() for ach in achievements] if achievements else []
        }

    except Exception as e:
        logger.error(f"Ошибка при извлечении информации о карьере: {e}")
        return {
            'growth_speed': 'Ошибка при обработке',
            'transitions': 'Ошибка при обработке',
            'path_logic': 'Ошибка при обработке',
            'progression': 'Ошибка при обработке',
            'achievements': []
        }
