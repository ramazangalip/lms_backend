from rest_framework import serializers
from .models import *
from django.db.models import Sum
from django.contrib.auth import get_user_model

User = get_user_model()

# --- ALT MODELLER ---

from rest_framework import serializers
from .models import *
from django.db.models import Sum
from django.contrib.auth import get_user_model

User = get_user_model()

# --- ALT MODELLER ---

from rest_framework import serializers
from .models import *
from django.db.models import Sum
from django.contrib.auth import get_user_model

User = get_user_model()

# --- ALT MODELLER ---
class QuizOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = QuizOption
        fields = ['id', 'option_text', 'is_correct']
        extra_kwargs = {'id': {'read_only': False, 'required': False}}

class QuizQuestionSerializer(serializers.ModelSerializer):
    options = QuizOptionSerializer(many=True)
    class Meta:
        model = QuizQuestion
        fields = ['id', 'question_text', 'order', 'options']
        extra_kwargs = {'id': {'read_only': False, 'required': False}}

class QuizSerializer(serializers.ModelSerializer):
    questions = QuizQuestionSerializer(many=True)
    class Meta:
        model = Quiz
        fields = ['id', 'title', 'description', 'questions']
        extra_kwargs = {'id': {'read_only': False, 'required': False}}

class MaterialSerializer(serializers.ModelSerializer):
    quiz = QuizSerializer(required=False, allow_null=True)
    embed_url = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    class Meta:
        model = Material
        fields = ['id', 'content_type', 'embed_url', 'title', 'quiz']
        extra_kwargs = {'id': {'read_only': False, 'required': False}}

class FlashcardSerializer(serializers.ModelSerializer):
    class Meta:
        model = Flashcard
        fields = ['id', 'question', 'answer', 'order']
        extra_kwargs = {'id': {'read_only': False, 'required': False}}

