from django.contrib import admin
from .models import Resume
from django.utils.html import format_html
from django.utils.safestring import mark_safe

@admin.register(Resume)
class ResumeAdmin(admin.ModelAdmin):
    list_display = ('id', 'full_name', 'location', 'get_rating_display', 'uploaded_at')
    list_filter = ('uploaded_at', 'location')
    search_fields = ('full_name', 'education', 'work_experience')
    
    def get_rating_display(self, obj):
        """Отображение рейтинга с цветовой индикацией"""
        if obj.rating >= 80:
            color = 'green'
        elif obj.rating >= 60:
            color = 'orange'
        else:
            color = 'red'
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}/100</span>',
            color,
            obj.rating
        )
    get_rating_display.short_description = 'Рейтинг'

    fieldsets = (
        ('Основная информация', {
            'fields': (
                'file', 
                'uploaded_at',
                ('full_name', 'age', 'location'),
            ),
        }),
        ('Образование и опыт', {
            'fields': ('education', 'work_experience', 'career_progression'),
            'classes': ('collapse',),
        }),
        ('Навыки и характеристики', {
            'fields': (
                'technical_skills', 
                'soft_skills',
                'personality_profile',
                'achievements'
            ),
            'classes': ('collapse',),
        }),
        ('Карьерные перспективы', {
            'fields': (
                'motivation',
                'corporate_compatibility',
                'recommended_positions',
                'career_plan'
            ),
            'classes': ('collapse',),
        }),
        ('Оценка', {
            'fields': (
                'rating',
                'advantages',
                'growth_zones',
                'recommendations',
                'risks'
            ),
            'classes': ('collapse',),
        }),
    )

    readonly_fields = ('uploaded_at',)
