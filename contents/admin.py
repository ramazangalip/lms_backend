from django.contrib import admin
from .models import *
from django.urls import reverse
from django.utils.safestring import mark_safe

# --- INLINES ---

class MaterialInline(admin.TabularInline):
    """Haftalık içeriklerin altına video/podcast/test eklemeyi sağlar."""
    model = Material
    extra = 1
    fields = ('content_type', 'title', 'embed_url')

class WeeklyContentScheduleInline(admin.TabularInline):
    model = WeeklyContentSchedule
    extra = 1

# --- MODELLER ---

@admin.register(WeeklyContent)
class WeeklyContentAdmin(admin.ModelAdmin):
    list_display = ('week_number', 'title', 'release_date', 'due_date', 'has_global_intro')
    list_filter = ('week_number',)
    search_fields = ('title', 'description')
    ordering = ('week_number',)
    inlines = [MaterialInline, WeeklyContentScheduleInline]

    fieldsets = (
        ('Haftalık Ders Bilgileri', {
            'fields': ('week_number', 'title', 'description', 'release_date', 'due_date')
        }),
        ('Merkezi Tanıtım Videosu (Sadece Hafta 1 İçin Doldurun)', {
            'description': (
                "Öğrencilerin tüm sistemi açmak için izlemesi gereken tek videodur. "
                "Hafta 1'e eklenen video global kilit görevi görür."
            ),
            'fields': ('intro_title', 'intro_video_url'),
            'classes': ('collapse',)
        }),
    )

    def has_global_intro(self, obj):
        return bool(obj.intro_video_url)
    has_global_intro.boolean = True
    has_global_intro.short_description = "Tanıtım Videosu Var"

@admin.register(WeeklyContentSchedule)
class WeeklyContentScheduleAdmin(admin.ModelAdmin):
    list_display = ('weekly_content', 'department', 'release_date', 'due_date')
    list_filter = ('department', 'weekly_content')
    search_fields = ('department', 'weekly_content__title')

    def formfield_for_dbfield(self, db_field, **kwargs):
        field = super().formfield_for_dbfield(db_field, **kwargs)
        if db_field.name == 'description':
            field.widget.attrs['rows'] = 5
            field.widget.attrs['style'] = 'width: 85%;'
        return field

@admin.register(IntroVideoCompletion)
class IntroVideoCompletionAdmin(admin.ModelAdmin):
    """Öğrencilerin global tanıtım videosunu bitirip bitirmediğini takip eder."""
    list_display = ('student', 'is_watched', 'watched_at')
    list_filter = ('is_watched', 'watched_at')
    search_fields = ('student__email', 'student__first_name', 'student__last_name')
    readonly_fields = ('watched_at',)

# --- TAKİP VE ANALİZ MODELLERİ ---

@admin.register(StudentProgress)
class StudentProgressAdmin(admin.ModelAdmin):
    list_display = ('student', 'weekly_content', 'get_progress', 'is_completed', 'last_accessed')
    list_filter = ('weekly_content', 'is_completed')
    search_fields = ('student__email', 'weekly_content__title')

    def get_progress(self, obj):
        return f"%{obj.completion_percentage}"
    get_progress.short_description = "İlerleme"

@admin.register(TimeTracking)
class TimeTrackingAdmin(admin.ModelAdmin):
    list_display = ('student', 'weekly_content', 'formatted_duration', 'date')
    list_filter = ('date', 'weekly_content')
    search_fields = ('student__email',)

    def formatted_duration(self, obj):
        mins = obj.duration_seconds // 60
        if mins < 60: return f"{mins} dk"
        return f"{mins // 60} sa {mins % 60} dk"
    formatted_duration.short_description = "Süre"

@admin.register(StudentQuestion)
class StudentQuestionAdmin(admin.ModelAdmin):
    list_display = ('student', 'get_week', 'short_question', 'created_at')
    list_filter = ('weekly_content', 'created_at')
    search_fields = ('student__email', 'question_text')

    def get_week(self, obj):
        return f"Hafta {obj.weekly_content.week_number}"
    
    def short_question(self, obj):
        return obj.question_text[:50] + "..." if len(obj.question_text) > 50 else obj.question_text

# --- SINAV (QUIZ) SİSTEMİ ---

class StudentAnswerInline(admin.TabularInline):
    model = StudentAnswer
    extra = 0
    readonly_fields = ('question', 'selected_option', 'is_correct')
    can_delete = False

@admin.register(StudentQuizAttempt)
class StudentQuizAttemptAdmin(admin.ModelAdmin):
    list_display = ('student', 'quiz', 'score', 'correct_answers', 'wrong_answers', 'completed_at')
    list_filter = ('quiz', 'completed_at')
    search_fields = ('student__email', 'quiz__title')
    inlines = [StudentAnswerInline]

