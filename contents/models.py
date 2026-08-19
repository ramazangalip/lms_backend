from django.db import models
from django.contrib import admin
from django.contrib.auth import get_user_model

User = get_user_model()

class WeeklyContent(models.Model):
    week_number = models.IntegerField(unique=True, verbose_name="Hafta")
    title = models.CharField(max_length=200, blank=True, null=True, verbose_name="Hafta Başlığı")
    description = models.TextField(blank=True, null=True, verbose_name="Ders Notları")

    release_date = models.DateTimeField(
        null=True, 
        blank=True, 
        verbose_name="Erişime Açılma Tarihi",
        help_text="Bu tarih gelmeden öğrenci içeriğe erişemez."
    )
    due_date = models.DateTimeField(
        null=True, 
        blank=True, 
        verbose_name="Erişime Kapanma (Pasif Olma) Tarihi",
        help_text="Bu tarih geçtikten sonra öğrenci içeriğe erişemez."
    )
    

    intro_title = models.CharField(max_length=255, default="Genel Tanıtım", blank=True, null=True, verbose_name="Tanıtım Başlığı")
    intro_video_url = models.URLField(blank=True, null=True, verbose_name="Tanıtım Videosu (Embed Link)")
    intro_description = models.TextField(blank=True, null=True, verbose_name="Tanıtım Metni/Açıklaması")

    class Meta:
        verbose_name = "Haftalık İçerik"
        verbose_name_plural = "Haftalık İçerikler"
        ordering = ['week_number']

    def __str__(self):
        return f"Hafta {self.week_number} - {self.title or ''}"

class WeeklyContentSchedule(models.Model):
    weekly_content = models.ForeignKey(
        WeeklyContent,
        related_name='schedules',
        on_delete=models.CASCADE,
        verbose_name="Haftalık İçerik"
    )
    department = models.CharField(max_length=100, verbose_name="Bölüm Kodu")
    release_date = models.DateTimeField(
        null=True, 
        blank=True, 
        verbose_name="Erişime Açılma Tarihi"
    )
    due_date = models.DateTimeField(
        null=True, 
        blank=True, 
        verbose_name="Erişime Kapanma (Pasif Olma) Tarihi"
    )

    class Meta:
        verbose_name = "Bölüm Bazlı Hafta Takvimi"
        verbose_name_plural = "Bölüm Bazlı Hafta Takvimleri"
        unique_together = ('weekly_content', 'department')

    def __str__(self):
        return f"Hafta {self.weekly_content.week_number} - {self.department}"

class IntroVideoCompletion(models.Model):
    """
    SİSTEM GENELİ TEK TANITIM VİDEOSU TAKİBİ
    Öğrenci Hafta 1'deki videoyu bir kez izlediğinde OneToOneField sayesinde
    tüm haftaların kilidini açan global bir anahtar görevi görür.
    """
    student = models.OneToOneField(
        User, 
        on_delete=models.CASCADE, 
        related_name='intro_status',
        verbose_name="Öğrenci"
    )
    is_watched = models.BooleanField(default=False, verbose_name="İzledi mi?")
    watched_at = models.DateTimeField(auto_now_add=True, verbose_name="İzleme Tarihi")

    class Meta:
        verbose_name = "Genel Tanıtım Tamamlama"
        verbose_name_plural = "Genel Tanıtım Tamamlamaları"

    def __str__(self):
        status = "Tamamladı" if self.is_watched else "Tamamlamadı"
        return f"{self.student.email} - {status}"

class Material(models.Model):
    CONTENT_TYPES = (
        ('video', 'Video'),
        ('podcast', 'Podcast'),
        ('form', 'Bilgi Testi'),
        ('pdf', 'Ders Notu (PDF)'),
        ('assignment', 'Ödev (Microsoft Form)'),
    )
    parent_content = models.ForeignKey(
        WeeklyContent, 
        related_name='materials', 
        on_delete=models.CASCADE
    )
    content_type = models.CharField(max_length=10, choices=CONTENT_TYPES, blank=True, null=True)
    embed_url = models.URLField(verbose_name="Materyal Linki", help_text="Video/Podcast embed kodu veya OneDrive PDF indirme linki.", blank=True, null=True)
    title = models.CharField(max_length=200, verbose_name="Materyal Başlığı", blank=True, null=True)
    point_value = models.PositiveIntegerField(default=1, verbose_name="Tamamlama Puanı", blank=True, null=True)
    min_duration_seconds = models.PositiveIntegerField(default=300, verbose_name="Minimum İzleme/Dinleme Süresi (Saniye)", blank=True, null=True)

    def __str__(self):
        return f"{self.get_content_type_display()} - {self.title}"
    


