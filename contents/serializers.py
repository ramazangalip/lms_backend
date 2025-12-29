from rest_framework import serializers
from .models import WeeklyContent, Material

class MaterialSerializer(serializers.ModelSerializer):
    class Meta:
        model = Material
        fields = ['id', 'content_type', 'embed_url', 'title']

class WeeklyContentSerializer(serializers.ModelSerializer):
    materials = MaterialSerializer(many=True, required=False)

    class Meta:
        model = WeeklyContent
        fields = ['id', 'week_number', 'title', 'description', 'materials']

    def create(self, validated_data):
        materials_data = validated_data.pop('materials', [])
        
        # week_number'a göre mevcut içeriği bul veya yeni oluştur
        # Bu satır 400 hatasını (Unique constraint) önler
        content, created = WeeklyContent.objects.update_or_create(
            week_number=validated_data.get('week_number'),
            defaults={
                'title': validated_data.get('title'),
                'description': validated_data.get('description'),
            }
        )
        
        # Mevcut materyalleri temizle ve yenilerini ekle
        content.materials.all().delete()
        for material_data in materials_data:
            Material.objects.create(parent_content=content, **material_data)
            
        return content