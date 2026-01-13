from rest_framework import serializers
from .models import *
from django.db.models import Sum


class MaterialSerializer(serializers.ModelSerializer):
    class Meta:
        model = Material
        fields = ['id', 'content_type', 'embed_url', 'title']

class WeeklyContentSerializer(serializers.ModelSerializer):
    materials = MaterialSerializer(many=True, required=False)
    # Frontend için eklediğimiz dinamik alanlar
    progress = serializers.SerializerMethodField()
    is_completed = serializers.SerializerMethodField()

    class Meta:
        model = WeeklyContent
        fields = ['id', 'week_number', 'title', 'description', 'materials', 'progress', 'is_completed']

    def get_progress(self, obj):
        # İsteği atan öğrenciyi alıyoruz
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            progress_obj = StudentProgress.objects.filter(student=request.user, weekly_content=obj).first()
            if progress_obj:
                return progress_obj.completion_percentage
        return 0

    def get_is_completed(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            progress_obj = StudentProgress.objects.filter(student=request.user, weekly_content=obj).first()
            if progress_obj:
                return progress_obj.is_completed
        return False

    def create(self, validated_data):
        materials_data = validated_data.pop('materials', [])
        content, created = WeeklyContent.objects.update_or_create(
            week_number=validated_data.get('week_number'),
            defaults={
                'title': validated_data.get('title'),
                'description': validated_data.get('description'),
            }
        )
        content.materials.all().delete()
        for material_data in materials_data:
            Material.objects.create(parent_content=content, **material_data)
        return content
    
    


# --- GÜNCELLENEN ANALİZ SERIALIZER'LARI ---

class ActivityTrackSerializer(serializers.Serializer):
    # module_id yerine artık weekly_content_id kullanıyoruz
    weekly_content_id = serializers.IntegerField()
    seconds = serializers.IntegerField(default=30)

class StudentAnalyticsSerializer(serializers.ModelSerializer):
    """Hoca paneli için öğrenci bazlı özet serializer"""
    total_time_spent = serializers.SerializerMethodField()
    overall_progress = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'first_name', 'last_name', 'email', 'total_time_spent', 'overall_progress']

    def get_total_time_spent(self, obj):
        # TimeTracking artık weekly_content üzerinden filtreleniyor
        trackings = TimeTracking.objects.filter(student=obj)
        total_seconds = sum(t.duration_seconds for t in trackings)
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        return f"{hours}h {minutes}m"

    def get_overall_progress(self, obj):
        # StudentProgress artık weekly_content üzerinden filtreleniyor
        progresses = StudentProgress.objects.filter(student=obj)
        if not progresses.exists():
            return 0
        total_pct = sum(p.completion_percentage for p in progresses)
        # Toplam haftalık içerik sayısına bölerek genel ilerlemeyi bulalım
        total_weeks = WeeklyContent.objects.count()
        if total_weeks == 0: return 0
        return round(total_pct / total_weeks, 2)
    
class CompleteMaterialSerializer(serializers.Serializer):
    material_id = serializers.IntegerField()

class StudentProgressSerializer(serializers.ModelSerializer):
    # İsteğe bağlı: Hafta numarasını ve başlığını da görmek için
    week_number = serializers.ReadOnlyField(source='weekly_content.week_number')
    week_title = serializers.ReadOnlyField(source='weekly_content.title')

    class Meta:
        model = StudentProgress
        fields = ['id', 'weekly_content', 'week_number', 'week_title', 'is_completed', 'completion_percentage', 'last_accessed']

User = get_user_model()

class StudentAnalyticsSerializer(serializers.ModelSerializer):
    total_time_spent = serializers.SerializerMethodField()
    overall_progress = serializers.SerializerMethodField()
    weekly_breakdown = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'first_name', 'last_name', 'email', 'total_time_spent', 'overall_progress', 'weekly_breakdown']

    def get_total_time_spent(self, obj):
        total_seconds = TimeTracking.objects.filter(student=obj).aggregate(
            total=Sum('duration_seconds')
        )['total'] or 0
        
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        return f"{hours} saat {minutes} dakika"

    def get_overall_progress(self, obj):
        total_materials = Material.objects.count()
        if total_materials == 0:
            return 0
        completed_count = CompletedMaterial.objects.filter(student=obj).count()
        progress = (completed_count / total_materials) * 100
        return round(progress, 2)

    def get_weekly_breakdown(self, obj):
        weeks = WeeklyContent.objects.all().order_by('week_number')
        breakdown = []
        
        for week in weeks:
            progress_obj = StudentProgress.objects.filter(student=obj, weekly_content=week).first()
            
            # O haftaya ait toplam saniyeyi çek
            total_sec = TimeTracking.objects.filter(
                student=obj, 
                weekly_content=week
            ).aggregate(total=Sum('duration_seconds'))['total'] or 0

            # --- SÜRE FORMATLAMA MANTIĞI ---
            if total_sec == 0:
                duration_str = "0 saniye"
            elif total_sec < 60:
                duration_str = f"{total_sec} saniye"
            elif total_sec < 3600:
                duration_str = f"{total_sec // 60} dakika {total_sec % 60} saniye"
            else:
                hours = total_sec // 3600
                minutes = (total_sec % 3600) // 60
                duration_str = f"{hours} saat {minutes} dakika"

            # --- YENİ: ÖĞRENCİ SORULARINI ÇEKME ---
            # O öğrencinin o haftada AI'ya sorduğu soruların metinlerini liste olarak alıyoruz
            questions = StudentQuestion.objects.filter(
                student=obj, 
                weekly_content=week
            ).values_list('question_text', flat=True)

            breakdown.append({
                "week_number": week.week_number,
                "progress": progress_obj.completion_percentage if progress_obj else 0,
                "duration": duration_str,
                "questions": list(questions) # Frontend'deki interface ile uyumlu isim: 'questions'
            })
            
        return breakdown
    
class AIChatSerializer(serializers.Serializer):
    message = serializers.CharField(required=True, min_length=1)