from django import template
from django.utils.safestring import mark_safe
import json

register = template.Library()

@register.filter
def relevance_color(score):
    """Возвращает цвет в зависимости от релевантности"""
    if score >= 80:
        return mark_safe('#4CAF50')  # Зеленый
    elif score >= 60:
        return mark_safe('#FFC107')  # Желтый
    elif score >= 40:
        return mark_safe('#FF9800')  # Оранжевый
    else:
        return mark_safe('#F44336')  # Красный

@register.filter
def format_skills(skills_list):
    """Форматирует список навыков"""
    if not skills_list:
        return ''
    return ', '.join(skills_list)

@register.simple_tag
def get_page_range(paginator, current_page, show_pages=5):
    """Возвращает диапазон страниц для пагинации"""
    middle = show_pages // 2
    if paginator.num_pages <= show_pages:
        return range(1, paginator.num_pages + 1)
    
    if current_page <= middle:
        return range(1, show_pages + 1)
    elif current_page + middle >= paginator.num_pages:
        return range(paginator.num_pages - show_pages + 1, paginator.num_pages + 1)
    else:
        return range(current_page - middle, current_page + middle + 1) 

@register.filter
def parse_json(json_string):
    """Парсит JSON строку в список"""
    if not json_string:
        return []
    try:
        return json.loads(json_string)
    except:
        return []

@register.filter
def split_skills(skills_string):
    """Разделяет строку навыков на список"""
    if not skills_string:
        return []
    return [skill.strip() for skill in skills_string.split(',')]