from django.db import models
from django.utils import timezone
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError
from typing import Any
import json
import re
import logging

logger = logging.getLogger(__name__)

class Resume(models.Model):
    # Основные поля
    file = models.FileField(upload_to='resumes/', verbose_name='Файл резюме')
    uploaded_at = models.DateTimeField(default=timezone.now, verbose_name='Дата загрузки')
    
    # Основная информация
    full_name = models.CharField(max_length=255, blank=True, null=True, verbose_name='ФИО')
    age = models.CharField(max_length=50, blank=True, null=True, verbose_name='Возраст')
    location = models.CharField(max_length=255, blank=True, null=True, verbose_name='Локация')
    
    # Образование и опыт
    education = models.TextField(blank=True, null=True, verbose_name='Образование')
    work_experience = models.TextField(blank=True, null=True, verbose_name='Опыт работы')
    career_progression = models.TextField(blank=True, null=True, verbose_name='Карьерная прогрессия')
    
    # Навыки и характеристики
    technical_skills = models.TextField(blank=True, null=True, verbose_name='Технические навыки')
    soft_skills = models.TextField(blank=True, null=True, verbose_name='Soft skills')
    personality_profile = models.TextField(blank=True, null=True, verbose_name='Личностный профиль')
    achievements = models.TextField(blank=True, null=True, verbose_name='Достижения')
    
    # Карьерные перспективы
    motivation = models.TextField(blank=True, null=True, verbose_name='Мотивация и стремления')
    corporate_compatibility = models.TextField(blank=True, null=True, verbose_name='Корпоративная совместимость')
    recommended_positions = models.TextField(blank=True, null=True, verbose_name='Рекомендуемые позиции')
    career_plan = models.TextField(blank=True, null=True, verbose_name='Карьерный план')
    
    # Оценка
    rating = models.IntegerField(
        default=0, 
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        verbose_name='Общий рейтинг'
    )
    advantages = models.TextField(blank=True, null=True, verbose_name='Ключевые преимущества')
    growth_zones = models.TextField(blank=True, null=True, verbose_name='Зоны роста')
    recommendations = models.TextField(blank=True, null=True, verbose_name='Рекомендации')
    risks = models.TextField(blank=True, null=True, verbose_name='Потенциальные риски')
    
    # Сохраняем оригинальный анализ
    analysis_result = models.TextField(blank=True, null=True, verbose_name='Оригинальный анализ')

    def __str__(self):
        name = self.full_name if self.full_name else f"Резюме №{self.id}"
        return f"{name} ({self.uploaded_at.strftime('%d.%m.%Y')})"
    
    class Meta:
        verbose_name = 'Резюме'
        verbose_name_plural = 'Резюме'
        ordering = ['-uploaded_at']
        indexes = [
            models.Index(fields=['rating']),
            models.Index(fields=['location']),
            models.Index(fields=['uploaded_at']),
            models.Index(fields=['full_name']),
            # Составной индекс для часто используемых полей в поиске
            models.Index(fields=['rating', 'location']),
        ]

    def clean(self) -> None:
        """Валидация модели"""
        super().clean()
        if self.rating < 0 or self.rating > 100:
            raise ValidationError({'rating': 'Рейтинг должен быть от 0 до 100'})

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Сохранение модели"""
        self.full_clean()
        super().save(*args, **kwargs)

    def save_recommended_positions(self, positions_data):
        """Сохраняет рекомендуемые позиции в JSON формате"""
        if isinstance(positions_data, str):
            # Если получили строку, пробуем преобразовать в структурированные данные
            try:
                positions = []
                for line in positions_data.split('\n'):
                    if '📊 Соответствие:' in line:
                        position = line.split('👔')[1].split('📊')[0].strip()
                        match = re.search(r'(\d+)%', line)
                        if match:
                            percentage = int(match.group(1))
                            positions.append({
                                'position': position,
                                'match_percentage': percentage
                            })
                self.recommended_positions = json.dumps(positions)
            except Exception as e:
                logger.error(f"Ошибка при сохранении рекомендуемых позиций: {e}")
                self.recommended_positions = positions_data
        else:
            self.recommended_positions = json.dumps(positions_data)