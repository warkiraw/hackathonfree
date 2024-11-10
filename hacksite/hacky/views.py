import os
import logging
from django.shortcuts import render, redirect
from django.views.generic import CreateView, DetailView
from .models import Resume
from .forms import ResumeUploadForm
from .services import (
    analyze_resume, 
    analyze_resume_style,
    analyze_career_progression,
    extract_organizations_from_analysis,
    analyze_organization_details,
    create_final_analysis,
    extract_text_from_pdf,
    process_with_chatgpt,
    search_place_info,
    extract_skills_from_analysis,
    process_analysis_for_admin,
    search_candidates,
    calculate_candidate_relevance
)
from django.contrib import messages
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.views import View
from typing import Dict, Any
from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from django.core.exceptions import ValidationError
import json
from django.urls import reverse

logger = logging.getLogger(__name__)

class ResumeUploadView(CreateView):
    model = Resume
    form_class = ResumeUploadForm
    template_name = 'hacky/upload.html'
    
    def form_valid(self, form):
        try:
            resume = form.save()
            
            if not os.path.exists(resume.file.path):
                return JsonResponse({
                    'status': 'error',
                    'message': 'Файл не найден'
                }, status=400)

            # Запускаем анализ
            analysis_result = analyze_resume(resume)
            if not analysis_result:
                raise Exception("Не удалось выполнить анализ резюме")

            # Обрабатываем результаты анализа
            try:
                analysis_data = json.loads(analysis_result)
                
                # Обновляем поля резюме
                basic_info = analysis_data.get('basic_info', {})
                resume.full_name = basic_info.get('full_name', '')
                resume.age = basic_info.get('age', '')
                resume.location = basic_info.get('location', '')
                resume.education = json.dumps(analysis_data.get('education', []))
                resume.work_experience = json.dumps(analysis_data.get('work_experience', []))
                
                skills = analysis_data.get('skills', {})
                resume.technical_skills = ','.join(skills.get('technical', []))
                resume.soft_skills = ','.join(skills.get('soft', []))
                
                # Получаем рейтинг из структуры rating
                rating_data = analysis_data.get('rating', {})
                resume.rating = rating_data.get('score', 0) if isinstance(rating_data, dict) else 0
                
                # Сохраняем оригинальный анализ
                resume.analysis_result = analysis_result
                resume.save()

            except json.JSONDecodeError:
                raise Exception("Ошибка при обработке результатов анализа")

            return JsonResponse({
                'status': 'success',
                'redirect_url': reverse('hacky:resume_detail', kwargs={'pk': resume.pk})
            })

        except Exception as e:
            logger.error(f"Ошибка при обработке резюме: {str(e)}")
            if resume.id:
                resume.delete()  # Удаляем неудачную запись
            return JsonResponse({
                'status': 'error',
                'message': str(e)
            }, status=400)

    def form_invalid(self, form):
        return JsonResponse({
            'status': 'error',
            'message': 'Неверный формат файла'
        }, status=400)

class ResumeDetailView(DetailView):
    model = Resume
    template_name = 'hacky/detail.html'
    context_object_name = 'resume'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        resume = self.get_object()
        if resume.analysis_result:
            try:
                context['analysis'] = json.loads(resume.analysis_result)
            except json.JSONDecodeError:
                context['analysis'] = {}
        return context

class CandidateSearchView(View):
    template_name = 'hacky/search.html'
    per_page: int = 10

    def get(self, request) -> HttpResponse:
        query: str = request.GET.get('q', '')
        page: int = int(request.GET.get('page', 1))
        
        filters: Dict[str, Any] = {
            'min_rating': int(request.GET.get('min_rating', 0)),
            'location': request.GET.get('location', ''),
            'education_level': request.GET.get('education_level', ''),
            'min_relevance': int(request.GET.get('min_relevance', 0))
        }
        
        if query:
            search_results = search_candidates(query, filters, page=int(page), per_page=self.per_page)
            total_results = search_results['total']
            results = search_results['results']
            
            paginator = Paginator(range(total_results), self.per_page)
            try:
                current_page = paginator.page(page)
            except PageNotAnInteger:
                current_page = paginator.page(1)
            except EmptyPage:
                current_page = paginator.page(paginator.num_pages)
        else:
            results = []
            current_page = None
            paginator = None
        
        context = {
            'query': query,
            'filters': filters,
            'results': results,
            'page_obj': current_page,
            'paginator': paginator
        }
        return render(request, self.template_name, context)