class StudentProgress(models.Model):
    student = models.ForeignKey(User, on_delete=models.CASCADE)
    weekly_content = models.ForeignKey(WeeklyContent, on_delete=models.CASCADE)
    is_completed = models.BooleanField(default=False)
    completion_percentage = models.FloatField(default=0.0) 
    last_accessed = models.DateTimeField(auto_now=True)
    
    # YENİ ALAN: Öğrenci şu an hangi turda? (1 veya 2)
    current_attempt_round = models.PositiveIntegerField(default=1, verbose_name="Aktif Deneme Turu")

    class Meta:
        unique_together = ('student', 'weekly_content')
        verbose_name = "Öğrenci İlerlemesi"
        verbose_name_plural = "Öğrenci İlerlemeleri"

class TimeTracking(models.Model):
    student = models.ForeignKey(User, on_delete=models.CASCADE)
    weekly_content = models.ForeignKey(WeeklyContent, on_delete=models.CASCADE)
    material = models.ForeignKey(Material, on_delete=models.CASCADE, null=True, blank=True)
    duration_seconds = models.PositiveIntegerField(default=0)
    date = models.DateField(auto_now_add=True)
    
    attempt_round = models.PositiveIntegerField(default=1)

    class Meta:
        verbose_name = "Zaman Takibi"
        verbose_name_plural = "Zaman Takipleri"
        indexes = [
            models.Index(fields=['student', 'weekly_content', 'material', 'attempt_round', 'date']),
        ]

    def __str__(self):
        return f"{self.student.email} - Tur {self.attempt_round} - {self.duration_seconds}s"
    
class CompletedMaterial(models.Model):
    student = models.ForeignKey(User, on_delete=models.CASCADE)
    material = models.ForeignKey(Material, on_delete=models.CASCADE)
    completed_at = models.DateTimeField(auto_now_add=True)
    
    # YENİ ALAN: Hangi turda tamamlandı?
    attempt_round = models.PositiveIntegerField(default=1)

    class Meta:
        # Artık bir öğrenci bir materyali farklı turlarda tamamlayabilir
        unique_together = ('student', 'material', 'attempt_round')

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
    """Sınavın içindeki her bir soru"""
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name='questions')
    question_text = models.TextField()
    order = models.PositiveIntegerField(default=0)
    # --- YENİ ALAN: HAZIR ANALİZ ---
    explanation = models.TextField(
        null=True, 
        blank=True, 
        verbose_name="Soru Analizi / Açıklaması",
        help_text="Öğrenci bu soruyu yanlış yaptığında gösterilecek hazır yapay zeka veya hoca analizi."
    )

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
    student = models.ForeignKey(User, on_delete=models.CASCADE)
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE)
    score = models.IntegerField() 
    correct_answers = models.IntegerField()
    wrong_answers = models.IntegerField()
    completed_at = models.DateTimeField(auto_now_add=True)
    
    # YENİ ALAN: AI analizi öncesi (1) veya sonrası (2) deneme
    attempt_round = models.PositiveIntegerField(default=1)

    # YENİ ALAN: Üstbilişsel Tahmin / Kalibrasyon
    predicted_score = models.FloatField(null=True, blank=True, verbose_name="Tahmin Edilen Puan")

    @property
    def calibration_gap(self):
        if self.predicted_score is not None:
            return round(abs(self.predicted_score - self.score), 2)
        return None

    def __str__(self):
        return f"{self.student.first_name} - Tur {self.attempt_round} - %{self.score}"

class StudentAnswer(models.Model):
    """Öğrencinin her bir soruya verdiği spesifik cevap"""
    attempt = models.ForeignKey(StudentQuizAttempt, on_delete=models.CASCADE, related_name='answers')
    question = models.ForeignKey(QuizQuestion, on_delete=models.CASCADE)
    selected_option = models.ForeignKey(QuizOption, on_delete=models.CASCADE)
    is_correct = models.BooleanField()

# ... Diğer modellerin (WeeklyContent, Material vb.) aynı kalıyor ...

class Flashcard(models.Model):
    """
    Flashcard'ları 'Haftalık Kaynaklar' olarak güncelliyoruz.
    question -> Kaynağın Başlığı (Örn: Haftalık Özet PDF)
    answer   -> OneDrive Linki
    """
    weekly_content = models.ForeignKey(
        WeeklyContent, 
        related_name='flashcards', 
        on_delete=models.CASCADE
    )
    # Alan isimlerini veritabanını bozmamak için aynı tutuyoruz 
    # ama açıklama ve verbose_name'leri güncelliyoruz.
    question = models.TextField(verbose_name="Kaynak Başlığı")
    answer = models.TextField(verbose_name="OneDrive Linki") 
    order = models.IntegerField(default=0)

    class Meta:
        ordering = ['order']
        verbose_name = "Haftalık Kaynak"
        verbose_name_plural = "Haftalık Kaynaklar"

    def __str__(self):
        return f"{self.weekly_content.week_number}. Hafta - {self.question}"

