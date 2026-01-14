from django.contrib import admin
from .models import *

class MaterialInline(admin.TabularInline):
    """
    Haftalık içerik sayfasının içinde materyallerin (video/podcast) 
    satır satır eklenmesini sağlar.
    """
    model = Material
    extra = 1  # Varsayılan olarak 1 tane boş satır gösterir
    fields = ('content_type', 'title', 'embed_url')

@admin.register(WeeklyContent)
class WeeklyContentAdmin(admin.ModelAdmin):
    # Departman ve eski içerik tipi alanları listeden kaldırıldı
    list_display = ('week_number', 'title')
    
    # Filtreleme ve arama departman bağımsız hale getirildi
    list_filter = ('week_number',)
    search_fields = ('title', 'description')
    
    # Hafta numarasına göre sıralama
    ordering = ('week_number',)
    
    # Materyalleri haftalık içeriğin içine gömüyoruz
    inlines = [MaterialInline]

    fieldsets = (
        ('Haftalık Ders Bilgileri', {
            'fields': ('week_number', 'title', 'description')
        }),
    )

    def formfield_for_dbfield(self, db_field, **kwargs):
        field = super().formfield_for_dbfield(db_field, **kwargs)
        if db_field.name == 'description':
            field.widget.attrs['rows'] = 5
            field.widget.attrs['style'] = 'width: 80%;'
        return field

# Material modelini isterseniz tek başına da kaydedebilirsiniz ama Inline kullanım daha pratiktir.
admin.site.register(Material)

# --- YENİ: Materyal Bazlı Tamamlama Takibi ---
@admin.register(CompletedMaterial)
class CompletedMaterialAdmin(admin.ModelAdmin):
    list_display = ('student', 'get_week', 'material', 'completed_at')
    list_filter = ('material__parent_content', 'student', 'completed_at')
    search_fields = ('student__email', 'material__title')
    readonly_fields = ('completed_at',)

    def get_week(self, obj):
        return f"Hafta {obj.material.parent_content.week_number}"
    get_week.short_description = "Hafta"

# --- YENİ: Hassas İlerleme Durumu (0, 33, 66, 100 vb.) ---
@admin.register(StudentProgress)
class StudentProgressAdmin(admin.ModelAdmin):
    list_display = ('student', 'weekly_content', 'progress_bar', 'is_completed', 'last_accessed')
    list_filter = ('weekly_content', 'is_completed')
    search_fields = ('student__email', 'weekly_content__title')

    # Admin panelinde görsel bir yüzde çubuğu gibi görünmesi için
    def progress_bar(self, obj):
        return f"%{obj.completion_percentage}"
    progress_bar.short_description = "İlerleme"

@admin.register(TimeTracking)
class TimeTrackingAdmin(admin.ModelAdmin):
    # Süre takibi kayıtları
    list_display = ('student', 'weekly_content', 'formatted_duration', 'date')
    list_filter = ('date', 'weekly_content', 'student')
    search_fields = ('student__email', 'weekly_content__title')

    # Saniyeyi Admin'de daha okunur yapmak için (Örn: 45 dk)
    def formatted_duration(self, obj):
        minutes = obj.duration_seconds // 60
        if minutes < 60:
            return f"{minutes} dk"
        hours = minutes // 60
        remaining_minutes = minutes % 60
        return f"{hours} sa {remaining_minutes} dk"
    formatted_duration.short_description = "Geçirilen Süre"


# --- YENİ: Öğrenci AI Soruları Takibi ---
@admin.register(StudentQuestion)
class StudentQuestionAdmin(admin.ModelAdmin):
    """
    Öğrencilerin AI Asistanına sorduğu soruların 
    Admin panelinden takip edilmesini sağlar.
    """
    list_display = ('student', 'get_week', 'short_question', 'created_at')
    list_filter = ('weekly_content', 'student', 'created_at')
    search_fields = ('student__first_name', 'student__last_name', 'student__email', 'question_text')
    readonly_fields = ('created_at',)
    ordering = ('-created_at',) # En yeni soruyu en üstte gösterir

    # Hafta bilgisini daha güzel göstermek için
    def get_week(self, obj):
        return f"Hafta {obj.weekly_content.week_number}"
    get_week.short_description = "Hafta"

    # Çok uzun soruların listeyi bozmaması için özet gösterim
    def short_question(self, obj):
        if len(obj.question_text) > 50:
            return f"{obj.question_text[:50]}..."
        return obj.question_text
    short_question.short_description = "Öğrenci Sorusu"

# --- YENİ: Quiz / Test Sonuçları Takibi ---

class StudentAnswerInline(admin.TabularInline):
    """
    Hoca, öğrencinin sınav detayına baktığında 
    hangi soruya ne cevap verdiğini (doğru/yanlış) satır satır görür.
    """
    model = StudentAnswer
    extra = 0
    readonly_fields = ('question', 'selected_option', 'is_correct')
    can_delete = False

@admin.register(StudentQuizAttempt)
class StudentQuizAttemptAdmin(admin.ModelAdmin):
    """
    Öğrencinin bitirdiği testlerin genel listesi.
    """
    list_display = ('student', 'get_week', 'quiz', 'score', 'correct_answers', 'wrong_answers', 'completed_at')
    list_filter = ('quiz__material__parent_content', 'completed_at', 'score')
    search_fields = ('student__first_name', 'student__last_name', 'student__email', 'quiz__title')
    readonly_fields = ('completed_at',)
    
    # Öğrencinin cevaplarını bu sayfanın içinde gösteriyoruz
    inlines = [StudentAnswerInline]

    def get_week(self, obj):
        return f"Hafta {obj.quiz.material.parent_content.week_number}"
    get_week.short_description = "Hafta"

# Opsiyonel: Quiz tanımlarını (sorular ve şıklar) yönetmek için
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