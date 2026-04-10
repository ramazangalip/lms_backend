from rest_framework import serializers
from .models import *
from django.db.models import Sum
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.db import transaction # Bunu dosyanın en üstüne ekle

User = get_user_model()

# --- ALT MODELLER ---

class QuizOptionSerializer(serializers.ModelSerializer):
    # ID'yi writable yapıyoruz
    id = serializers.IntegerField(required=False)
    class Meta:
        model = QuizOption
        fields = ['id', 'option_text', 'is_correct']

class QuizQuestionSerializer(serializers.ModelSerializer):
    # ID'yi writable yapıyoruz
    id = serializers.IntegerField(required=False)
    options = QuizOptionSerializer(many=True)
    class Meta:
        model = QuizQuestion
        fields = ['id', 'question_text', 'order', 'options', 'explanation']

class QuizSerializer(serializers.ModelSerializer):
    # ID'yi writable yapıyoruz
    id = serializers.IntegerField(required=False)
    questions = QuizQuestionSerializer(many=True)
    class Meta:
        model = Quiz
        fields = ['id', 'title', 'description', 'questions']

class MaterialSerializer(serializers.ModelSerializer):
    # DİKKAT: read_only=True KISMINI SİLDİK
    id = serializers.IntegerField(required=False) 
    quiz = QuizSerializer(required=False, allow_null=True)
    embed_url = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    class Meta:
        model = Material
        fields = ['id', 'content_type', 'title', 'embed_url', 'point_value', 'quiz']
    
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
    # ID'yi mutlaka IntegerField ve writable yapıyoruz
    id = serializers.IntegerField(required=False) 

    class Meta:
        model = PreTestOption
        fields = ['id', 'option_text', 'is_correct']

class PreTestQuestionSerializer(serializers.ModelSerializer):
    # ID'yi mutlaka IntegerField ve writable yapıyoruz
    id = serializers.IntegerField(required=False)
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


class WeeklyPreTestOptionSerializer(serializers.ModelSerializer):
    # ID'yi mutlaka IntegerField ve writable yapıyoruz
    id = serializers.IntegerField(required=False)

    class Meta:
        model = WeeklyPreTestOption
        fields = ['id', 'option_text', 'is_correct']

class WeeklyPreTestQuestionSerializer(serializers.ModelSerializer):
    # ID'yi mutlaka IntegerField ve writable yapıyoruz
    id = serializers.IntegerField(required=False)
    options = WeeklyPreTestOptionSerializer(many=True)
    
    # target_week zaten PrimaryKeyRelatedField olduğu için ID olarak gidip gelir, sorun çıkarmaz
    target_week = serializers.PrimaryKeyRelatedField(queryset=WeeklyContent.objects.all())

    class Meta:
        model = WeeklyPreTestQuestion
        fields = ['id', 'question_text', 'order', 'target_week', 'options']