# --- ÖNDEĞERLENDİRME (PRE-TEST) SİSTEMİ ---

class PreTestQuestion(models.Model):
    """Sistem girişinde sorulacak zorunlu ön test soruları"""
    question_text = models.TextField(verbose_name="Soru Metni")
    order = models.PositiveIntegerField(default=0, verbose_name="Sıralama")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['order']
        verbose_name = "Ön Test Sorusu"
        verbose_name_plural = "Ön Test Soruları"

    def __str__(self):
        return self.question_text[:50]

class PreTestOption(models.Model):
    """Ön test sorularının seçenekleri"""
    question = models.ForeignKey(PreTestQuestion, related_name='options', on_delete=models.CASCADE)
    option_text = models.CharField(max_length=255, verbose_name="Seçenek Metni")
    is_correct = models.BooleanField(default=False, verbose_name="Doğru Şık mı?")

    def __str__(self):
        return f"{self.option_text} ({'Doğru' if self.is_correct else 'Yanlış'})"

class PreTestResult(models.Model):
    """Öğrencilerin ön test sonuçları ve sistem kilidini açma durumu"""
    student = models.OneToOneField(User, on_delete=models.CASCADE, related_name='pre_test_result')
    correct_answers = models.IntegerField(default=0, verbose_name="Doğru Sayısı")
    wrong_answers = models.IntegerField(default=0, verbose_name="Yanlış Sayısı")
    score = models.FloatField(default=0.0, verbose_name="Başarı Puanı")
    is_completed = models.BooleanField(default=False, verbose_name="Tamamlandı mı?")
    completed_at = models.DateTimeField(auto_now_add=True, verbose_name="Tamamlanma Tarihi")

    class Meta:
        verbose_name = "Ön Test Sonucu"
        verbose_name_plural = "Ön Test Sonuçları"

    def __str__(self):
        return f"{self.student.first_name} - Skor: {self.score}"

# --- HAFTALIK HAZIRLIK VE GEÇİCİ KİLİT SİSTEMİ ---

class WeeklyPreTestQuestion(models.Model):
    """
    Her haftanın girişinde sorulacak olan 'Hatırlatıcı' sorular.
    Örn: 3. haftaya girerken (appearing), 1. haftanın (target) konusu sorulur.
    """
    appearing_week = models.ForeignKey(
        WeeklyContent, 
        on_delete=models.CASCADE, 
        related_name='entry_questions',
        verbose_name="Hangi Haftanın Girişinde Sorulacak?"
    )
    target_week = models.ForeignKey(
        WeeklyContent, 
        on_delete=models.CASCADE, 
        related_name='referenced_by_questions',
        verbose_name="Hangi Haftanın Konusu? (Yanlışta Açılacak Hafta)"
    )
    question_text = models.TextField(verbose_name="Soru Metni")
    order = models.PositiveIntegerField(default=0, verbose_name="Sıralama")

    class Meta:
        ordering = ['order']
        verbose_name = "Haftalık Hazırlık Sorusu"
        verbose_name_plural = "Haftalık Hazırlık Soruları"

    def __str__(self):
        return f"H.{self.appearing_week.week_number} Girişi -> H.{self.target_week.week_number} Sorusu"

class WeeklyPreTestOption(models.Model):
    """Haftalık hazırlık sorularının seçenekleri"""
    question = models.ForeignKey(WeeklyPreTestQuestion, related_name='options', on_delete=models.CASCADE)
    option_text = models.CharField(max_length=255, verbose_name="Seçenek Metni")
    is_correct = models.BooleanField(default=False, verbose_name="Doğru mu?")

    def __str__(self):
        return self.option_text

class TemporaryUnlock(models.Model):
    """
    Yanlış yapılan sorular neticesinde geçmiş haftaların 
    kilitlerinin geçici olarak (2 gün) açılmasını sağlar.
    """
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name='temporary_unlocks')
    week = models.ForeignKey(WeeklyContent, on_delete=models.CASCADE)
    unlocked_at = models.DateTimeField(auto_now_add=True)
    unlock_until = models.DateTimeField(verbose_name="Kilit Ne Zamana Kadar Açık?")

    @property
    def is_active(self):
        from django.utils import timezone
        return timezone.now() < self.unlock_until

    class Meta:
        verbose_name = "Geçici Kilit Açma"
        verbose_name_plural = "Geçici Kilit Açmaları"
        unique_together = ('student', 'week') # Bir öğrenci için aynı haftada tek kayıt yeterli

