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
    id = serializers.IntegerField(required=False) 
    quiz = QuizSerializer(required=False, allow_null=True)
    embed_url = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    min_duration_seconds = serializers.IntegerField(required=False, allow_null=True, default=300)

    class Meta:
        model = Material
        fields = ['id', 'content_type', 'embed_url', 'title', 'point_value', 'min_duration_seconds', 'quiz']
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
    options = WeeklyPreTestOptionSerializer(many=True, required=False)
    id = serializers.IntegerField(required=False, allow_null=True)
    
    # IntegerField yerine SerializerMethodField kullanıyoruz.
    # Bu alan 'read_only'dir, bu yüzden POST sırasında Django buna dokunmaz.
    target_week = serializers.SerializerMethodField()

    class Meta:
        model = WeeklyPreTestQuestion
        fields = ['id', 'question_text', 'order', 'target_week', 'options']

    def get_target_week(self, obj):
        """Veritabanından çıkarken objeyi sayıya çevirir."""
        if obj.target_week:
            return obj.target_week.week_number
        return None

    def to_internal_value(self, data):
        """POST sırasında gelen veriyi içeri kabul eder (Süzgeçten geçirir)."""
        # SerializerMethodField read-only olduğu için veriyi elle içeri almalıyız
        internal_value = super().to_internal_value(data)
        if 'target_week' in data:
            internal_value['target_week'] = data['target_week']
        return internal_value
class MaterialListSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False) 
    embed_url = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    min_duration_seconds = serializers.IntegerField(required=False, allow_null=True, default=300)

    class Meta:
        model = Material
        fields = ['id', 'content_type', 'embed_url', 'title', 'point_value', 'min_duration_seconds']
        extra_kwargs = {'id': {'read_only': False, 'required': False}}