class QuizOptionInline(admin.TabularInline):
    model = QuizOption
    extra = 4

@admin.register(QuizQuestion)
class QuizQuestionAdmin(admin.ModelAdmin):
    list_display = ('question_text', 'quiz')
    inlines = [QuizOptionInline]

@admin.register(Quiz)
class QuizAdmin(admin.ModelAdmin):
    list_display = ('title', 'material')

# Tekil kayıtlar
admin.site.register(Material)

admin.site.register(Flashcard)

# --- ÖN DEĞERLENDİRME (PRE-TEST) SİSTEMİ ---

class PreTestOptionInline(admin.TabularInline):
    """Ön test sorularının altına şık eklemeyi sağlar."""
    model = PreTestOption
    extra = 5  # Varsayılan 5 şık gelsin (A, B, C, D, E)

# --- ÖN DEĞERLENDİRME (PRE-TEST) SİSTEMİ ADMİN ---

class PreTestOptionInline(admin.TabularInline):
    """Ön test sorularının içine şıkları gömer."""
    model = PreTestOption
    extra = 4  # Yeni soru eklerken varsayılan 4 boş şık getirir
    fields = ('option_text', 'is_correct')

@admin.register(PreTestQuestion)
class PreTestQuestionAdmin(admin.ModelAdmin):
    """Soru listesi ve düzenleme paneli."""
    list_display = ('order', 'short_question', 'get_option_count')
    ordering = ('order',)
    inlines = [PreTestOptionInline]

    def short_question(self, obj):
        return obj.question_text[:75] + "..." if len(obj.question_text) > 75 else obj.question_text
    short_question.short_description = "Soru Metni"

    def get_option_count(self, obj):
        return obj.options.count()
    get_option_count.short_description = "Şık Sayısı"

@admin.register(PreTestResult)
class PreTestResultAdmin(admin.ModelAdmin):
    """Öğrencilerin sınavdan aldığı puanları listeler."""
    list_display = ('student_info', 'score_display', 'correct_answers', 'wrong_answers', 'is_completed', 'completed_at')
    list_filter = ('is_completed', 'completed_at')
    search_fields = ('student__email', 'student__first_name', 'student__last_name')
    readonly_fields = ('completed_at', 'correct_answers', 'wrong_answers', 'score', 'is_completed') # Elle değiştirilmesin

    def student_info(self, obj):
        return f"{obj.student.first_name} {obj.student.last_name} ({obj.student.email})"
    student_info.short_description = "Öğrenci"

    def score_display(self, obj):
        return f"%{obj.score}"
    score_display.short_description = "Başarı Puanı"

# --- HAFTALIK GİRİŞ (HAZIRLIK) TESTİ SİSTEMİ ADMİN ---

class WeeklyPreTestOptionInline(admin.TabularInline):
    """Her giriş sorusunun altına şıkları ekler."""
    model = WeeklyPreTestOption
    extra = 5
    fields = ('option_text', 'is_correct')

@admin.register(WeeklyPreTestQuestion)
class WeeklyPreTestQuestionAdmin(admin.ModelAdmin):
    """Haftalık hazırlık soruları yönetimi."""
    list_display = ('appearing_week_display', 'short_question', 'target_week_display', 'order')
    list_filter = ('appearing_week', 'target_week')
    ordering = ('appearing_week', 'order')
    inlines = [WeeklyPreTestOptionInline]

    def appearing_week_display(self, obj):
        return f"Hafta {obj.appearing_week.week_number}"
    appearing_week_display.short_description = "Sorulduğu Hafta"

    def target_week_display(self, obj):
        return f"Hafta {obj.target_week.week_number}"
    target_week_display.short_description = "Hata Halinde Açılacak Hafta"

    def short_question(self, obj):
        return obj.question_text[:60] + "..." if len(obj.question_text) > 60 else obj.question_text
    short_question.short_description = "Soru"

@admin.register(WeeklyPreTestResult)
class WeeklyPreTestResultAdmin(admin.ModelAdmin):
    """Öğrencilerin haftalık hazırlık test sonuçları."""
    list_display = ('student', 'week', 'is_completed', 'completed_at')
    list_filter = ('week', 'is_completed', 'completed_at')
    search_fields = ('student__email', 'student__first_name', 'student__last_name')
    readonly_fields = ('completed_at',)

# --- GEÇİCİ KİLİT AÇMA (TEMPORARY UNLOCK) SİSTEMİ ---

@admin.register(TemporaryUnlock)
class TemporaryUnlockAdmin(admin.ModelAdmin):
    """Yanlış cevap sonucu açılan geçici hafta erişimleri."""
    list_display = ('student', 'week_display', 'unlocked_at', 'unlock_until', 'is_active')
    list_filter = ('unlocked_at', 'week')
    search_fields = ('student__email',)
    readonly_fields = ('unlocked_at',)

    def week_display(self, obj):
        return f"Hafta {obj.week.week_number}"
    week_display.short_description = "Açılan Hafta"

    def is_active(self, obj):
        from django.utils import timezone
        return obj.unlock_until > timezone.now()
    is_active.boolean = True
    is_active.short_description = "Erişim Aktif mi?"

