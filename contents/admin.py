from django.contrib import admin
from .models import WeeklyContent, Material

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