class WeeklyContentListSerializer(serializers.ModelSerializer):
    id = serializers.CharField(read_only=True)
    materials = MaterialListSerializer(many=True, required=False)
    flashcards = FlashcardSerializer(many=True, required=False)

    total_score = serializers.SerializerMethodField()
    is_entry_test_passed = serializers.SerializerMethodField()
    is_entry_test_required = serializers.SerializerMethodField()
    is_survey_required = serializers.SerializerMethodField()

    title = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    description = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    intro_title = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    intro_video_url = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    intro_description = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    release_date = serializers.DateTimeField(required=False, allow_null=True)
    due_date = serializers.DateTimeField(required=False, allow_null=True)

    progress = serializers.SerializerMethodField()
    is_completed = serializers.SerializerMethodField()
    is_intro_watched = serializers.SerializerMethodField()
    is_locked = serializers.SerializerMethodField()
    lock_reason = serializers.SerializerMethodField()
    is_temporarily_unlocked = serializers.SerializerMethodField()
    temporary_unlock_until = serializers.SerializerMethodField()
    week_number = serializers.IntegerField(validators=[])

    class Meta:
        model = WeeklyContent
        fields = [
            'id', 'week_number', 'title', 'description', 
            'intro_title', 'intro_video_url', 'intro_description',
            'release_date', 'due_date', 'is_locked', 'lock_reason',
            'is_temporarily_unlocked', 'temporary_unlock_until',
            'is_intro_watched', 'materials', 'flashcards', 
            'progress', 'is_completed',
            'is_entry_test_passed', 'is_entry_test_required',
            'total_score', 'is_survey_required', 'schedules'
        ]

    def get_effective_dates(self, obj):
        request = self.context.get('request')
        target_dept = self.context.get('target_department')

        if not target_dept and request:
            if hasattr(request, 'query_params'):
                target_dept = request.query_params.get('department')
            if not target_dept and hasattr(request, 'user') and request.user and request.user.is_authenticated:
                target_dept = getattr(request.user, 'department', None)

        if target_dept and target_dept != 'all':
            schedules_map = self.context.get('schedules_map')
            if schedules_map is not None:
                dept_schedules = schedules_map.get(obj.id, {})
                sch = dept_schedules.get(target_dept)
                if sch:
                    return (sch.release_date, sch.due_date)
            else:
                from .models import WeeklyContentSchedule
                sch = WeeklyContentSchedule.objects.filter(weekly_content=obj, department=target_dept).first()
                if sch:
                    return (sch.release_date, sch.due_date)

        return (obj.release_date, obj.due_date)

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        rel_date, due_date = self.get_effective_dates(instance)
        ret['release_date'] = rel_date.isoformat() if rel_date else None
        ret['due_date'] = due_date.isoformat() if due_date else None

        schedules_map = self.context.get('schedules_map')
        if schedules_map is not None:
            dept_schedules = schedules_map.get(instance.id, {})
            ret['schedules'] = {
                dept: {
                    "release_date": s.release_date.isoformat() if s.release_date else None,
                    "due_date": s.due_date.isoformat() if s.due_date else None
                }
                for dept, s in dept_schedules.items()
            }
        else:
            ret['schedules'] = {
                s.department: {
                    "release_date": s.release_date.isoformat() if s.release_date else None,
                    "due_date": s.due_date.isoformat() if s.due_date else None
                }
                for s in instance.schedules.all()
            }

        # KONTROL: Eğer haftalık ön test veya anket zorunluysa ve geçici kilit açık değilse materyalleri gizle
        if (ret.get('is_entry_test_required') or ret.get('is_survey_required')) and not ret.get('is_temporarily_unlocked'):
            ret['materials'] = []
            ret['flashcards'] = []

        return ret
    # --- YENİ: ANKET GEREKLİ Mİ KONTROLÜ ---
    # --- 1. ANKET KİLİT MANTIĞI ---
    def get_is_survey_required(self, obj):
        request = self.context.get('request')
        if not request or not request.user or not request.user.is_authenticated:
            return False
        
        if getattr(request.user, 'is_teacher', False) or request.user.is_staff:
            return False

        surveys_map = self.context.get('surveys_map')
        answered_survey_weeks = self.context.get('answered_survey_weeks')

        if surveys_map is not None and answered_survey_weeks is not None:
            if obj.week_number not in surveys_map:
                return False
            return obj.week_number not in answered_survey_weeks

        from .models import Survey, StudentSurveyResponse
        survey = Survey.objects.filter(week_number=obj.week_number).first()
        if not survey:
            return False

        already_answered = StudentSurveyResponse.objects.filter(
            student=request.user, 
            question__survey=survey
        ).exists()

        return not already_answered

    def get_survey_data(self, obj):
        try:
            surveys_map = self.context.get('surveys_map')
            if surveys_map is not None:
                survey = surveys_map.get(obj.week_number)
            else:
                from .models import Survey
                survey = Survey.objects.filter(week_number=obj.week_number).first()

            if not survey:
                return None

            questions_data = []
            all_questions = survey.questions.all()

            for q in all_questions:
                options_list = []
                db_opts = getattr(q, 'options', getattr(q, 'surveyoption_set', None))
                if db_opts:
                    for opt in db_opts.all():
                        options_list.append({
                            "id": opt.id,
                            "option_text": opt.option_text,
                            "value": getattr(opt, 'value', 0)
                        })
                
                questions_data.append({
                    "id": q.id,
                    "text": q.text,
                    "category": q.category,
                    "options": options_list
                })

            return {
                "id": survey.id,
                "title": survey.title,
                "description": survey.description,
                "questions": questions_data
            }

        except Exception as e:
            return None

    def get_is_entry_test_required(self, obj):
        request = self.context.get('request')
        if not request or not request.user or not request.user.is_authenticated:
            return False
            
        if getattr(request.user, 'is_teacher', False) or request.user.is_staff:
            return False

        if obj.week_number <= 1:
            return False

        entry_questions_map = self.context.get('entry_questions_map')
        passed_entry_weeks = self.context.get('passed_entry_weeks')

        if entry_questions_map is not None and passed_entry_weeks is not None:
            has_qs = bool(entry_questions_map.get(obj.id))
            if not has_qs:
                return False
            return obj.id not in passed_entry_weeks

        from .models import WeeklyPreTestQuestion, WeeklyPreTestResult
        has_questions = WeeklyPreTestQuestion.objects.filter(appearing_week=obj).exists()
        if not has_questions:
            return False

        passed = WeeklyPreTestResult.objects.filter(student=request.user, week=obj, is_completed=True).exists()
        return not passed
    
    # --- ÖĞRENCİ İLERLEME VE KİLİT MANTIKLARI (GÜVENLİ) ---

    def get_progress(self, obj):
        request = self.context.get('request')
        if not request or not request.user or not request.user.is_authenticated or getattr(request.user, 'is_teacher', False) or request.user.is_staff:
            return 0.0
        
        user_progress_map = self.context.get('user_progress_map')
        if user_progress_map is not None:
            prog_obj = user_progress_map.get(obj.id)
            return float(prog_obj.completion_percentage) if prog_obj else 0.0

        progress_obj = StudentProgress.objects.filter(student=request.user, weekly_content=obj).first()
        return float(progress_obj.completion_percentage) if progress_obj else 0.0

    def get_is_completed(self, obj):
        request = self.context.get('request')
        if not request or not request.user or not request.user.is_authenticated or getattr(request.user, 'is_teacher', False) or request.user.is_staff:
            return False
        
        user_progress_map = self.context.get('user_progress_map')
        if user_progress_map is not None:
            prog_obj = user_progress_map.get(obj.id)
            return prog_obj.is_completed if prog_obj else False

        progress_obj = StudentProgress.objects.filter(student=request.user, weekly_content=obj).first()
        return progress_obj.is_completed if progress_obj else False

    def get_active_temporary_unlock(self, obj):
        request = self.context.get('request')
        if not request or not request.user or not request.user.is_authenticated:
            return None
        
        temporary_unlocks_map = self.context.get('temporary_unlocks_map')
        if temporary_unlocks_map is not None:
            return temporary_unlocks_map.get(obj.id)
        
        from .models import TemporaryUnlock
        now = timezone.now()
        return TemporaryUnlock.objects.filter(
            student=request.user, 
            week=obj, 
            unlock_until__gt=now
        ).first()

    def get_is_temporarily_unlocked(self, obj):
        tu = self.get_active_temporary_unlock(obj)
        return tu is not None

    def get_temporary_unlock_until(self, obj):
        tu = self.get_active_temporary_unlock(obj)
        return tu.unlock_until.isoformat() if tu else None

    def get_is_locked(self, obj):
        now = timezone.now()
        request = self.context.get('request')

        if request and request.user and (getattr(request.user, 'is_teacher', False) or request.user.is_staff):
            return False

        if self.get_is_temporarily_unlocked(obj):
            return False

        rel_date, due_date = self.get_effective_dates(obj)

        if rel_date and now < rel_date:
            return True

        if due_date and now >= due_date:
            return True

        if obj.week_number > 1:
            weeks_by_num = self.context.get('weeks_by_num')
            if weeks_by_num is not None:
                previous_week = weeks_by_num.get(obj.week_number - 1)
            else:
                previous_week = WeeklyContent.objects.filter(week_number=obj.week_number - 1).first()

            if previous_week:
                prev_rel_date, _ = self.get_effective_dates(previous_week)
                if prev_rel_date and now >= prev_rel_date:
                    user_progress_map = self.context.get('user_progress_map')
                    if user_progress_map is not None:
                        prev_progress = user_progress_map.get(previous_week.id)
                    else:
                        from .models import StudentProgress
                        prev_progress = StudentProgress.objects.filter(
                            student=request.user, 
                            weekly_content=previous_week
                        ).first()
                    
                    if not prev_progress or not prev_progress.is_completed:
                        return True

        return False

    def get_lock_reason(self, obj):
        request = self.context.get('request')
        if not request or not request.user or not request.user.is_authenticated or getattr(request.user, 'is_teacher', False) or request.user.is_staff:
            return None

        if self.get_is_temporarily_unlocked(obj):
            return None

        now = timezone.now()
        rel_date, due_date = self.get_effective_dates(obj)

        if rel_date and now < rel_date:
            return f"Bu içerik {rel_date.strftime('%d.%m.%Y')} tarihinde erişime açılacaktır."

        if due_date and now >= due_date:
            return f"Bu içeriğin erişim süresi {due_date.strftime('%d.%m.%Y')} tarihinde sona ermiştir."

        if obj.week_number > 1:
            weeks_by_num = self.context.get('weeks_by_num')
            if weeks_by_num is not None:
                previous_week = weeks_by_num.get(obj.week_number - 1)
            else:
                previous_week = WeeklyContent.objects.filter(week_number=obj.week_number - 1).first()

            if previous_week:
                user_progress_map = self.context.get('user_progress_map')
                if user_progress_map is not None:
                    prev_progress = user_progress_map.get(previous_week.id)
                else:
                    prev_progress = StudentProgress.objects.filter(student=request.user, weekly_content=previous_week).first()

                if not prev_progress or not prev_progress.is_completed:
                    return f"Bu haftayı açmak için lütfen {obj.week_number - 1}. haftayı %100 tamamlayın."
        return None

    def get_is_intro_watched(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            if getattr(request.user, 'is_teacher', False) or request.user.is_staff: 
                return True
            is_intro_watched = self.context.get('is_intro_watched')
            if is_intro_watched is not None:
                return is_intro_watched
            completion = IntroVideoCompletion.objects.filter(student=request.user).first()
            return completion.is_watched if completion else False
        return False
    
    def get_entry_questions(self, obj):
        try:
            entry_questions_map = self.context.get('entry_questions_map')
            if entry_questions_map is not None:
                qs = entry_questions_map.get(obj.id, [])
            else:
                from .models import WeeklyPreTestQuestion
                qs = WeeklyPreTestQuestion.objects.filter(appearing_week=obj).select_related('target_week').prefetch_related('options')
            
            output = []
            for q in qs:
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
            return []
    
    def get_is_entry_test_passed(self, obj):
        if obj.week_number <= 1:
            return True
            
        request = self.context.get('request')
        if not request or not request.user or not request.user.is_authenticated:
            return True
            
        if getattr(request.user, 'is_teacher', False) or request.user.is_staff:
            return True

        passed_entry_weeks = self.context.get('passed_entry_weeks')
        if passed_entry_weeks is not None:
            return obj.id in passed_entry_weeks
            
        try:
            from .models import WeeklyPreTestResult
            return WeeklyPreTestResult.objects.filter(student=request.user, week=obj, is_completed=True).exists()
        except:
            return True
        
    def get_total_score(self, obj):
        request = self.context.get('request')
        # Kullanıcı giriş yapmışsa direkt onun total_points alanını döndür
        if request and request.user and request.user.is_authenticated:
            # User modelindeki total_points alanını okuyoruz
            return getattr(request.user, 'total_points', 0)
        return 0
        
    

    # --- VERİ SİLİNMESİNİ ENGELLEYEN VE GÜNCELLEMEYİ SAĞLAYAN CREATE ---


    # --- VERİ SİLİNMESİNİ ENGELLEYEN VE GÜNCELLEMEYİ SAĞLAYAN METODLAR ---

    # --- VERİ BÜTÜNLÜĞÜNÜ KORUYAN GÜVENLİ KAYIT SİSTEMİ ---

    def create(self, validated_data):
        return self.save_all_content(validated_data)

    def update(self, instance, validated_data):
        instance = self.save_all_content(validated_data)
        if not instance:
            raise serializers.ValidationError({"error": "Güncelleme sırasında nesne oluşturulamadı."})
        return instance

class WeeklyContentSerializer(WeeklyContentListSerializer):
    materials = MaterialSerializer(many=True, required=False)
    pre_test_questions = PreTestQuestionSerializer(many=True, required=False, allow_null=True)
    entry_questions = WeeklyPreTestQuestionSerializer(many=True, required=False)
    survey_data = serializers.SerializerMethodField()

    survey_questions = serializers.JSONField(write_only=True, required=False, allow_null=True)
    survey_title = serializers.CharField(write_only=True, required=False, allow_blank=True, allow_null=True)
    has_survey = serializers.BooleanField(write_only=True, required=False)

    class Meta(WeeklyContentListSerializer.Meta):
        fields = WeeklyContentListSerializer.Meta.fields + [
            'pre_test_questions', 'entry_questions', 'survey_data',
            'survey_questions', 'survey_title', 'has_survey'
        ]

    def save_all_content(self, validated_data):
        """
        Material, Quiz, Flashcard, EntryTest ve özellikle Survey (Anket)
        modellerini ID bazlı koruyarak günceller.
        """
        from .models import (
            WeeklyContent, Material, Quiz, QuizQuestion, QuizOption, 
            Flashcard, WeeklyPreTestQuestion, WeeklyPreTestOption,
            Survey, SurveyQuestion, SurveyOption
        )
        
        # 1. Verileri Frontend'den gelen Key'lere göre ayıkla
        mats_data = validated_data.pop('materials', None)
        cards_data = validated_data.pop('flashcards', None)
        entry_questions_data = validated_data.pop('entry_questions', None)
        
        survey_questions_list = validated_data.pop('survey_questions', None)
        s_title = validated_data.pop('survey_title', None)
        has_survey_flag = validated_data.pop('has_survey', False)
        
        schedule_dept = validated_data.pop('schedule_department', None) or validated_data.pop('department', None)
        if not schedule_dept and self.initial_data:
            schedule_dept = self.initial_data.get('schedule_department') or self.initial_data.get('department')

        w_num = validated_data.get('week_number')

        try:
            with transaction.atomic():
                # 2. HAFTA ANA BİLGİLERİNİ GÜNCELLE
                content, _ = WeeklyContent.objects.update_or_create(
                    week_number=w_num,
                    defaults={
                        'title': validated_data.get('title', ''),
                        'description': validated_data.get('description', ''),
                        'intro_title': validated_data.get('intro_title', 'Genel Tanıtım'),
                        'intro_video_url': validated_data.get('intro_video_url', ''),
                        'intro_description': validated_data.get('intro_description', ''),
                        'release_date': validated_data.get('release_date', None),
                        'due_date': validated_data.get('due_date', None),
                    }
                )

                rel_date = validated_data.get('release_date')
                due_date = validated_data.get('due_date')

                if schedule_dept:
                    from .models import WeeklyContentSchedule
                    dept_list = ['siyasetbilimi', 'turkdili', 'matematik', 'sb', 'td', 'mt']
                    if schedule_dept == 'all':
                        for d in dept_list:
                            WeeklyContentSchedule.objects.update_or_create(
                                weekly_content=content,
                                department=d,
                                defaults={
                                    'release_date': rel_date,
                                    'due_date': due_date
                                }
                            )
                    else:
                        WeeklyContentSchedule.objects.update_or_create(
                            weekly_content=content,
                            department=schedule_dept,
                            defaults={
                                'release_date': rel_date,
                                'due_date': due_date
                            }
                        )

                # 3. ANKET (SURVEY) KAYIT MANTIĞI
                if has_survey_flag:
                    if not survey_questions_list:
                        survey_questions_list = self.initial_data.get('survey_questions', [])

                    if survey_questions_list:
                        survey_obj, _ = Survey.objects.update_or_create(
                            week_number=w_num,
                            defaults={
                                'title': s_title if (s_title and str(s_title) != str(w_num)) else f"Hafta {w_num} Ölçeği",
                                'description': f"{w_num}. Hafta Bilimsel Ölçeği"
                            }
                        )
                        
                        keep_survey_q_ids = []
                        for s_q in survey_questions_list:
                            s_q_text = s_q.get('text')
                            if not s_q_text:
                                continue
                            
                            s_q_id = s_q.get('id')
                            survey_question_obj, _ = SurveyQuestion.objects.update_or_create(
                                survey=survey_obj,
                                id=s_q_id if (s_q_id and str(s_q_id).isdigit()) else None,
                                defaults={
                                    'text': s_q_text,
                                    'category': s_q.get('category', '')
                                }
                            )
                            keep_survey_q_ids.append(survey_question_obj.id)

                            s_o_list = s_q.get('options', [])
                            keep_survey_o_ids = []
                            for s_o in s_o_list:
                                o_text = s_o.get('option_text')
                                o_val = s_o.get('value')
                                s_o_id = s_o.get('id')

                                if not o_text or str(o_text).strip() == "":
                                    existing_opt = SurveyOption.objects.filter(question=survey_question_obj, value=o_val).first()
                                    if existing_opt:
                                        keep_survey_o_ids.append(existing_opt.id)
                                    continue 

                                survey_option_obj, _ = SurveyOption.objects.update_or_create(
                                    question=survey_question_obj,
                                    value=o_val, 
                                    defaults={
                                        'option_text': str(o_text).strip()
                                    }
                                )
                                keep_survey_o_ids.append(survey_option_obj.id)

                            if keep_survey_o_ids:
                                survey_question_obj.options.exclude(id__in=keep_survey_o_ids).delete()

                        if keep_survey_q_ids:
                            survey_obj.questions.exclude(id__in=keep_survey_q_ids).delete()
                else:
                    Survey.objects.filter(week_number=w_num).delete()

                # 4. MATERYALLER VE QUIZLER
                if mats_data is not None:
                    keep_mat_ids = []
                    for m_item in mats_data:
                        if not m_item.get('title'):
                            continue
                        q_data = m_item.pop('quiz', None)
                        m_id = m_item.get('id')

                        if m_id and str(m_id).isdigit():
                            Material.objects.filter(id=m_id).update(**m_item)
                            mat_obj = Material.objects.get(id=m_id)
                        else:
                            mat_obj = Material.objects.create(parent_content=content, **m_item)
                        
                        keep_mat_ids.append(mat_obj.id)

                        if mat_obj.content_type == 'form' and q_data:
                            quiz_instance, _ = Quiz.objects.update_or_create(
                                material=mat_obj,
                                defaults={'title': q_data.get('title', 'Haftalık Test'), 'description': q_data.get('description', '')}
                            )
                            quiz_qs = q_data.pop('questions', [])
                            keep_quiz_q_ids = []
                            for idx, q_val in enumerate(quiz_qs):
                                if not q_val.get('question_text'):
                                    continue
                                o_list = q_val.pop('options', [])
                                q_id = q_val.get('id')
                                q_obj, _ = QuizQuestion.objects.update_or_create(
                                    quiz=quiz_instance, id=q_id if q_id and str(q_id).isdigit() else None,
                                    defaults={'question_text': q_val.get('question_text'), 'order': idx, 'explanation': q_val.get('explanation', '')}
                                )
                                keep_quiz_q_ids.append(q_obj.id)
                                for o_val in o_list:
                                    if o_val.get('option_text'):
                                        o_id = o_val.pop('id', None)
                                        QuizOption.objects.update_or_create(question=q_obj, id=o_id if o_id and str(o_id).isdigit() else None, defaults=o_val)
                            
                            if keep_quiz_q_ids:
                                quiz_instance.questions.exclude(id__in=keep_quiz_q_ids).delete()

                    if keep_mat_ids:
                        content.materials.exclude(id__in=keep_mat_ids).delete()

                # 5. FLASHCARDLAR
                if cards_data is not None:
                    keep_card_ids = []
                    for idx, c_item in enumerate(cards_data):
                        if not c_item.get('question'):
                            continue
                        c_id = c_item.get('id')
                        card_obj, _ = Flashcard.objects.update_or_create(
                            weekly_content=content,
                            id=c_id if c_id and str(c_id).isdigit() else None,
                            defaults={'question': c_item.get('question'), 'answer': c_item.get('answer'), 'order': idx}
                        )
                        keep_card_ids.append(card_obj.id)
                    if keep_card_ids:
                        content.flashcards.exclude(id__in=keep_card_ids).delete()

                # 6. GİRİŞ TESTİ (ENTRY QUESTIONS)
                if entry_questions_data is not None:
                    keep_entry_ids = []
                    for eq_idx, eq_item in enumerate(entry_questions_data):
                        if not eq_item.get('question_text'):
                            continue
                        eq_id = eq_item.get('id')
                        
                        t_week_num = eq_item.get('target_week')
                        target_week_obj = None
                        if t_week_num:
                            try:
                                target_week_obj = WeeklyContent.objects.get(week_number=int(t_week_num))
                            except (WeeklyContent.DoesNotExist, ValueError):
                                target_week_obj = WeeklyContent.objects.filter(week_number=1).first()

                        eq_opts = eq_item.pop('options', [])
                        entry_q, _ = WeeklyPreTestQuestion.objects.update_or_create(
                            id=eq_id if eq_id and str(eq_id).isdigit() else None,
                            defaults={
                                'appearing_week': content, 
                                'target_week': target_week_obj,
                                'question_text': eq_item.get('question_text'), 
                                'order': eq_idx
                            }
                        )
                        keep_entry_ids.append(entry_q.id)
                        for eo in eq_opts:
                            if eo.get('option_text'):
                                eo_id = eo.pop('id', None)
                                WeeklyPreTestOption.objects.update_or_create(
                                    question=entry_q, id=eo_id if eo_id and str(eo_id).isdigit() else None, defaults=eo
                                )
                    if keep_entry_ids:
                        WeeklyPreTestQuestion.objects.filter(appearing_week=content).exclude(id__in=keep_entry_ids).delete()

                print("--- TÜM KAYITLAR TAMAMLANDI, COMMIT EDİLİYOR ---")
                return content

        except Exception as e:
            print(f"DEBUG: Kayıt Hatası -> {str(e)}")
            import traceback
            traceback.print_exc()
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

class BadgeStatusSerializer(serializers.ModelSerializer):
    is_earned = serializers.SerializerMethodField()
    earned_at = serializers.SerializerMethodField()

    class Meta:
        model = Badge
        fields = ['id', 'name', 'description', 'icon_name', 'color', 'requirement_text', 'is_earned', 'earned_at']

    def get_is_earned(self, obj):
        request = self.context.get('request')
        if request and request.user and request.user.is_authenticated:
            return StudentBadge.objects.filter(student=request.user, badge=obj).exists()
        return False

    def get_earned_at(self, obj):
        request = self.context.get('request')
        if request and request.user and request.user.is_authenticated:
            earned = StudentBadge.objects.filter(student=request.user, badge=obj).first()
            return earned.earned_at if earned else None
        return None

from rest_framework import serializers
from .models import Survey, SurveyQuestion, SurveyOption, StudentSurveyResponse

# 1. Şıklar İçin Serializer (Dinamik metinler için şart)
class SurveyOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = SurveyOption
        fields = ['id', 'option_text', 'value']

# 2. Sorular İçin Serializer (Şıkları da içermeli)
class SurveyQuestionSerializer(serializers.ModelSerializer):
    # 'options' ismi SurveyQuestion modelindeki related_name ile aynı olmalı
    options = SurveyOptionSerializer(many=True, read_only=True)

    class Meta:
        model = SurveyQuestion
        fields = ['id', 'text', 'category', 'options']

# 3. Anket Ana Serializer (Soruları ve Şıkları frontend'e taşır)
class SurveySerializer(serializers.ModelSerializer):
    # 'questions' ismi Survey modelindeki related_name ile aynı olmalı
    questions = SurveyQuestionSerializer(many=True, read_only=True)

    class Meta:
        model = Survey
        fields = ['id', 'title', 'description', 'week_number', 'questions']

    def create(self, validated_data):
        # NOT: Akademisyen panelinde 'save_all_content' kullandığın için 
        # bu metod genellikle manuel kayıtlar için yedektir.
        questions_data = validated_data.pop('questions', [])
        survey = Survey.objects.create(**validated_data)
        for q_data in questions_data:
            SurveyQuestion.objects.create(survey=survey, **q_data)
        return survey

# 4. Öğrenci Cevap Gönderim Serializer
class SurveyResponseSubmitSerializer(serializers.Serializer):
    question_id = serializers.IntegerField()
    answer_value = serializers.IntegerField(min_value=1, max_value=5)

# 5. Akademisyen Paneli Raporlama Serializer (Sayı değil metin döner)
class AcademicSurveyResultSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source='student.get_full_name', read_only=True)
    department = serializers.CharField(source='student.department', read_only=True)
    question_text = serializers.CharField(source='question.text', read_only=True)
    # BURASI KRİTİK: 'answer_value' yerine modelde sakladığımız 'answer_text'i dönüyoruz
    answer = serializers.CharField(source='answer_text', read_only=True)

    class Meta:
        model = StudentSurveyResponse
        fields = ['student_name', 'department', 'question_text', 'answer', 'created_at']

class StudentQuestionSerializer(serializers.ModelSerializer):
    student_name = serializers.SerializerMethodField()
    week_number = serializers.SerializerMethodField()

    class Meta:
        model = StudentQuestion
        fields = ['id', 'question_text', 'ai_response_text', 'created_at', 'weekly_content', 'week_number', 'student_name']

    def get_student_name(self, obj):
        if hasattr(obj.student, 'get_full_name') and callable(obj.student.get_full_name):
            return obj.student.get_full_name() or obj.student.username
        return getattr(obj.student, 'username', '')

    def get_week_number(self, obj):
        return obj.weekly_content.week_number if obj.weekly_content else None