class WeeklyPreTestResult(models.Model):
    """Öğrencinin her haftanın girişindeki test başarısını ve açılan telafi haftalarını tutar"""
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name="weekly_pretest_results")
    week = models.ForeignKey(WeeklyContent, on_delete=models.CASCADE)  # Hazırlık testinin sorulduğu hafta
    is_completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(auto_now=True)
    
    # --- İSTATİSTİKSEL VERİLER ---
    correct_count = models.IntegerField(default=0)
    wrong_count = models.IntegerField(default=0)
    
    # Yanlışlar sonucu açılan telafi haftalarını liste olarak tutar (Örn: [1, 3])
    # Bu veri ileride yapay zeka analizleri için çok değerli olacak.
    unlocked_weeks_json = models.JSONField(default=list, blank=True)

    class Meta:
        unique_together = ('student', 'week')
        verbose_name = "Haftalık Giriş Test Sonucu"
        verbose_name_plural = "Haftalık Giriş Test Sonuçları"

    def __str__(self):
        return f"{self.student.email} - Hafta {self.week.week_number} (D:{self.correct_count} Y:{self.wrong_count})"

    @property
    def score_percentage(self):
        total = self.correct_count + self.wrong_count
        if total == 0:
            return 0
        return round((self.correct_count / total) * 100, 2)
    
class Badge(models.Model):
    BADGE_TYPES = (
        ('first_material', 'İlk Materyal Tamamlama'),
        ('double_test_streak', '2 Hafta Üst Üste Başarı'),
        ('manual', 'Manuel (Hoca Tarafından Verilen)'),
    )

    name = models.CharField(max_length=100, verbose_name="Rozet Adı")
    description = models.TextField(verbose_name="Rozet Açıklaması")
    icon_name = models.CharField(max_length=50, help_text="Lucide ikon adı (örn: Zap, Trophy, Star)")
    color = models.CharField(max_length=20, default="#FACC15", help_text="Tailwind rengi veya HEX kodu")
    badge_type = models.CharField(max_length=30, choices=BADGE_TYPES, default='manual')
    requirement_text = models.CharField(max_length=255, verbose_name="Gereksinim Metni", help_text="Örn: 2 hafta üst üste testi tamamla")

    class Meta:
        verbose_name = "Rozet Tanımı"
        verbose_name_plural = "Rozet Tanımları"

    def __str__(self):
        return self.name

class StudentBadge(models.Model):
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name="earned_badges")
    badge = models.ForeignKey(Badge, on_delete=models.CASCADE)
    earned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('student', 'badge')
        verbose_name = "Öğrenci Rozeti"
        verbose_name_plural = "Öğrenci Rozetleri"

class Survey(models.Model):
    title = models.CharField(max_length=255, verbose_name="Anket Başlığı")
    description = models.TextField(blank=True, verbose_name="Açıklama")
    week_number = models.PositiveIntegerField(unique=True, verbose_name="Hangi Haftanın Kilidi?")

    def __str__(self):
        return f"Hafta {self.week_number} - {self.title}"

class SurveyQuestion(models.Model):
    survey = models.ForeignKey(Survey, on_delete=models.CASCADE, related_name='questions')
    text = models.TextField(verbose_name="Soru Metni")
    category = models.CharField(max_length=100, blank=True, verbose_name="Alt Boyut / Kategori")

    def __str__(self):
        return self.text[:50]

class StudentSurveyResponse(models.Model):
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name='survey_responses')
    question = models.ForeignKey(SurveyQuestion, on_delete=models.CASCADE)
    answer_value = models.IntegerField(verbose_name="Likert Değeri (1-5)")
    # Bu alan artık fiziksel olarak DB'de duracak
    answer_text = models.CharField(max_length=255, verbose_name="Seçilen Şık Metni", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('student', 'question')

    def __str__(self):
        # Burada direkt veritabanındaki sütunu (self.answer_text) döndürür
        return f"{self.student.get_full_name()} - {self.answer_text}"


# Soruları anketin içinde satır içi (inline) düzenlemek için
class SurveyQuestionInline(admin.TabularInline):
    model = SurveyQuestion
    extra = 1  # Varsayılan olarak kaç boş soru satırı görünsün?


class SurveyOption(models.Model):
    question = models.ForeignKey(SurveyQuestion, on_delete=models.CASCADE, related_name='options')
    option_text = models.CharField(max_length=255, verbose_name="Seçenek Metni")
    value = models.IntegerField(verbose_name="Puan Değeri") # 1, 2, 3, 4, 5 gibi

    def __str__(self):
        return f"{self.option_text} ({self.value})"