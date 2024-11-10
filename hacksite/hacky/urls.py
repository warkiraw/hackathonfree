from django.urls import path
from django.views.generic import TemplateView
from .views import (
    ResumeUploadView, 
    ResumeDetailView, 
    CandidateSearchView
)

app_name = 'hacky'

urlpatterns = [
    path('upload/', ResumeUploadView.as_view(), name='upload'),
    path('resume/<int:pk>/', ResumeDetailView.as_view(), name='resume_detail'),
    path('search/', CandidateSearchView.as_view(), name='search'),
]