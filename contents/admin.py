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