class WeeklyContentSerializer(serializers.ModelSerializer):
    id = serializers.CharField(read_only=True)
    
    # DİKKAT: SerializerMethodField yerine direkt Serializer kullanıyoruz.
    # Bu sayede hoca panelinden gelen 'materials' verisi 'create' metoduna ulaşabilir.
    materials = MaterialSerializer(many=True, required=False)
    flashcards = FlashcardSerializer(many=True, required=False)

    
    is_entry_test_passed = serializers.SerializerMethodField()
    is_entry_test_required = serializers.SerializerMethodField()
    pre_test_questions = PreTestQuestionSerializer(many=True, required=False, allow_null=True)
    entry_questions = WeeklyPreTestQuestionSerializer(many=True, required=False)
    
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
            'progress', 'is_completed', 'pre_test_questions',
            'entry_questions', 'is_entry_test_passed',
            'is_entry_test_required'
        ]

    # BU METODU EKLE
    def get_is_entry_test_required(self, obj):
        request = self.context.get('request')
        if not request or not request.user or not request.user.is_authenticated:
            return False
            
        if getattr(request.user, 'is_teacher', False) or request.user.is_staff:
            return False

        if obj.week_number <= 1:
            return False

        from .models import WeeklyPreTestQuestion, WeeklyPreTestResult
        # 1. Bu haftaya ait giriş sorusu var mı?
        has_questions = WeeklyPreTestQuestion.objects.filter(appearing_week=obj).exists()
        if not has_questions:
            return False

        # 2. Öğrenci bu haftanın testini zaten çözmüş mü?
        passed = WeeklyPreTestResult.objects.filter(student=request.user, week=obj, is_completed=True).exists()
        
        # Eğer soru varsa VE çözülmediyse TRUE döner (Yani test istenir)
        return not passed

    # --- ÖĞRENCİ İLERLEME VE KİLİT MANTIKLARI (GÜVENLİ) ---

    def get_progress(self, obj):
        request = self.context.get('request')
        # Hoca veya Admin ise ilerleme arama (Hata almamak için)
        if not request or not request.user or not request.user.is_authenticated or getattr(request.user, 'is_teacher', False) or request.user.is_staff:
            return 0.0
        
        progress_obj = StudentProgress.objects.filter(student=request.user, weekly_content=obj).first()
        return float(progress_obj.completion_percentage) if progress_obj else 0.0

    def get_is_completed(self, obj):
        request = self.context.get('request')
        if not request or not request.user or not request.user.is_authenticated or getattr(request.user, 'is_teacher', False) or request.user.is_staff:
            return False
        
        progress_obj = StudentProgress.objects.filter(student=request.user, weekly_content=obj).first()
        return progress_obj.is_completed if progress_obj else False

    def get_is_locked(self, obj):
        if obj.week_number == 1:
            return False

        request = self.context.get('request')
        if not request or not request.user or not request.user.is_authenticated:
            return True
        if getattr(request.user, 'is_teacher', False) or request.user.is_staff:
            return False

        # Geçici Kilit Kontrolü
        try:
            from .models import TemporaryUnlock
            if TemporaryUnlock.objects.filter(student=request.user, week=obj, unlock_until__gt=timezone.now()).exists():
                return False
        except:
            pass

        now = timezone.now()
        if obj.release_date and now < obj.release_date:
            return True

        # Önceki hafta kontrolü
        previous_week = WeeklyContent.objects.filter(week_number=obj.week_number - 1).first()
        if previous_week:
            from .models import StudentProgress
            prev_progress = StudentProgress.objects.filter(student=request.user, weekly_content=previous_week).first()
            if not prev_progress or not prev_progress.is_completed:
                return True
        return False

    def get_lock_reason(self, obj):
        request = self.context.get('request')
        if not request or not request.user or not request.user.is_authenticated or getattr(request.user, 'is_teacher', False) or request.user.is_staff:
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
            if getattr(request.user, 'is_teacher', False) or request.user.is_staff: 
                return True
            completion = IntroVideoCompletion.objects.filter(student=request.user).first()
            return completion.is_watched if completion else False
        return False
    
    def get_entry_questions(self, obj):
        try:
            # Soru modelini içeride import et (Circular import koruması)
            from .models import WeeklyPreTestQuestion
            qs = WeeklyPreTestQuestion.objects.filter(appearing_week=obj).select_related('target_week')
            
            output = []
            for q in qs:
                # target_week yoksa veya Hafta 1 ise hata vermemesi için koruma
                t_week_num = 1
                if q.target_week:
                    t_week_num = q.target_week.week_number

                output.append({
                    "id": q.id,
                    "question_text": q.question_text,
                    "target_week": t_week_num,
                    "options": [
                        {
                            "id": o.id, 
                            "option_text": o.option_text, 
                            "is_correct": o.is_correct
                        } for o in q.options.all()
                    ]
                })
            return output
        except Exception as e:
            print(f"DEBUG: Entry Questions Error -> {str(e)}")
            return []
    
    def get_is_entry_test_passed(self, obj):
        if obj.week_number <= 1:
            return True
            
        request = self.context.get('request')
        if not request or not request.user or not request.user.is_authenticated:
            return True # Akademisyen paneli için True dönmek en güvenlisidir
            
        if getattr(request.user, 'is_teacher', False) or request.user.is_staff:
            return True
            
        try:
            from .models import WeeklyPreTestResult
            return WeeklyPreTestResult.objects.filter(student=request.user, week=obj, is_completed=True).exists()
        except:
            return True
        
    

    # --- VERİ SİLİNMESİNİ ENGELLEYEN VE GÜNCELLEMEYİ SAĞLAYAN CREATE ---


    # --- VERİ SİLİNMESİNİ ENGELLEYEN VE GÜNCELLEMEYİ SAĞLAYAN METODLAR ---

    # --- VERİ BÜTÜNLÜĞÜNÜ KORUYAN GÜVENLİ KAYIT SİSTEMİ ---

    def create(self, validated_data):
        return self.save_all_content(validated_data)

    def update(self, instance, validated_data):
        return self.save_all_content(validated_data)

    def save_all_content(self, validated_data):
        """
        Tüm alt modelleri (Material, Quiz, Question, Flashcard, EntryTest) 
        ID bazlı koruyarak günceller.
        """
        mats_data = validated_data.pop('materials', None)
        cards_data = validated_data.pop('flashcards', None)
        pre_test_data = validated_data.pop('pre_test_questions', None)
        entry_questions_data = validated_data.pop('entry_questions', None)
        
        w_num = validated_data.get('week_number')

        try:
            with transaction.atomic():
                # 1. HAFTA ANA BİLGİLERİNİ GÜNCELLE
                content, _ = WeeklyContent.objects.update_or_create(
                    week_number=w_num,
                    defaults={
                        'title': validated_data.get('title'),
                        'description': validated_data.get('description', ''),
                        'intro_title': validated_data.get('intro_title', 'Genel Tanıtım'),
                        'intro_video_url': validated_data.get('intro_video_url', ''),
                        'intro_description': validated_data.get('intro_description', ''),
                        'release_date': validated_data.get('release_date', None),
                    }
                )

                # 2. MATERYALLER (ID Koruma & CASCADE Önleme)
                if mats_data is not None:
                    if len(mats_data) > 0:
                        keep_mat_ids = []
                        for m_item in mats_data:
                            if not m_item.get('title'): continue
                            q_data = m_item.pop('quiz', None)
                            m_id = m_item.get('id')

                            if m_id:
                                # Physical Update: CASCADE silinmesini engeller
                                Material.objects.filter(id=m_id).update(**m_item)
                                mat_obj = Material.objects.get(id=m_id)
                            else:
                                mat_obj = Material.objects.create(parent_content=content, **m_item)
                            
                            keep_mat_ids.append(mat_obj.id)

                            # SINAV (QUIZ) MANTIĞI
                            if mat_obj.content_type == 'form' and q_data:
                                quiz_instance, _ = Quiz.objects.update_or_create(
                                    material=mat_obj,
                                    defaults={'title': q_data.get('title', 'Haftalık Test'), 'description': q_data.get('description', '')}
                                )
                                q_list = q_data.pop('questions', [])
                                keep_q_ids = []
                                for idx, q_val in enumerate(q_list):
                                    if not q_val.get('question_text'): continue
                                    o_list = q_val.pop('options', [])
                                    q_id = q_val.get('id')
                                    question_obj, _ = QuizQuestion.objects.update_or_create(
                                        quiz=quiz_instance, id=q_id if q_id else None,
                                        defaults={'question_text': q_val.get('question_text'), 'order': idx, 'explanation': q_val.get('explanation', '')}
                                    )
                                    keep_q_ids.append(question_obj.id)
                                    for o_val in o_list:
                                        if o_val.get('option_text'):
                                            o_id = o_val.pop('id', None)
                                            QuizOption.objects.update_or_create(question=question_obj, id=o_id if o_id else None, defaults=o_val)
                                if keep_q_ids:
                                    quiz_instance.questions.exclude(id__in=keep_q_ids).delete()

                        if keep_mat_ids:
                            content.materials.exclude(id__in=keep_mat_ids).delete()

                # 3. FLASHCARDLAR (Özel Serializer'ın yoksa burası ID korumalı olmalı)
                if cards_data is not None:
                    if len(cards_data) > 0:
                        keep_card_ids = []
                        for idx, c_item in enumerate(cards_data):
                            if not c_item.get('question'): continue
                            c_id = c_item.get('id')
                            card_obj, _ = Flashcard.objects.update_or_create(
                                weekly_content=content,
                                id=c_id if c_id else None,
                                defaults={'question': c_item.get('question'), 'answer': c_item.get('answer'), 'order': idx}
                            )
                            keep_card_ids.append(card_obj.id)
                        if keep_card_ids:
                            content.flashcards.exclude(id__in=keep_card_ids).delete()

                # 4. ENTRY QUESTIONS (Haftalık Giriş Testi)
                if entry_questions_data is not None:
                    if len(entry_questions_data) > 0:
                        keep_entry_ids = []
                        for eq_idx, eq_item in enumerate(entry_questions_data):
                            if not eq_item.get('question_text'): continue
                            eq_id = eq_item.get('id')
                            t_week = eq_item.get('target_week')
                            eq_opts = eq_item.pop('options', [])
                            entry_q, _ = WeeklyPreTestQuestion.objects.update_or_create(
                                id=eq_id if eq_id else None,
                                defaults={'appearing_week': content, 'target_week': t_week, 'question_text': eq_item.get('question_text'), 'order': eq_idx}
                            )
                            keep_entry_ids.append(entry_q.id)
                            for eo in eq_opts:
                                if eo.get('option_text'):
                                    eo_id = eo.pop('id', None)
                                    WeeklyPreTestOption.objects.update_or_create(question=entry_q, id=eo_id if eo_id else None, defaults=eo)
                        if keep_entry_ids:
                            WeeklyPreTestQuestion.objects.filter(appearing_week=content).exclude(id__in=keep_entry_ids).delete()

                return content

        except Exception as e:
            print(f"DEBUG: Kayıt Hatası -> {str(e)}")
            raise serializers.ValidationError({"error": str(e)})
    


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
                        "is_correct": ans.is_correct,
                        "explanation": ans.question.explanation if ans.question.explanation else "Bu soru için özel bir analiz bulunmamaktadır."
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

# --- HAFTALIK HAZIRLIK TESTİ SERIALIZERLARI ---

class WeeklyPreTestOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = WeeklyPreTestOption
        fields = ['id', 'option_text', 'is_correct']

# serializers.py içindeki bu kısmı şu şekilde değiştir:

class WeeklyPreTestQuestionSerializer(serializers.ModelSerializer):
    options = WeeklyPreTestOptionSerializer(many=True)
    # DİKKAT: SlugRelatedField kullanarak hafta numarasına göre eşleşme sağlıyoruz
    target_week = serializers.SlugRelatedField(
        slug_field='week_number', 
        queryset=WeeklyContent.objects.all()
    )

    class Meta:
        model = WeeklyPreTestQuestion
        fields = ['id', 'question_text', 'order', 'target_week', 'options']
    class Meta:
        model = WeeklyPreTestQuestion
        fields = ['id', 'question_text', 'order', 'target_week_id', 'options']