@admin.register(Badge)
class BadgeAdmin(admin.ModelAdmin):
    list_display = ('name', 'badge_type', 'icon_name', 'color')
    list_filter = ('badge_type',)

@admin.register(StudentBadge)
class StudentBadgeAdmin(admin.ModelAdmin):
    list_display = ('student', 'badge', 'earned_at')


# 1. Şıklar için Inline (Soru düzenleme sayfasında görünecek)
class SurveyOptionInline(admin.TabularInline):
    model = SurveyOption
    extra = 5  # Genelde Likert 5'lidir, 5 boş satır gelsin
    fields = ('option_text', 'value')

# 2. Sorular için Inline (Anket sayfasında görünecek)
class SurveyQuestionInline(admin.TabularInline):
    model = SurveyQuestion
    extra = 1
    # Burada 'get_options_link' ekleyerek şıklara hızlı geçiş sağlıyoruz
    readonly_fields = ('get_options_link',)
    fields = ('text', 'category', 'get_options_link')

    def get_options_link(self, obj):
        if obj.id:
            # Soru kaydedilmişse, o sorunun şıklarını düzenleme sayfasına link veriyoruz
            url = reverse('admin:contents_surveyquestion_change', args=[obj.id])
            return mark_safe(f'<a href="{url}" target="_blank">🔍 Şıkları Düzenle</a>')
        return "Önce soruyu kaydedin"
    get_options_link.short_description = "Seçenekler"

# 3. Anket Admin (Ana Yönetim)
@admin.register(Survey)
class SurveyAdmin(admin.ModelAdmin): # <--- Burayı kontrol et
    list_display = ('week_number', 'title')
    list_filter = ('week_number',)
    search_fields = ('title',)
    inlines = [SurveyQuestionInline]

# 4. Soru Admin (Şıklar burada direkt görünecek)
@admin.register(SurveyQuestion)
class SurveyQuestionAdmin(admin.ModelAdmin):
    list_display = ('text', 'survey', 'category', 'get_options_count')
    list_filter = ('survey', 'category')
    search_fields = ('text', 'category')
    # İŞTE BURASI: Sorunun içine girdiğinde şıkları (options) direkt görebilirsin
    inlines = [SurveyOptionInline]

    def get_options_count(self, obj):
            # Related name ile uğraşmadan, SurveyOption tablosuna direkt soruyoruz: 
            # "Bu soruya (obj) bağlı kaç tane şık var?"
            from .models import SurveyOption
            return SurveyOption.objects.filter(question=obj).count()
        
    get_options_count.short_description = "Şık Sayısı"

# 5. Öğrenci Cevapları Admin
@admin.register(StudentSurveyResponse)
class StudentSurveyResponseAdmin(admin.ModelAdmin):
    list_display = ('student', 'get_question_text', 'answer_text', 'answer_value', 'created_at')
    list_filter = ('student', 'question__survey')
    # Modelde 'answer_text' artık CharField olduğu için direkt kullanabiliriz
    # get_answer_text fonksiyonuna gerek kalmadı (eğer modelde answer_text alanı varsa)
    
    def get_question_text(self, obj):
        return obj.question.text[:50] + "..."
    get_question_text.short_description = 'Soru'

@admin.register(CompletedMaterial)
class CompletedMaterialAdmin(admin.ModelAdmin):
    # list_display: Tablo sütunlarında nelerin görüneceğini belirler
    list_display = ('get_student_full_name', 'get_department', 'get_material_name', 'completed_at')
    
    # Filtreleme seçenekleri
    list_filter = ('completed_at', 'student__department', 'material__content_type')
    
    # Arama çubuğu (Öğrenci adı, e-postası veya materyal başlığına göre)
    search_fields = ('student__first_name', 'student__last_name', 'student__email', 'material__title')

    # 1. Öğrenci Adı ve Soyadı
    def get_student_full_name(self, obj):
        return f"{obj.student.first_name} {obj.student.last_name}"
    get_student_full_name.short_description = 'Öğrenci Adı Soyadı'
    get_student_full_name.admin_order_field = 'student__first_name'

    # 2. Bölüm Bilgisi
    def get_department(self, obj):
        # User modelindeki department alanını çeker (get_department_display seçeneği varsa onu kullanır)
        return obj.student.get_department_display() if hasattr(obj.student, 'get_department_display') else obj.student.department
    get_department.short_description = 'Bölüm'

    # 3. Materyal İsmi
    def get_material_name(self, obj):
        return obj.material.title
    get_material_name.short_description = 'Tamamlanan İçerik'
