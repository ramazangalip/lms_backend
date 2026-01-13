from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()

class WeeklyContent(models.Model):
    week_number = models.IntegerField(unique=True, verbose_name="Hafta")
    title = models.CharField(max_length=200, verbose_name="Hafta Başlığı")
    description = models.TextField(blank=True, verbose_name="Ders Notları")

    class Meta:
        verbose_name = "Haftalık İçerik"
        verbose_name_plural = "Haftalık İçerikler"
        ordering = ['week_number']

    def __str__(self):
        return f"Hafta {self.week_number} - {self.title}"

class Material(models.Model):
    CONTENT_TYPES = (
        ('video', 'Video'),
        ('podcast', 'Podcast'),
        ('form', 'Google Form'),
    )
    parent_content = models.ForeignKey(
        WeeklyContent, 
        related_name='materials', 
        on_delete=models.CASCADE
    )
    content_type = models.CharField(max_length=10, choices=CONTENT_TYPES)
    embed_url = models.URLField(verbose_name="Materyal Linki")
    title = models.CharField(max_length=200, verbose_name="Materyal Başlığı")

    def __str__(self):
        return f"{self.get_content_type_display()} - {self.title}"

# --- TAKİP MODELLERİ (WeeklyContent'e Bağlı) ---

class StudentProgress(models.Model):
    student = models.ForeignKey(User, on_delete=models.CASCADE)
    # CourseModule yerine WeeklyContent'e bağladık
    weekly_content = models.ForeignKey(WeeklyContent, on_delete=models.CASCADE)
    is_completed = models.BooleanField(default=False)
    completion_percentage = models.FloatField(default=0.0) 
    last_accessed = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('student', 'weekly_content')
        verbose_name = "Öğrenci İlerlemesi"
        verbose_name_plural = "Öğrenci İlerlemeleri"

class TimeTracking(models.Model):
    student = models.ForeignKey(User, on_delete=models.CASCADE)
    # CourseModule yerine WeeklyContent'e bağladık
    weekly_content = models.ForeignKey(WeeklyContent, on_delete=models.CASCADE)
    duration_seconds = models.PositiveIntegerField(default=0)
    date = models.DateField(auto_now_add=True)

    def __str__(self):
        return f"{self.student.email} - Hafta {self.weekly_content.week_number} - {self.duration_seconds}s"
    
class CompletedMaterial(models.Model):
    student = models.ForeignKey(User, on_delete=models.CASCADE)
    material = models.ForeignKey(Material, on_delete=models.CASCADE)
    completed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('student', 'material')

class StudentQuestion(models.Model):
    student = models.ForeignKey(User, on_delete=models.CASCADE)
    weekly_content = models.ForeignKey(WeeklyContent, on_delete=models.CASCADE)
    question_text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.student.first_name} - Hafta {self.weekly_content.week_number}"