# --- ANA SERIALIZER ---
class WeeklyContentSerializer(serializers.ModelSerializer):
    materials = MaterialSerializer(many=True, required=False)
    flashcards = FlashcardSerializer(many=True, required=False)
    progress = serializers.SerializerMethodField()
    is_completed = serializers.SerializerMethodField()
    week_number = serializers.IntegerField(validators=[])

    class Meta:
        model = WeeklyContent
        fields = ['id', 'week_number', 'title', 'description', 'materials', 'flashcards', 'progress', 'is_completed']

    def get_progress(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            progress_obj = StudentProgress.objects.filter(student=request.user, weekly_content=obj).first()
            if progress_obj: return progress_obj.completion_percentage
        return 0

    def get_is_completed(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            progress_obj = StudentProgress.objects.filter(student=request.user, weekly_content=obj).first()
            if progress_obj: return progress_obj.is_completed
        return False

    def create(self, validated_data):
        # 1. Verileri ayıkla
        mats_data = validated_data.pop('materials', [])
        cards_data = validated_data.pop('flashcards', [])
        w_num = validated_data.get('week_number')

        # 2. Haftayı oluştur veya güncelle
        content, _ = WeeklyContent.objects.update_or_create(
            week_number=w_num,
            defaults={
                'title': validated_data.get('title'),
                'description': validated_data.get('description'),
            }
        )

        # 3. Materyalleri İşle
        keep_mat_ids = []
        for m_item in mats_data:
            q_data = m_item.pop('quiz', None)
            m_id = m_item.get('id')

            # Elle atama yaparak hata riskini bitiriyoruz
            if m_id and Material.objects.filter(id=m_id).exists():
                mat_obj = Material.objects.get(id=m_id)
                mat_obj.title = m_item.get('title', mat_obj.title)
                mat_obj.content_type = m_item.get('content_type', mat_obj.content_type)
                mat_obj.embed_url = m_item.get('embed_url', mat_obj.embed_url)
                mat_obj.save()
            else:
                mat_obj = Material.objects.create(parent_content=content, **m_item)
            
            keep_mat_ids.append(mat_obj.id)

            # Quiz İşlemi
            if mat_obj.content_type == 'form' and q_data:
                Quiz.objects.filter(material=mat_obj).delete()
                qs_list = q_data.pop('questions', [])
                quiz_instance = Quiz.objects.create(material=mat_obj, title=q_data.get('title', ''), description=q_data.get('description', ''))
                for idx, q_val in enumerate(qs_list):
                    opts_list = q_val.pop('options', [])
                    question_instance = QuizQuestion.objects.create(quiz=quiz_instance, question_text=q_val.get('question_text', ''), order=idx)
                    for o_val in opts_list:
                        QuizOption.objects.create(question=question_instance, **o_val)

        # 4. Flashcardları İşle (En güvenli yöntem)
        keep_card_ids = []
        for idx, c_item in enumerate(cards_data):
            c_id = c_item.get('id')
            if c_id and Flashcard.objects.filter(id=c_id).exists():
                card_obj = Flashcard.objects.get(id=c_id)
                card_obj.question = c_item.get('question', card_obj.question)
                card_obj.answer = c_item.get('answer', card_obj.answer)
                card_obj.order = idx
                card_obj.save()
            else:
                card_obj = Flashcard.objects.create(
                    weekly_content=content,
                    question=c_item.get('question'),
                    answer=c_item.get('answer'),
                    order=idx
                )
            keep_card_ids.append(card_obj.id)

        # 5. Silinenleri Temizle
        content.materials.exclude(id__in=keep_mat_ids).delete()
        content.flashcards.exclude(id__in=keep_card_ids).delete()

        return content

# --- ANALİZ SERIALIZERLARINI BURAYA EKLE (KODUNUN KALAN KISMI) ---


# --- ANALİZ VE DİĞER SERIALIZERLAR (DEĞİŞMEDİ) ---

class ActivityTrackSerializer(serializers.Serializer):
    weekly_content_id = serializers.IntegerField()
    seconds = serializers.IntegerField(default=30)

class StudentAnalyticsSerializer(serializers.ModelSerializer):
    total_time_spent = serializers.SerializerMethodField()
    overall_progress = serializers.SerializerMethodField()
    weekly_breakdown = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'first_name', 'last_name', 'email', 'total_time_spent', 'overall_progress', 'weekly_breakdown']

    def get_total_time_spent(self, obj):
        total_seconds = TimeTracking.objects.filter(student=obj).aggregate(total=Sum('duration_seconds'))['total'] or 0
        return f"{total_seconds // 3600} saat {(total_seconds % 3600) // 60} dakika"

    def get_overall_progress(self, obj):
        total_materials = Material.objects.count()
        if total_materials == 0: return 0
        completed_count = CompletedMaterial.objects.filter(student=obj).count()
        return round((completed_count / total_materials) * 100, 2)

    def get_weekly_breakdown(self, obj):
            weeks = WeeklyContent.objects.all().order_by('week_number')
            breakdown = []

            for week in weeks:
                # 1. Temel İlerleme ve Süre Verileri
                progress_obj = StudentProgress.objects.filter(student=obj, weekly_content=week).first()
                total_sec = TimeTracking.objects.filter(student=obj, weekly_content=week).aggregate(total=Sum('duration_seconds'))['total'] or 0
                
                # 2. AI Soruları
                questions = StudentQuestion.objects.filter(student=obj, weekly_content=week).values_list('question_text', flat=True)
                
                # 3. Quiz Analizi (Haftalık Bazda)
                quiz_results = []
                
                # attempts sorgusunda related_name'leri doğru prefetch etmek hızı artırır ve hata önler
                attempts = StudentQuizAttempt.objects.filter(
                    student=obj, 
                    quiz__material__parent_content=week
                ).select_related('quiz').prefetch_related('answers__question', 'answers__selected_option')

                for attempt in attempts:
                    for ans in attempt.answers.all():
                        # Soruya ait asıl doğru şıkkı buluyoruz
                        # Not: question.options senin related_name tanımlaman
                        correct_opt = ans.question.options.filter(is_correct=True).first()
                        
                        quiz_results.append({
                            "question_text": ans.question.question_text,
                            "selected_option": ans.selected_option.option_text if ans.selected_option else "Cevapsız",
                            "correct_option": correct_opt.option_text if correct_opt else "Belirlenmemiş",
                            "is_correct": ans.is_correct
                        })

                # 4. Veriyi Paketleme
                breakdown.append({
                    "week_number": week.week_number,
                    "progress": progress_obj.completion_percentage if progress_obj else 0,
                    "duration": f"{total_sec // 60} dk",
                    "questions": list(questions),
                    "quiz_results": quiz_results # Frontend bu anahtarı (key) bekliyor
                })
                
            return breakdown

class CompleteMaterialSerializer(serializers.Serializer):
    material_id = serializers.IntegerField()

class StudentProgressSerializer(serializers.ModelSerializer):
    week_number = serializers.ReadOnlyField(source='weekly_content.week_number')
    week_title = serializers.ReadOnlyField(source='weekly_content.title')
    class Meta:
        model = StudentProgress
        fields = ['id', 'weekly_content', 'week_number', 'week_title', 'is_completed', 'completion_percentage', 'last_accessed']

class AIChatSerializer(serializers.Serializer):
    message = serializers.CharField(required=True, min_length=1)