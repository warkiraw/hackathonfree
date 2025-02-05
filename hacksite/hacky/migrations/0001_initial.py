# Generated by Django 5.1.3 on 2024-11-10 09:06

import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Resume',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('file', models.FileField(upload_to='resumes/')),
                ('uploaded_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('analysis_result', models.TextField(blank=True, null=True)),
            ],
        ),
    ]
