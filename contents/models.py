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

class Quiz(models.Model):
    """Her bir test materyali için ana başlık"""
    material = models.OneToOneField('Material', on_delete=models.CASCADE, related_name='quiz')
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Test: {self.title} (Hafta {self.material.parent_content.week_number})"

class QuizQuestion(models.Model):
    """Sınavın içindeki her bir soru (Resim alanı kaldırıldı)"""
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name='questions')
    question_text = models.TextField()
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order']

    def __str__(self):
        return self.question_text[:50]

class QuizOption(models.Model):
    """Soruların şıkları (A, B, C, D...)"""
    question = models.ForeignKey(QuizQuestion, on_delete=models.CASCADE, related_name='options')
    option_text = models.CharField(max_length=255)
    is_correct = models.BooleanField(default=False)

    def __str__(self):
        return self.option_text

class StudentQuizAttempt(models.Model):
    """Öğrencinin genel sınav sonucu"""
    student = models.ForeignKey(User, on_delete=models.CASCADE)
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE)
    score = models.IntegerField() 
    correct_answers = models.IntegerField()
    wrong_answers = models.IntegerField()
    completed_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.student.first_name} - {self.quiz.title} - %{self.score}"

class StudentAnswer(models.Model):
    """Öğrencinin her bir soruya verdiği spesifik cevap"""
    attempt = models.ForeignKey(StudentQuizAttempt, on_delete=models.CASCADE, related_name='answers')
    question = models.ForeignKey(QuizQuestion, on_delete=models.CASCADE)
    selected_option = models.ForeignKey(QuizOption, on_delete=models.CASCADE)
    is_correct = models.BooleanField()

# contents/models.py

class Flashcard(models.Model):
    # BURAYI DÜZELT: on_responses -> on_delete
    weekly_content = models.ForeignKey(
        WeeklyContent, 
        related_name='flashcards', 
        on_delete=models.CASCADE  # Doğru parametre budur
    )
    question = models.TextField()
    answer = models.TextField()
    order = models.IntegerField(default=0)

    class Meta:
        ordering = ['order']

