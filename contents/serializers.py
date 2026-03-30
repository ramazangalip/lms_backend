from rest_framework import serializers
from .models import *
from django.db.models import Sum
from django.contrib.auth import get_user_model
from django.utils import timezone

User = get_user_model()

# --- ALT MODELLER ---

class QuizOptionSerializer(serializers.ModelSerializer):
    id = serializers.CharField(read_only=True) 
    class Meta:
        model = QuizOption
        fields = ['id', 'option_text', 'is_correct']

class QuizQuestionSerializer(serializers.ModelSerializer):
    id = serializers.CharField(read_only=True)
    options = QuizOptionSerializer(many=True)
    class Meta:
        model = QuizQuestion
        fields = ['id', 'question_text', 'order', 'options']

class QuizSerializer(serializers.ModelSerializer):
    id = serializers.CharField(read_only=True) 
    questions = QuizQuestionSerializer(many=True)
    class Meta:
        model = Quiz
        fields = ['id', 'title', 'description', 'questions']

class MaterialSerializer(serializers.ModelSerializer):
    id = serializers.CharField(read_only=True) 
    quiz = QuizSerializer(required=False, allow_null=True)
    embed_url = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    
    class Meta:
        model = Material
        fields = ['id', 'content_type', 'embed_url', 'title', 'point_value', 'quiz']
        extra_kwargs = {'id': {'read_only': False, 'required': False}}

class FlashcardSerializer(serializers.ModelSerializer):
    class Meta:
        model = Flashcard
        fields = ['id', 'question', 'answer', 'order']
        extra_kwargs = {'id': {'read_only': False, 'required': False}}

# --- ANA SERIALIZER ---

class PreTestOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = PreTestOption
        fields = ['id', 'option_text', 'is_correct']

class PreTestQuestionSerializer(serializers.ModelSerializer):
    options = PreTestOptionSerializer(many=True)

    class Meta:
        model = PreTestQuestion
        fields = ['id', 'question_text', 'order', 'options']

from rest_framework import serializers
from django.utils import timezone
from .models import (
    WeeklyContent, Material, Flashcard, StudentProgress, 
    IntroVideoCompletion, PreTestQuestion, PreTestOption, 
    Quiz, QuizQuestion, QuizOption
)
# Diğer serializer'larının (MaterialSerializer vb.) yukarıda tanımlı olduğunu varsayıyoruz.

