# Generated by Django 5.1.3 on 2024-11-10 09:40

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('hacky', '0002_alter_resume_options_alter_resume_analysis_result_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='resume',
            name='achievements',
            field=models.TextField(blank=True, null=True, verbose_name='Достижения'),
        ),
        migrations.AddField(
            model_name='resume',
            name='advantages',
            field=models.TextField(blank=True, null=True, verbose_name='Ключевые преимущества'),
        ),
        migrations.AddField(
            model_name='resume',
            name='age',
            field=models.CharField(blank=True, max_length=50, null=True, verbose_name='Возраст'),
        ),
        migrations.AddField(
            model_name='resume',
            name='career_plan',
            field=models.TextField(blank=True, null=True, verbose_name='Карьерный план'),
        ),
        migrations.AddField(
            model_name='resume',
            name='career_progression',
            field=models.TextField(blank=True, null=True, verbose_name='Карьерная прогрессия'),
        ),
        migrations.AddField(
            model_name='resume',
            name='corporate_compatibility',
            field=models.TextField(blank=True, null=True, verbose_name='Корпоративная совместимость'),
        ),
        migrations.AddField(
            model_name='resume',
            name='education',
            field=models.TextField(blank=True, null=True, verbose_name='Образование'),
        ),
        migrations.AddField(
            model_name='resume',
            name='full_name',
            field=models.CharField(blank=True, max_length=255, null=True, verbose_name='ФИО'),
        ),
        migrations.AddField(
            model_name='resume',
            name='growth_zones',
            field=models.TextField(blank=True, null=True, verbose_name='Зоны роста'),
        ),
        migrations.AddField(
            model_name='resume',
            name='location',
            field=models.CharField(blank=True, max_length=255, null=True, verbose_name='Локация'),
        ),
        migrations.AddField(
            model_name='resume',
            name='motivation',
            field=models.TextField(blank=True, null=True, verbose_name='Мотивация и стремления'),
        ),
        migrations.AddField(
            model_name='resume',
            name='personality_profile',
            field=models.TextField(blank=True, null=True, verbose_name='Личностный профиль'),
        ),
        migrations.AddField(
            model_name='resume',
            name='rating',
            field=models.IntegerField(default=0, verbose_name='Общий рейтинг'),
        ),
        migrations.AddField(
            model_name='resume',
            name='recommendations',
            field=models.TextField(blank=True, null=True, verbose_name='Рекомендации'),
        ),
        migrations.AddField(
            model_name='resume',
            name='recommended_positions',
            field=models.TextField(blank=True, null=True, verbose_name='Рекомендуемые позиции'),
        ),
        migrations.AddField(
            model_name='resume',
            name='risks',
            field=models.TextField(blank=True, null=True, verbose_name='Потенциальные риски'),
        ),
        migrations.AddField(
            model_name='resume',
            name='soft_skills',
            field=models.TextField(blank=True, null=True, verbose_name='Soft skills'),
        ),
        migrations.AddField(
            model_name='resume',
            name='technical_skills',
            field=models.TextField(blank=True, null=True, verbose_name='Технические навыки'),
        ),
        migrations.AddField(
            model_name='resume',
            name='work_experience',
            field=models.TextField(blank=True, null=True, verbose_name='Опыт работы'),
        ),
        migrations.AlterField(
            model_name='resume',
            name='analysis_result',
            field=models.TextField(blank=True, null=True, verbose_name='Оригинальный анализ'),
        ),
    ]
