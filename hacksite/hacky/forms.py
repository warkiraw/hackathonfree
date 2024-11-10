from django import forms
from .models import Resume

class ResumeUploadForm(forms.ModelForm):
    class Meta:
        model = Resume
        fields = ['file']
        
    def clean_file(self):
        file = self.cleaned_data.get('file')
        if file:
            if not file.name.endswith('.pdf'):
                raise forms.ValidationError('Только PDF файлы разрешены')
            if file.size > 5242880:  # 5MB
                raise forms.ValidationError('Файл слишком большой (максимум 5MB)')
        return file