class WeeklyContentSerializer(serializers.ModelSerializer):
    id = serializers.CharField(read_only=True)
    materials = MaterialSerializer(many=True, required=False)
    flashcards = FlashcardSerializer(many=True, required=False)
    
    # KRİTİK DEĞİŞİKLİK: MethodField yerine direkt Serializer kullanarak yazma desteği sağlıyoruz.
    # required=False ve allow_null=True ile diğer haftalarda hata almasını önlüyoruz.
    pre_test_questions = PreTestQuestionSerializer(many=True, required=False, allow_null=True)

    progress = serializers.SerializerMethodField()
    is_completed = serializers.SerializerMethodField()
    is_intro_watched = serializers.SerializerMethodField()
    is_locked = serializers.SerializerMethodField()
    lock_reason = serializers.SerializerMethodField()
    week_number = serializers.IntegerField(validators=[])

    class Meta:
        model = WeeklyContent
        fields = [
            'id', 'week_number', 'title', 'description', 
            'intro_title', 'intro_video_url', 'intro_description',
            'release_date', 'is_locked', 'lock_reason',
            'is_intro_watched', 'materials', 'flashcards', 
            'progress', 'is_completed', 'pre_test_questions'
        ]

    # --- ÖĞRENCİ KİLİT VE İLERLEME MANTIKLARI ---

    def get_is_locked(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return True
        if getattr(request.user, 'is_teacher', False) or request.user.is_staff:
            return False

        now = timezone.now()
        if obj.release_date and now < obj.release_date:
            return True

        if obj.week_number > 1:
            previous_week = WeeklyContent.objects.filter(week_number=obj.week_number - 1).first()
            if previous_week:
                prev_progress = StudentProgress.objects.filter(
                    student=request.user, 
                    weekly_content=previous_week
                ).first()
                if not prev_progress or not prev_progress.is_completed:
                    return True
        return False

    def get_lock_reason(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated or getattr(request.user, 'is_teacher', False):
            return None

        now = timezone.now()
        if obj.release_date and now < obj.release_date:
            return f"Bu içerik {obj.release_date.strftime('%d.%m.%Y')} tarihinde erişime açılacaktır."

        if obj.week_number > 1:
            previous_week = WeeklyContent.objects.filter(week_number=obj.week_number - 1).first()
            if previous_week:
                prev_progress = StudentProgress.objects.filter(student=request.user, weekly_content=previous_week).first()
                if not prev_progress or not prev_progress.is_completed:
                    return f"Bu haftayı açmak için lütfen {obj.week_number - 1}. haftayı %100 tamamlayın."
        return None

    def get_is_intro_watched(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            if getattr(request.user, 'is_teacher', False): return True
            completion = IntroVideoCompletion.objects.filter(student=request.user).first()
            return completion.is_watched if completion else False
        return False

    def get_progress(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            progress_obj = StudentProgress.objects.filter(student=request.user, weekly_content=obj).first()
            return float(progress_obj.completion_percentage) if progress_obj else 0.0
        return 0.0

    def get_is_completed(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            progress_obj = StudentProgress.objects.filter(student=request.user, weekly_content=obj).first()
            return progress_obj.is_completed if progress_obj else False
        return False

    # --- KAYIT VE GÜNCELLEME MANTIKLARI (POST/CREATE) ---

    def create(self, validated_data):
        mats_data = validated_data.pop('materials', [])
        cards_data = validated_data.pop('flashcards', [])
        # pre_test_questions artık validated_data içinde doğru bir şekilde gelecek
        pre_test_data = validated_data.pop('pre_test_questions', [])
        w_num = validated_data.get('week_number')

        content, _ = WeeklyContent.objects.update_or_create(
            week_number=w_num,
            defaults={
                'title': validated_data.get('title'),
                'description': validated_data.get('description'),
                'intro_title': validated_data.get('intro_title', 'Genel Tanıtım'),
                'intro_video_url': validated_data.get('intro_video_url', ''),
                'intro_description': validated_data.get('intro_description', ''),
                'release_date': validated_data.get('release_date', None),
            }
        )

        # HAFTA 1: Global Ön Test Sorularını Kaydetme
        if w_num == 1:
            # Öncekileri silip temiz bir kurulum yapıyoruz
            PreTestQuestion.objects.all().delete()
            for q_idx, q_item in enumerate(pre_test_data):
                opts_list = q_item.pop('options', [])
                question_obj = PreTestQuestion.objects.create(
                    question_text=q_item.get('question_text'),
                    order=q_idx
                )
                for o_item in opts_list:
                    PreTestOption.objects.create(question=question_obj, **o_item)
            content.save()

        # MATERYALLER
        keep_mat_ids = []
        for m_item in mats_data:
            q_data = m_item.pop('quiz', None)
            m_id = m_item.get('id')

            if m_id and Material.objects.filter(id=m_id).exists():
                mat_obj = Material.objects.get(id=m_id)
                mat_obj.title = m_item.get('title', mat_obj.title)
                mat_obj.content_type = m_item.get('content_type', mat_obj.content_type)
                mat_obj.embed_url = m_item.get('embed_url', mat_obj.embed_url)
                mat_obj.save()
            else:
                mat_obj = Material.objects.create(parent_content=content, **m_item)
            
            keep_mat_ids.append(mat_obj.id)

            if mat_obj.content_type == 'form' and q_data:
                Quiz.objects.filter(material=mat_obj).delete()
                qs_list = q_data.pop('questions', [])
                quiz_instance = Quiz.objects.create(
                    material=mat_obj, 
                    title=q_data.get('title', ''), 
                    description=q_data.get('description', '')
                )
                for idx, q_val in enumerate(qs_list):
                    opts_list = q_val.pop('options', [])
                    question_instance = QuizQuestion.objects.create(
                        quiz=quiz_instance, 
                        question_text=q_val.get('question_text', ''), 
                        order=idx
                    )
                    for o_val in opts_list:
                        QuizOption.objects.create(question=question_instance, **o_val)

        # FLASHCARDLAR
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

        # Silinenleri temizle
        content.materials.exclude(id__in=keep_mat_ids).delete()
        content.flashcards.exclude(id__in=keep_card_ids).delete()

        return content
    


# --- DİĞER SERIALIZERLAR ---

class IntroCompleteSerializer(serializers.Serializer):
    weekly_content_id = serializers.IntegerField(required=False)



class ActivityTrackSerializer(serializers.Serializer):
    weekly_content_id = serializers.CharField() 
    seconds = serializers.IntegerField(default=30)

class StudentAnalyticsSerializer(serializers.ModelSerializer):
    pre_test_data = serializers.SerializerMethodField() # Yeni alan
    total_time_spent = serializers.SerializerMethodField()
    overall_progress = serializers.SerializerMethodField()
    weekly_breakdown = serializers.SerializerMethodField()
    # Bölümün ismini (display name) çekmek için choice metodunu kullanıyoruz
    department_name = serializers.CharField(source='get_department_display', read_only=True)

    class Meta:
        model = User
        fields = [
            'id', 'first_name', 'last_name', 'email', 
            'department', 'department_name', 'total_points', 
            'total_time_spent', 'overall_progress', 'weekly_breakdown','pre_test_data',
        ]
    def get_pre_test_data(self, obj):
        """Öğrencinin karne modalında görünecek ön test verisi"""
        from .models import PreTestResult # Import döngüsünü engellemek için burada
        res = PreTestResult.objects.filter(student=obj).first()
        if res:
            return {
                "score": res.score,
                "correct": res.correct_answers,
                "wrong": res.wrong_answers,
                "is_completed": res.is_completed,
                "date": res.completed_at.strftime('%d.%m.%Y')
            }
        return None

    def get_total_time_spent(self, obj):
        total_seconds = TimeTracking.objects.filter(student=obj).aggregate(total=Sum('duration_seconds'))['total'] or 0
        return f"{total_seconds // 3600} saat {(total_seconds % 3600) // 60} dakika"

    def get_overall_progress(self, obj):
        # 1. Toplam materyal sayısını al
        total_materials = Material.objects.count()
        if total_materials == 0: 
            return 0
            
        # 2. ÖNEMLİ: Her hafta için sadece AKTİF TURDAKİ tamamlanmaları say
        progresses = StudentProgress.objects.filter(student=obj)
        
        current_completed_count = 0
        for prog in progresses:
            # Sadece o haftanın o anki aktif turunda (Round 1 veya 2) bitenleri say
            count = CompletedMaterial.objects.filter(
                student=obj,
                material__parent_content=prog.weekly_content,
                attempt_round=prog.current_attempt_round
            ).count()
            current_completed_count += count

        # 3. Yüzdeyi hesapla (Asla %100'ü geçemez)
        percentage = (current_completed_count / total_materials) * 100
        return round(min(percentage, 100), 2)

    def get_weekly_breakdown(self, obj):
        weeks = WeeklyContent.objects.all().order_by('week_number')
        breakdown = []
        
        for week in weeks:
            # TUR 1 TOPLAM SÜRE
            total_sec_1 = TimeTracking.objects.filter(
                student=obj, weekly_content=week, attempt_round=1
            ).aggregate(total=Sum('duration_seconds'))['total'] or 0
            
            # TUR 2 TOPLAM SÜRE
            total_sec_2 = TimeTracking.objects.filter(
                student=obj, weekly_content=week, attempt_round=2
            ).aggregate(total=Sum('duration_seconds'))['total'] or 0
            
            # QUIZ SONUÇLARI
            quiz_1 = StudentQuizAttempt.objects.filter(student=obj, quiz__material__parent_content=week, attempt_round=1).first()
            quiz_2 = StudentQuizAttempt.objects.filter(student=obj, quiz__material__parent_content=week, attempt_round=2).first()
            
            progress_obj = StudentProgress.objects.filter(student=obj, weekly_content=week).first()

            # --- MATERYAL BAZLI DETAYLI SÜRE ANALİZİ ---
            material_details = []
            mats = week.materials.all()
            for m in mats:
                m_sec = TimeTracking.objects.filter(
                    student=obj, 
                    material=m
                ).aggregate(total=Sum('duration_seconds'))['total'] or 0
                
                material_details.append({
                    "title": m.title,
                    "content_type": m.content_type,
                    "duration_seconds": m_sec
                })

            # --- YENİ: YAPAY ZEKA SORULARINI ÇEK ---
            ai_questions = StudentQuestion.objects.filter(
                student=obj, 
                weekly_content=week
            ).values_list('question_text', flat=True)

            # --- YENİ: TEST CEVAP ANALİZİNİ ÇEK ---
            # En güncel denemeyi (Tur 1 veya Varsa Tur 2) temel alarak detayları çekiyoruz
            quiz_results = []
            last_attempt = StudentQuizAttempt.objects.filter(
                student=obj, 
                quiz__material__parent_content=week
            ).order_by('-completed_at').first()

            if last_attempt:
                answers = StudentAnswer.objects.filter(attempt=last_attempt)
                for ans in answers:
                    # Bu sorunun doğru şıkkını bul
                    correct_opt = QuizOption.objects.filter(question=ans.question, is_correct=True).first()
                    quiz_results.append({
                        "question_text": ans.question.question_text,
                        "selected_option": ans.selected_option.option_text,
                        "correct_option": correct_opt.option_text if correct_opt else "Belirtilmemiş",
                        "is_correct": ans.is_correct
                    })

            breakdown.append({
                "week_number": week.week_number,
                "progress": progress_obj.completion_percentage if progress_obj else 0,
                "duration": total_sec_1 + total_sec_2, 
                "duration_seconds": total_sec_1 + total_sec_2,
                "material_details": material_details,
                "questions": list(ai_questions),  # AI soruları listesi
                "quiz_results": quiz_results,      # Test cevap detayları
                
                # Tur 1 Detayları
                "duration_1": total_sec_1,
                "score_1": quiz_1.score if quiz_1 else 0,
                "correct_1": quiz_1.correct_answers if quiz_1 else 0,
                "wrong_1": quiz_1.wrong_answers if quiz_1 else 0,

                # Tur 2 Detayları
                "duration_2": total_sec_2,
                "score_2": quiz_2.score if quiz_2 else 0,
                "correct_2": quiz_2.correct_answers if quiz_2 else 0,
                "wrong_2": quiz_2.wrong_answers if quiz_2 else 0,
            })
            
        return breakdown

class CompleteMaterialSerializer(serializers.Serializer):
    material_id = serializers.CharField()

class StudentProgressSerializer(serializers.ModelSerializer):
    weekly_content = serializers.CharField(source='weekly_content.id')
    week_number = serializers.ReadOnlyField(source='weekly_content.week_number')
    week_title = serializers.ReadOnlyField(source='weekly_content.title')
    
    class Meta:
        model = StudentProgress
        fields = ['id', 'weekly_content', 'week_number', 'week_title', 'is_completed', 'completion_percentage', 'last_accessed']

class AIChatSerializer(serializers.Serializer):
    message = serializers.CharField(required=True, min_length=1)

class QuizAIAnalysisSerializer(serializers.Serializer):
    attempt_id = serializers.CharField(read_only=True) 
    ai_feedback = serializers.CharField()
    score = serializers.IntegerField()
    correct_answers = serializers.IntegerField()
    wrong_answers = serializers.IntegerField()



class BulkWeeklyStatSerializer(serializers.Serializer):
    week = serializers.IntegerField()
    progress = serializers.FloatField()
    
    # Tur 1
    duration_seconds = serializers.IntegerField()
    correct = serializers.IntegerField()
    wrong = serializers.IntegerField()
    
    # Tur 2
    duration_seconds_2 = serializers.IntegerField()
    correct_2 = serializers.IntegerField()
    wrong_2 = serializers.IntegerField()
    
    has_quiz = serializers.BooleanField()
    is_round_2_started = serializers.BooleanField()

class BulkAcademicReportSerializer(serializers.Serializer):
    """PDF Raporu için tüm öğrenci verisini paketler"""
    id = serializers.CharField() 
    full_name = serializers.CharField()
    email = serializers.EmailField()
    pre_test_score = serializers.SerializerMethodField()
    # YENİ EKLENEN ALANLAR:
    department = serializers.CharField() 
    total_points = serializers.IntegerField()
    total_time = serializers.IntegerField()
    weekly_breakdown = BulkWeeklyStatSerializer(many=True)

    def get_pre_test_score(self, obj):
        # obj burada bir User nesnesidir
        from .models import PreTestResult
        res = PreTestResult.objects.filter(student=obj).first()
        if res and res.is_completed:
            return f"%{res.score} ({res.correct_answers}D / {res.wrong_answers}Y)"
        return "Girilmedi"

