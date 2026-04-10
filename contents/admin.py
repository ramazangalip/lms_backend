from django.contrib import admin
from .models import *

# --- INLINES ---

class MaterialInline(admin.TabularInline):
    """Haftalık içeriklerin altına video/podcast/test eklemeyi sağlar."""
    model = Material
    extra = 1
    fields = ('content_type', 'title', 'embed_url')

# --- MODELLER ---

@admin.register(WeeklyContent)
class WeeklyContentAdmin(admin.ModelAdmin):
    list_display = ('week_number', 'title', 'has_global_intro')
    list_filter = ('week_number',)
    search_fields = ('title', 'description')
    ordering = ('week_number',)
    inlines = [MaterialInline]

    fieldsets = (
        ('Haftalık Ders Bilgileri', {
            'fields': ('week_number', 'title', 'description')
        }),
        ('Merkezi Tanıtım Videosu (Sadece Hafta 1 İçin Doldurun)', {
            'description': (
                "Öğrencilerin tüm sistemi açmak için izlemesi gereken tek videodur. "
                "Hafta 1'e eklenen video global kilit görevi görür."
            ),
            'fields': ('intro_title', 'intro_video_url'),
            'classes': ('collapse',) # Varsayılan olarak kapalı durur, Hafta 1'de açılabilir
        }),
    )

    def has_global_intro(self, obj):
        return bool(obj.intro_video_url)
    has_global_intro.boolean = True
    has_global_intro.short_description = "Tanıtım Videosu Var"

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
admin.site.register(CompletedMaterial)
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