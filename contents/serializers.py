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
class WeeklyContentSerializer(serializers.ModelSerializer):
    id = serializers.CharField(read_only=True)
    
    # DİKKAT: SerializerMethodField yerine direkt Serializer kullanıyoruz.
    # Bu sayede hoca panelinden gelen 'materials' verisi 'create' metoduna ulaşabilir.
    materials = MaterialSerializer(many=True, required=False)
    flashcards = FlashcardSerializer(many=True, required=False)

    total_score = serializers.SerializerMethodField() # 1. Burası doğru mu?
    is_entry_test_passed = serializers.SerializerMethodField()
    is_entry_test_required = serializers.SerializerMethodField()
    pre_test_questions = PreTestQuestionSerializer(many=True, required=False, allow_null=True)
    entry_questions = WeeklyPreTestQuestionSerializer(many=True, required=False)

    survey_questions = serializers.JSONField(write_only=True, required=False, allow_null=True)
    survey_title = serializers.CharField(write_only=True, required=False, allow_blank=True, allow_null=True)
    has_survey = serializers.BooleanField(write_only=True, required=False)

    # 2. OKUNABİLİR ALANLAR (Öğrenciye veri dönerken hata almamak için)
    # HATA BURADAYDI: Bu iki satırın burada tanımlı olması şart!
    is_survey_required = serializers.SerializerMethodField()
    survey_data = serializers.SerializerMethodField()
    
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
            'is_entry_test_required','total_score',# BURAYA EKLEMEN GEREKENLER:
            'is_survey_required', 'survey_data', # Okuma için
            'survey_questions', 'survey_title', 'has_survey' # Yazma için
        ]
    # --- YENİ: ANKET GEREKLİ Mİ KONTROLÜ ---
    # --- 1. ANKET KİLİT MANTIĞI ---
    def get_is_survey_required(self, obj):
        request = self.context.get('request')
        if not request or not request.user or not request.user.is_authenticated:
            return False
        
        # Akademisyen veya personelse anket engeline takılmasınlar
        if getattr(request.user, 'is_teacher', False) or request.user.is_staff:
            return False

        from .models import Survey, StudentSurveyResponse
        # Bu haftaya atanmış bir anket var mı?
        survey = Survey.objects.filter(week_number=obj.week_number).first()
        if not survey:
            return False

        # Öğrenci bu anketi (en az bir sorusunu) yanıtlamış mı?
        already_answered = StudentSurveyResponse.objects.filter(
            student=request.user, 
            question__survey=survey
        ).exists()

        return not already_answered

    def get_survey_data(self, obj):
        try:
            from .models import Survey
            
            # 1. Debug: Hangi hafta için anket aranıyor?
            target_week = obj.week_number
            print(f"--- ANKET ARAMA BAŞLADI: Hafta {target_week} ---")

            # 2. Sorguyu yap
            survey = Survey.objects.filter(week_number=target_week).first()
            
            if not survey:
                # DB'de bu hafta numarasıyla eşleşen anket yoksa buraya düşer
                print(f"--- SONUÇ: Hafta {target_week} için DB'de anket bulunamadı! ---")
                return None

            print(f"--- SONUÇ: Anket bulundu: {survey.title} (ID: {survey.id}) ---")

            questions_data = []
            # 3. Soruları çek
            all_questions = survey.questions.all()
            print(f"--- SORU SAYISI: {all_questions.count()} ---")

            for q in all_questions:
                # Dinamik şıkları çekmeye çalış
                options_list = []
                
                # Modellerinde related_name='options' tanımlı olduğunu varsayıyoruz
                # Eğer değilse q.surveyoption_set.all() denenecek
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

            print(f"--- VERİ HAZIR: {len(questions_data)} soru paketlendi. ---")
            return {
                "id": survey.id,
                "title": survey.title,
                "description": survey.description,
                "questions": questions_data
            }

        except Exception as e:
            print(f"--- KRİTİK HATA: {str(e)} ---")
            import traceback
            traceback.print_exc()
            return None
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
        now = timezone.now()
        request = self.context.get('request')

        # 1. YETKİ KONTROLÜ
        if request and request.user and (getattr(request.user, 'is_teacher', False) or request.user.is_staff):
            return False

        # 2. HOCA MÜDAHALESİ (MUTLAK TARİH KİLİDİ)
        # Hoca tarihi ileriye aldıysa, bitirilmiş olsa bile o hafta "Erişilemez" olur.
        if obj.release_date and now < obj.release_date:
            return True

        # 3. SIRALI GEÇİŞ BARİKATI (Sadece yayınlanmış haftalar arasında zincir kurar)
        if obj.week_number > 1:
            # Bir önceki haftayı bul
            previous_week = WeeklyContent.objects.filter(week_number=obj.week_number - 1).first()
            
            if previous_week:
                # ÖNEMLİ: Eğer önceki haftanın da tarihi gelmişse (yani şu an aktifse/aktiftiyse)
                # o zaman bitirilme şartı ara.
                if previous_week.release_date and now >= previous_week.release_date:
                    from .models import StudentProgress
                    prev_progress = StudentProgress.objects.filter(
                        student=request.user, 
                        weekly_content=previous_week
                    ).first()
                    
                    if not prev_progress or not prev_progress.is_completed:
                        return True
                
                # NOT: Eğer önceki hafta hoca tarafından ileri bir tarihe kilitlendiyse,
                # yukarıdaki 'if'e girmez ve 3. haftanın önünü kesmez.

        # 4. VARSAYILAN DURUM
        # Tarihi gelmişse ve önünde engel yoksa aç.
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
        # save_all_content metodun zaten 'content' nesnesini dönüyor.
        # Bu nesneyi yakalayıp update metodundan dışarı dönmelisin.
        instance = self.save_all_content(validated_data)
        
        if not instance:
            # Eğer bir hata olduysa ve nesne dönmediyse DRF hata verir, 
            # bu yüzden burada bir geri dönüş garantisi olmalı.
            raise serializers.ValidationError({"error": "Güncelleme sırasında nesne oluşturulamadı."})
            
        return instance  # <--- KRİTİK SATIR BURASI!

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
        
        # ANKET VERİLERİ (Senin gönderdiğin yapıya göre)
       # ANKET VERİLERİ (Senin gönderdiğin yapıya tam uyumlu)
        survey_questions_list = validated_data.pop('survey_questions', None)
        s_title = validated_data.pop('survey_title', None)
        has_survey_flag = validated_data.pop('has_survey', False)
        
        w_num = validated_data.get('week_number')

        try:
            with transaction.atomic():
                # 2. HAFTA ANA BİLGİLERİNİ GÜNCELLE
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

                # 3. ANKET (SURVEY) KAYIT MANTIĞI
                # 'has_survey_flag' artık yukarıda tanımlandığı için hata vermez
                # ... save_all_content içi ...

            # --- 3. ANKET (SURVEY) KAYIT MANTIĞI ---
                # --- 3. ANKET (SURVEY) KAYIT MANTIĞI ---
                # --- 3. ANKET (SURVEY) KAYIT MANTIĞI ---
                if has_survey_flag:
                    survey_questions_list = validated_data.get('survey_questions') or self.initial_data.get('survey_questions')
                    s_title = validated_data.get('survey_title') or self.initial_data.get('survey_title')
                    # Sadece liste doluysa veya null değilse işlem yap
                    if survey_questions_list:
                        survey_obj, _ = Survey.objects.update_or_create(
                            week_number=w_num,
                            defaults={
                                'title': s_title if (s_title and str(s_title) != str(w_num)) else f"Hafta {w_num} Ölçeği",
                                'description': f"{w_num}. Hafta Bilimsel Ölçeği"
                            }
                        )
                        keep_survey_q_ids = []
                        print(f"DEBUG: Hafta {w_num} için gelen soru sayısı: {len(survey_questions_list)}")
                        for s_q in survey_questions_list:
                            print(f"DEBUG: Soru: {s_q.get('text')} - Şık Sayısı: {len(s_q.get('options', []))}")
                            s_q_text = s_q.get('text')
                            if not s_q_text:
                                continue
                            
                            s_q_id = s_q.get('id')
                            # Soruyu Kaydet/Güncelle
                            survey_question_obj, _ = SurveyQuestion.objects.update_or_create(
                                survey=survey_obj,
                                id=s_q_id if (s_q_id and str(s_q_id).isdigit()) else None,
                                defaults={
                                    'text': s_q_text,
                                    'category': s_q.get('category', '')
                                }
                            )
                            current_q_id = survey_question_obj.id
                            keep_survey_q_ids.append(current_q_id)

                            # --- ŞIKLARI (OPTIONS) DİNAMİK OLARAK KAYDET ---
                            s_o_list = s_q.get('options', [])
                            print(f"--- DEBUG: Soru: {s_q_text[:20]} ---")
                            print(f"--- DEBUG: s_o_list Tipi: {type(s_o_list)}")
                            print(f"--- DEBUG: s_o_list İÇERİK: {s_o_list}")
                            keep_survey_o_ids = []
                            
                            for s_o in s_o_list:
                                o_text = s_o.get('option_text')
                                o_val = s_o.get('value')

                                print(f"   -> İşleniyor: {o_text} (Değer: {o_val})")
                                
                                if not o_text:
                                    continue
                                
                                s_o_id = s_o.get('id')
                                survey_option_obj, _ = SurveyOption.objects.update_or_create(
                                    question=survey_question_obj,
                                    id=s_o_id if (s_o_id and str(s_o_id).isdigit()) else None,
                                    defaults={
                                        'option_text': str(o_text).strip(),
                                        'value': int(o_val) if o_val is not None else 0
                                    }
                                )
                                keep_survey_o_ids.append(survey_option_obj.id)
                                print(f"      [TAMAM] DB ID: {survey_option_obj.id} | Metin: {o_text}")
                            
                            # Soruya ait eski/gereksiz şıkları sil
                            survey_question_obj.options.exclude(id__in=keep_survey_o_ids).delete()

                        # Ankete ait ama artık listede olmayan soruları sil
                        survey_obj.questions.exclude(id__in=keep_survey_q_ids).delete()
                
                else:
                    # has_survey_flag False ise anketi veritabanından kaldır
                    Survey.objects.filter(week_number=w_num).delete()
                    print("      [UYARI] Bu sorunun options listesi BOŞ veya HATALI geliyor!")

                # 4. MATERYALLER VE QUIZLER
                if mats_data is not None:
                    keep_mat_ids = []
                    for m_item in mats_data:
                        if not m_item.get('title'): continue
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
                                if not q_val.get('question_text'): continue
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
                        if not c_item.get('question'): continue
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
                        if not eq_item.get('question_text'): continue
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

                return content
            
            print("--- TÜM KAYITLAR TAMAMLANDI, COMMIT EDİLİYOR ---")

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