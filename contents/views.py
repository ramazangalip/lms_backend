from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from .models import *
from .serializers import *
from django.utils import timezone
from datetime import date, timedelta
from rest_framework.permissions import IsAdminUser
from django.db.models import Sum
from django.conf import settings
from django.shortcuts import get_object_or_404
import google as genai
from google.cloud import aiplatform
import requests
from google.auth import default
from google.auth.transport.requests import Request as AuthRequest
import vertexai
from vertexai.generative_models import GenerativeModel
from google.oauth2 import service_account
import os
import json
from rest_framework import status, permissions
from rest_framework.pagination import PageNumberPagination

# --- YARDIMCI FONKSİYONLAR ---

def is_pre_requirements_met(user):
    """Öğrencinin sistem kilitlerini (Tanıtım ve Ön Test) açıp açmadığını kontrol eder."""
    if user.is_staff or getattr(user, 'is_teacher', False):
        return True
    
    video_watched = IntroVideoCompletion.objects.filter(student=user, is_watched=True).exists()
    pre_test_done = PreTestResult.objects.filter(student=user, is_completed=True).exists()
    
    return video_watched and pre_test_done

def init_vertex_ai():
    """Vertex AI bağlantısını merkezi olarak yönetir."""
    PROJECT_ID = "lmsproject-484210"
    LOCATION = "us-central1"
    creds_json = os.environ.get("GOOGLE_CREDENTIALS_JSON")
    
    if creds_json:
        creds_dict = json.loads(creds_json)
        credentials = service_account.Credentials.from_service_account_info(creds_dict)
        vertexai.init(project=PROJECT_ID, location=LOCATION, credentials=credentials)
    else:
        vertexai.init(project=PROJECT_ID, location=LOCATION)
    return PROJECT_ID, LOCATION

# --- ANA İÇERİK VIEW ---

from django.db import transaction
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
import traceback

class WeeklyContentView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        week_number = request.query_params.get('week_number')
        user = request.user
        
        # 1. TEK HAFTA DETAYI (Akademisyen düzenleme yaparken veya öğrenci haftaya girdiğinde)
        if week_number:
            content = WeeklyContent.objects.filter(week_number=week_number).first()
            if not content:
                return Response({"detail": "Bu hafta bulunamadı."}, status=status.HTTP_404_NOT_FOUND)

            # Context göndermek hayati önem taşıyor!
            serializer = WeeklyContentSerializer(content, context={'request': request})
            data = serializer.data

            # Hafta 1 özel durumunu manuel eklemeye devam edebiliriz
            if str(week_number) == "1":
                from .models import PreTestQuestion
                from .serializers import PreTestQuestionSerializer
                questions = PreTestQuestion.objects.all().prefetch_related('options')
                data['pre_test_questions'] = PreTestQuestionSerializer(questions, many=True).data if questions.exists() else []

            return Response(data, status=status.HTTP_200_OK)

        # 2. LİSTE GÖRÜNÜMÜ (Hem Akademisyen Paneli hem Öğrenci Dashboard burayı kullanır)
        # Prefetch_related kullanarak SQL sorgu sayısını azaltıyoruz
        contents = WeeklyContent.objects.all().order_by('week_number').prefetch_related(
            'materials', 'flashcards', 'materials__quiz', 'materials__quiz__questions'
        )
        
        # many=True durumunda her bir içerik için Serializer içindeki metodlar çalışacak
        serializer = WeeklyContentSerializer(contents, many=True, context={'request': request})
        
        # DEBUG: Akademisyen paneli için veri gidiyor mu terminalden bak
        if getattr(user, 'is_teacher', False) or user.is_staff:
            print(f"DEBUG: Akademisyen {user.username} için {len(serializer.data)} hafta paketlendi.")

        return Response(serializer.data, status=status.HTTP_200_OK)

    # post metodu aynı kalacak...

    def post(self, request):
        """Akademisyen Paneli: İçerik Güncelleme, Soru Ekleme ve Anket Kaydı"""
        # 1. Yetki Kontrolü
        if not getattr(request.user, 'is_teacher', False) and not request.user.is_staff:
            return Response({"error": "Yetkiniz bulunmamaktadır."}, status=status.HTTP_403_FORBIDDEN)

        # 2. Hafta Numarası Kontrolü
        week_number = request.data.get('week_number')
        if not week_number:
            return Response({"error": "Hafta numarası belirtilmelidir."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                # 3. Mevcut İçeriği Getir (Varsa)
                content_instance = WeeklyContent.objects.filter(week_number=week_number).first()
                
                # 4. Serializer'ı Çalıştır
                # NOT: survey_questions, survey_title ve has_survey verileri 
                # request.data içinde olduğu için Serializer bunları otomatik işleyecek.
                serializer = WeeklyContentSerializer(
                    content_instance, 
                    data=request.data, 
                    context={'request': request}, 
                    partial=True
                )

                if serializer.is_valid():
                    # Serializer içindeki update() ve dolayısıyla save_all_content() tetiklenir.
                    # Senin yazdığın o detaylı şık koruma mantığı burada devreye girer.
                    serializer.save()
                    
                    return Response(serializer.data, status=status.HTTP_201_CREATED)
                
                # Geçersiz veri durumunda hata logla
                print(f"Validation Errors: {serializer.errors}")
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            print("--- HAFTA/ANKET KAYDETME HATASI ---")
            import traceback
            traceback.print_exc()
            return Response(
                {"error": f"Sunucu hatası: {str(e)}"}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class CompleteIntroVideoView(APIView):
    """Öğrenci genel tanıtım videosunu bitirdiğinde tüm haftaların kilidi açılır."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        # OneToOneField sayesinde her öğrenci için tek bir "izledi" kaydı tutulur
        completion, created = IntroVideoCompletion.objects.get_or_create(student=request.user)
        completion.is_watched = True
        completion.save()
        
        return Response({
            "status": "success", 
            "message": "Genel tanıtım tamamlandı. Sistem kilidi açıldı."
        })
class ContentDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, week_number):
        user = request.user
        
        # 1. TEMEL SİSTEM KİLİDİ (Tanıtım Videosu ve Genel Ön Test - 1. Hafta Öncesi)
        # Not: is_pre_requirements_met fonksiyonunun tanımlı olduğunu varsayıyoruz.
        if int(week_number) > 1 and not is_pre_requirements_met(user):
             return Response(
                {"error": "Haftalık içeriklere erişebilmek için Tanıtım Videosunu izlemeli ve Ön Testi tamamlamalısınız."}, 
                status=status.HTTP_403_FORBIDDEN
            )

        content = WeeklyContent.objects.filter(week_number=week_number).first()
        if not content:
            return Response({"error": f"{week_number}. hafta içeriği bulunamadı."}, status=status.HTTP_404_NOT_FOUND)

        # Serializer'ı hazırla
        serializer = WeeklyContentSerializer(content, context={'request': request})
        data = serializer.data

        # --- YENİ SİSTEM: HAFTALIK GİRİŞ TESTİ VE ANKET ZORUNLULUĞU ---
        is_teacher = getattr(user, 'is_teacher', False) or user.is_staff
        
        if not is_teacher:
            # 1. haftadan sonraki tüm haftalar için kilit kontrolü
            if int(week_number) > 1:
                
                # A) Haftalık Ön Değerlendirme Testi Kontrolü
                pre_test_passed = WeeklyPreTestResult.objects.filter(
                    student=user, 
                    week=content, 
                    is_completed=True
                ).exists()
                
                # B) Haftalık Anket Ölçeği Kontrolü
                # Bu haftaya ait Survey'in en az bir sorusuna cevap verilmiş mi?
                survey_completed = StudentSurveyResponse.objects.filter(
                    student=user, 
                    question__survey__week_number=week_number
                ).exists()
                
                # KİLİT MEKANİZMASI: İkisinden biri eksikse materyalleri gizle
                if not pre_test_passed or not survey_completed:
                    # Güvenlik için veriyi temizle
                    data['materials'] = []
                    data['flashcards'] = []
                    
                    # Frontend tarafı için durum bayrakları (Flags)
                    data['is_locked'] = True
                    data['is_entry_test_required'] = not pre_test_passed
                    data['is_survey_required'] = not survey_completed
                    
                    # Kullanıcıya detaylı mesaj döndür
                    if not pre_test_passed and not survey_completed:
                        data['lock_message'] = "Bu haftanın materyallerine erişmek için hem Ön Değerlendirme Testini hem de Anketi tamamlamalısınız."
                    elif not pre_test_passed:
                        data['lock_message'] = "Lütfen önce bu haftanın Ön Değerlendirme Testini tamamlayın."
                    else:
                        data['lock_message'] = "Lütfen önce bu haftanın Anketini tamamlayın."
                else:
                    # İki şart da sağlanmışsa kilitleri aç
                    data['is_locked'] = False
                    data['is_entry_test_required'] = False
                    data['is_survey_required'] = False
            else:
                # 1. Hafta için (Tanıtım haftası vb.) kilitleri varsayılan olarak açıyoruz
                data['is_locked'] = False
                data['is_entry_test_required'] = False
                data['is_survey_required'] = False

        return Response(data, status=status.HTTP_200_OK)

# --- TAKİP VE İLERLEME SİSTEMİ ---

class TrackActivityView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ActivityTrackSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        weekly_content_id = serializer.validated_data.get('weekly_content_id')
        seconds = serializer.validated_data.get('seconds', 30)
        # YENİ: Frontend'den gelen material_id'yi alıyoruz
        material_id = request.data.get('material_id') 

        try:
            weekly_content = WeeklyContent.objects.get(id=weekly_content_id)
            progress, _ = StudentProgress.objects.get_or_create(
                student=request.user, 
                weekly_content=weekly_content
            )
            current_round = progress.current_attempt_round

            # KRİTİK DEĞİŞİKLİK: 
            # get_or_create içine 'material' alanını ekliyoruz.
            # Böylece her materyal için ayrı bir satır oluşur.
            tracking, _ = TimeTracking.objects.get_or_create(
                student=request.user,
                weekly_content=weekly_content,
                material_id=material_id, # Materyal bazlı satır
                attempt_round=current_round,
                date=date.today()
            )
            tracking.duration_seconds += seconds
            tracking.save()
            
            return Response({
                "status": "success", 
                "material": tracking.material.title if tracking.material else "Genel",
                "total_seconds_in_material": tracking.duration_seconds
            }, status=status.HTTP_200_OK)
            
        except WeeklyContent.DoesNotExist:
            return Response({"error": "İçerik bulunamadı."}, status=status.HTTP_404_NOT_FOUND)

class CompleteMaterialView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        print("\n" + "="*60)
        print(f"DEBUG: [CompleteMaterialView] POST BAŞLADI")
        
        serializer = CompleteMaterialSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        material_id_raw = serializer.validated_data.get('material_id')

        # 1. Materyal var mı kontrolü
        try:
            material = Material.objects.get(id=material_id_raw)
        except Material.DoesNotExist:
            return Response({"error": "Materyal bulunamadı"}, status=status.HTTP_404_NOT_FOUND)

        weekly_content = material.parent_content

        # 2. Öğrencinin aktif deneme turunu (Round) tespit et
        progress, _ = StudentProgress.objects.get_or_create(
            student=request.user, 
            weekly_content=weekly_content
        )
        current_round = progress.current_attempt_round
        print(f"DEBUG: Öğrenci {weekly_content.week_number}. Hafta için {current_round}. turda.")

        # 3. Materyali BU TUR için tamamlanmış olarak kaydet
        completed_record, created = CompletedMaterial.objects.get_or_create(
            student=request.user, 
            material=material,
            attempt_round=current_round # Tur bilgisi ile kaydediyoruz
        )

        new_points = 0
        # Puan Mantığı: Sadece 1. turda materyal bitirince puan verilir
        if created and current_round == 1:
            # --- GÜNCELLEME BURADA ---
            # Eğer puan 10 ise veya 0 ise (girilmemişse) 1 puan ver, değilse tanımlı puanı ver.
            actual_point = material.point_value
            if actual_point == 10 or actual_point == 0:
                new_points = 1
            else:
                new_points = actual_point
            # -------------------------

            request.user.total_points += new_points
            request.user.save()
            print(f"DEBUG: 1. Tur tamamlaması. {new_points} puan kazandı.")
        else:
            print(f"DEBUG: {current_round}. tur kaydı zaten var veya 2. tur olduğu için puan verilmedi.")

        # 4. İlerleme Hesaplama (Sadece aktif olan turdaki materyallere göre)
        total_mats = weekly_content.materials.count()
        done_mats_in_current_round = CompletedMaterial.objects.filter(
            student=request.user, 
            material__parent_content=weekly_content,
            attempt_round=current_round # Filtreleme sadece mevcut tura göre yapılır
        ).count()

        percentage = (done_mats_in_current_round / total_mats) * 100 if total_mats > 0 else 0
        
        progress.completion_percentage = round(percentage, 2)
        # Eğer yüzde 100 ise o tur için tamamlandı olarak işaretle
        progress.is_completed = (percentage >= 100)
        progress.save()

        print(f"DEBUG: {current_round}. Tur İlerlemesi: %{progress.completion_percentage}")
        print("="*60 + "\n")

        return Response({
            "status": "success", 
            "round": current_round,
            "current_percentage": progress.completion_percentage,
            "material_id": str(material.id),
            "new_points_earned": new_points,
            "total_points": request.user.total_points
        }, status=status.HTTP_200_OK)
class CompletedMaterialIdsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from django.db.models import Q
        
        # 1. Öğrencinin haftalık tur bilgilerini al
        student_progresses = StudentProgress.objects.filter(student=request.user)
        
        # 2. Dinamik bir filtre oluştur (Hafta X'te Tur Y verilerini getir)
        query = Q()
        for prog in student_progresses:
            query |= Q(
                material__parent_content=prog.weekly_content, 
                attempt_round=prog.current_attempt_round
            )
        
        if not query:
            return Response([])

        # 3. Sadece aktif tura ait olan tamamlanmış materyal ID'lerini çek
        completed_ids = CompletedMaterial.objects.filter(
            query,
            student=request.user
        ).values_list('material_id', flat=True)
        
        return Response([str(m_id) for m_id in completed_ids])

class StudentProgressListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        progresses = StudentProgress.objects.filter(student=request.user).order_by('weekly_content__week_number')
        serializer = StudentProgressSerializer(progresses, many=True)
        return Response(serializer.data)

# --- HOCA PANELİ VE ANALİTİKLER ---

class TeacherAnalyticsView(APIView):
    permission_classes = [IsAdminUser] 

    def get(self, request, student_id=None):
        if student_id:
            try:
                student = User.objects.get(id=student_id)
                one_week_ago = timezone.now().date() - timedelta(days=7)
                time_stats = TimeTracking.objects.filter(student=student, date__gte=one_week_ago).values('weekly_content__title', 'weekly_content__week_number').annotate(total_seconds=Sum('duration_seconds')).order_by('weekly_content__week_number')
                progress_stats = StudentProgress.objects.filter(student=student).values('weekly_content__title', 'completion_percentage', 'is_completed')
                return Response({"student_info": f"{student.first_name} {student.last_name}", "weekly_analysis": list(time_stats), "progress_analysis": list(progress_stats)})
            except User.DoesNotExist: return Response({"error": "Öğrenci bulunamadı."}, status=404)
        else:
            students = User.objects.filter(is_staff=False)
            serializer = StudentAnalyticsSerializer(students, many=True)
            return Response(serializer.data)

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.db.models import Sum
from django.contrib.auth import get_user_model
from .models import *

User = get_user_model()

class StudentAnalyticsPagination(PageNumberPagination):
    page_size = 10  # Her sayfada 10 öğrenci gösterilir
    page_size_query_param = 'page_size'
    max_page_size = 50

class StudentAnalyticsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # 1. Kullanıcının kim olduğunu anla
        is_teacher = getattr(request.user, 'is_teacher', False) or request.user.is_staff
        department_param = request.query_params.get('department')

        # 2. FİLTRELEME MANTIĞI (Bölüm bazlı filtreleme korunuyor)
        if is_teacher:
            if not department_param or department_param == 'all':
                return Response(
                    {"error": "Analiz verileri için bölüm seçimi zorunludur."}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            queryset = User.objects.filter(
                department=department_param, 
                is_staff=False,
                is_teacher=False 
            ).order_by('first_name')
        else:
            queryset = User.objects.filter(id=request.user.id)

        # --- SAYFALANDIRMA BAŞLANGICI ---
        paginator = StudentAnalyticsPagination()
        paginated_students = paginator.paginate_queryset(queryset, request)
        
        if not paginated_students:
            return Response([], status=status.HTTP_200_OK)

        # Sadece bu sayfadaki öğrencilerin ID'lerini alarak toplu veri çekiyoruz (RAM dostu)
        student_ids = [s.id for s in paginated_students]
        # --- SAYFALANDIRMA BİTİŞİ ---

        # 3. TOPLU VERİ ÇEKME (Sadece sayfadaki 10 öğrenci için optimize edildi)
        all_time_tracking = list(TimeTracking.objects.filter(student_id__in=student_ids).select_related('weekly_content'))
        all_attempts = list(StudentQuizAttempt.objects.filter(student_id__in=student_ids).select_related('quiz__material__parent_content'))
        all_answers = list(StudentAnswer.objects.filter(
            attempt__student_id__in=student_ids
        ).select_related('question', 'selected_option', 'attempt'))
        all_progress = list(StudentProgress.objects.filter(student_id__in=student_ids).select_related('weekly_content'))
        all_pre_tests = {pt.student_id: pt for pt in PreTestResult.objects.filter(student_id__in=student_ids)}
        all_questions = list(StudentQuestion.objects.filter(student_id__in=student_ids).select_related('weekly_content'))
        all_correct_options = {
            opt.question_id: opt.option_text 
            for opt in QuizOption.objects.filter(is_correct=True)
        }

        # 4. VERİLERİ HARİTALAMA
        final_data = []
        for student in paginated_students:
            s_times = [t for t in all_time_tracking if t.student_id == student.id]
            s_attempts = [a for a in all_attempts if a.student_id == student.id]
            s_progress = [p for p in all_progress if p.student_id == student.id]
            s_questions = [q for q in all_questions if q.student_id == student.id]
            s_pre_test = all_pre_tests.get(student.id)

            weekly_stats = []
            # 14 haftalık veriyi işleme
            for i in range(1, 15):
                dur_1 = sum(t.duration_seconds for t in s_times if t.weekly_content and t.weekly_content.week_number == i and t.attempt_round == 1)
                dur_2 = sum(t.duration_seconds for t in s_times if t.weekly_content and t.weekly_content.week_number == i and t.attempt_round == 2)
                
                att_1 = next((a for a in s_attempts if a.quiz.material.parent_content.week_number == i and a.attempt_round == 1), None)
                att_2 = next((a for a in s_attempts if a.quiz.material.parent_content.week_number == i and a.attempt_round == 2), None)
                
                prog_rec = next((p for p in s_progress if p.weekly_content and p.weekly_content.week_number == i), None)
                week_qs = [q.question_text for q in s_questions if q.weekly_content and q.weekly_content.week_number == i]

                quiz_results = []
                last_attempt = att_2 if att_2 else att_1
                
                if last_attempt:
                    s_answers = [ans for ans in all_answers if ans.attempt_id == last_attempt.id]
                    for ans in s_answers:
                        quiz_results.append({
                            "question_text": ans.question.question_text,
                            "selected_option": ans.selected_option.option_text,
                            "correct_option": all_correct_options.get(ans.question_id, "Belirtilmemiş"),
                            "is_correct": ans.is_correct,
                            "explanation": ans.question.explanation if ans.question.explanation else "Bu soru için analiz hazırlanmamış."
                        })

                weekly_stats.append({
                    "week_number": i,
                    "progress": float(prog_rec.completion_percentage) if prog_rec else 0,
                    "duration": dur_1 + dur_2,
                    "duration_seconds": dur_1,
                    "duration_2": dur_2,
                    "score_1": att_1.score if att_1 else 0,
                    "score_2": att_2.score if att_2 else 0,
                    "correct_1": att_1.correct_answers if att_1 else 0,
                    "wrong_1": att_1.wrong_answers if att_1 else 0,
                    "correct_2": att_2.correct_answers if att_2 else 0,
                    "wrong_2": att_2.wrong_answers if att_2 else 0,
                    "questions": week_qs,
                    "quiz_results": quiz_results 
                })

            overall_progress = sum(w['progress'] for w in weekly_stats) / 14 if weekly_stats else 0
            total_sec = sum(t.duration_seconds for t in s_times)
            total_time_str = f"{total_sec // 60} dk" if total_sec < 3600 else f"{total_sec // 3600} sa {(total_sec % 3600) // 60} dk"

            final_data.append({
                "id": student.id,
                "first_name": student.first_name,
                "last_name": student.last_name,
                "email": student.email,
                "department": student.department,
                "total_points": getattr(student, 'total_points', 0),
                "total_time_spent": total_time_str,
                "overall_progress": round(overall_progress, 1),
                "weekly_breakdown": weekly_stats,
                "pre_test_data": {
                    "score": s_pre_test.score,
                    "correct": s_pre_test.correct_answers,
                    "wrong": s_pre_test.wrong_answers,
                    "date": s_pre_test.completed_at.strftime('%d.%m.%Y')
                } if s_pre_test else None
            })

        # --- 5. SAYFALANDIRILMIŞ YANIT DÖNÜŞÜ ---
        return paginator.get_paginated_response(final_data)

# --- YAPAY ZEKA SOHBET ---

class AIChatView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user_message = request.data.get("message")
        week_id = request.data.get("weekly_content_id")
        if not user_message: return Response({"error": "Mesaj boş olamaz."}, status=400)

        try:
            p_id, loc = init_vertex_ai()
            model = GenerativeModel(f"projects/{p_id}/locations/{loc}/endpoints/981343814604029952")
            response = model.generate_content(user_message)
            ai_response_text = response.text

            if week_id:
                try:
                    weekly_content = WeeklyContent.objects.get(id=week_id)
                    StudentQuestion.objects.create(student=request.user, weekly_content=weekly_content, question_text=user_message)
                except: pass
            return Response({"response": ai_response_text}, status=200)
        except Exception as e: return Response({"response": "Asistan şu an yanıt veremiyor."}, status=500)

# --- QUIZ (SINAV) SİSTEMİ ---

class QuizSubmitView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, quiz_id):
        # 1. Temel nesneleri al
        quiz = get_object_or_404(Quiz, id=str(quiz_id))
        weekly_content = quiz.material.parent_content
        
        # 2. Mevcut tur (round) bilgisini al
        progress, _ = StudentProgress.objects.get_or_create(
            student=request.user, 
            weekly_content=weekly_content
        )
        current_round = progress.current_attempt_round

        # 3. Aynı tur içinde mükerrer sınav çözümünü engelle
        if StudentQuizAttempt.objects.filter(
            student=request.user, 
            quiz=quiz, 
            attempt_round=current_round
        ).exists():
            return Response(
                {"error": f"Bu haftanın testini {current_round}. tur için zaten çözdünüz."}, 
                status=status.HTTP_403_FORBIDDEN
            )

        answers_data = request.data.get('answers', [])
        correct_count = 0
        
        # 4. Sınav denemesini (Attempt) aktif tura göre oluştur
        attempt = StudentQuizAttempt.objects.create(
            student=request.user, 
            quiz=quiz, 
            score=0, 
            correct_answers=0, 
            wrong_answers=0,
            attempt_round=current_round # Hangi turda olduğu kaydediliyor
        )

        # 5. Cevapları işle
        for ans in answers_data:
            q_id = str(ans.get('question_id'))
            o_id = str(ans.get('option_id'))
            
            try:
                question = get_object_or_404(QuizQuestion, id=q_id, quiz=quiz)
                option = get_object_or_404(QuizOption, id=o_id, question=question)
                
                if option.is_correct:
                    correct_count += 1
                
                StudentAnswer.objects.create(
                    attempt=attempt, 
                    question=question, 
                    selected_option=option, 
                    is_correct=option.is_correct
                )
            except Exception as e:
                print(f"DEBUG: Quiz Soru/Cevap Hatası -> {str(e)}")

        # 6. Skor hesapla ve kaydet
        total_questions = quiz.questions.count()
        attempt.score = round((correct_count / total_questions) * 100) if total_questions > 0 else 0
        attempt.correct_answers = correct_count
        attempt.wrong_answers = total_questions - correct_count
        attempt.save()

        # 7. Sınav materyalini BU TUR için tamamlandı işaretle
        CompletedMaterial.objects.get_or_create(
            student=request.user, 
            material=quiz.material,
            attempt_round=current_round
        )
        
        # 8. İlerleme durumunu güncelle (Round yükseltme BURADA YAPILMIYOR)
        total_mats = weekly_content.materials.count()
        done_mats = CompletedMaterial.objects.filter(
            student=request.user, 
            material__parent_content=weekly_content,
            attempt_round=current_round
        ).count()
        
        perc = (done_mats / total_mats) * 100 if total_mats > 0 else 0
        progress.completion_percentage = round(perc, 2)
        progress.is_completed = (perc >= 100)
        progress.save()

        return Response({
            "attempt_id": str(attempt.id),
            "score": attempt.score,
            "correct": attempt.correct_answers,
            "wrong": attempt.wrong_answers,
            "current_round": current_round,
            "is_completed": progress.is_completed
        }, status=status.HTTP_201_CREATED)

class QuizLastAttemptView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, quiz_id):
        # 1. HATA KONTROLÜ: quiz_id'nin gelip gelmediğini kontrol et
        if not quiz_id:
            return Response({"error": "Quiz ID eksik"}, status=400)

        # 2. SORGULAMA: filter() kullanarak hata (404) fırlatmasını engelliyoruz
        # Quiz id'si veya bağlı olduğu material üzerinden de arama yapabiliriz
        attempt = StudentQuizAttempt.objects.filter(
            student=request.user, 
            quiz_id=quiz_id # Buradaki id'nin DB'deki ile tip uyuşmazlığı olabilir
        ).order_by('-completed_at').first()
        
        # 3. VERİ VARSA DÖN
        if attempt:
            return Response({
                "id": str(attempt.id), 
                "score": attempt.score,
                "correct": attempt.correct_answers,
                "wrong": attempt.wrong_answers 
            }, status=200)
        
        # 4. VERİ YOKSA (Buraya düşüyorsa DB'deki ID ile 14 uyuşmuyor demektir)
        # 404 yerine boş obje dönerek frontend'i kırmıyoruz
        return Response({}, status=200)

class QuizAIAnalysisView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, attempt_id):
        try:
            # 1. Sınav denemesini bul
            attempt = get_object_or_404(StudentQuizAttempt, id=attempt_id, student=request.user)
            
            # 2. Haftalık içerik ve ilerleme kaydına ulaş
            weekly_content = attempt.quiz.material.parent_content
            progress = StudentProgress.objects.get(student=request.user, weekly_content=weekly_content)
            
            # --- 2. TUR TETİKLEME MANTIĞI (Aynı kalıyor) ---
            if attempt.wrong_answers > 0 and progress.current_attempt_round == 1:
                progress.current_attempt_round = 2
                progress.completion_percentage = 0  
                progress.save()

            # 3. VERİTABANINDAN HAZIR ANALİZLERİ TOPLA
            # Öğrencinin yanlış cevapladığı soruları çekiyoruz
            wrong_answers = StudentAnswer.objects.filter(
                attempt=attempt, 
                is_correct=False
            ).select_related('question')

            combined_analysis = ""
            user_name = request.user.first_name if request.user.first_name else request.user.username
            
            combined_analysis += f"Merhaba {user_name}, bu testteki performansını senin için analiz ettim:\n\n"

            for ans in wrong_answers:
                # Soru bazlı hazır açıklamayı (explanation) çekiyoruz
                q_text = ans.question.question_text
                # Eğer explanation boşsa bir fallback metni koyuyoruz
                q_analysis = ans.question.explanation if ans.question.explanation else "Bu konuyla ilgili ders notlarını tekrar gözden geçirmelisin."
                
                combined_analysis += f"• SORU: {q_text}\n"
                combined_analysis += f"• ANALİZ: {q_analysis}\n\n"

            combined_analysis += "\nŞimdi 2. tura geçerek bu eksiklerini tamamlayabilirsin. Başarılar!"

            return Response({
                "ai_feedback": combined_analysis, # İsim aynı kalsın ki frontend kırılmasın
                "current_round": progress.current_attempt_round
            }, status=200)
            
        except Exception as e: 
            return Response({"error": "Analiz verisi alınamadı."}, status=500)

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from django.db.models import Sum
from django.contrib.auth import get_user_model
from .models import *

User = get_user_model()

class BulkAcademicReportView(APIView):
    """
    Akademisyen Paneli için toplu PDF raporu verisi sağlar.
    Bellek içi filtreleme ile yüksek performanslı rapor üretir.
    """
    permission_classes = [IsAuthenticated, IsAdminUser]

    def get(self, request):
        # 1. Filtre parametresini al
        department_filter = request.query_params.get('department')
        
        if not department_filter or department_filter == 'all':
            return Response(
                {"detail": "Rapor oluşturmak için geçerli bir bölüm seçilmelidir."}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        # 2. SEÇİLİ BÖLÜMDEKİ öğrencileri tek seferde getir
        students = User.objects.filter(
            department=department_filter,
            is_staff=False, 
            is_teacher=False
        ).order_by('first_name')
        
        student_ids = list(students.values_list('id', flat=True))

        # --- KRİTİK PERFORMANS ADIMI: TÜM VERİLERİ TOPLUCA ÇEK (N+1 ÖNLEYİCİ) ---
        # Veritabanına binlerce kez gitmek yerine 4-5 büyük sorgu atıyoruz.
        all_time_tracking = list(TimeTracking.objects.filter(student_id__in=student_ids).select_related('weekly_content', 'material'))
        all_attempts = list(StudentQuizAttempt.objects.filter(student_id__in=student_ids).select_related('quiz__material__parent_content'))
        all_progress = list(StudentProgress.objects.filter(student_id__in=student_ids).select_related('weekly_content'))
        all_pre_tests = {pt.student_id: pt for pt in PreTestResult.objects.filter(student_id__in=student_ids)}
        
        # Haftalık içerikleri ve materyalleri belleğe al (Sorgu sayısını azaltmak için)
        weekly_contents = list(WeeklyContent.objects.all().prefetch_related('materials'))
        
        report_data = []

        # 3. Öğrenci Döngüsü (Artık veritabanına gitmiyoruz, bellekteki listeleri kullanıyoruz)
        for student in students:
            # Bu öğrenciye ait verileri bellekte süz
            s_times = [t for t in all_time_tracking if t.student_id == student.id]
            s_attempts = [a for a in all_attempts if a.student_id == student.id]
            s_progress = [p for p in all_progress if p.student_id == student.id]
            s_pre_test = all_pre_tests.get(student.id)

            # Ön Test Bilgisi
            pre_test_info = "Girilmedi"
            if s_pre_test:
                pre_test_info = f"%{int(s_pre_test.score)} ({s_pre_test.correct_answers}D / {s_pre_test.wrong_answers}Y)"
            
            # Genel Toplam Süre (Bellekte topla)
            overall_total_seconds = sum(t.duration_seconds for t in s_times)
            
            weekly_stats = []
            
            # 4. 14 Haftalık Veri Döngüsü
            for i in range(1, 15):
                # O haftanın içerik nesnesini bellekte bul
                week_content = next((wc for wc in weekly_contents if wc.week_number == i), None)
                
                # Başlangıç değerleri
                duration_1 = 0
                duration_2 = 0
                correct_1, wrong_1, score_1 = 0, 0, 0
                correct_2, wrong_2, score_2 = 0, 0, 0
                material_details = []

                if week_content:
                    # Tur 1 & 2 Süreleri
                    duration_1 = sum(t.duration_seconds for t in s_times if t.weekly_content_id == week_content.id and t.attempt_round == 1)
                    duration_2 = sum(t.duration_seconds for t in s_times if t.weekly_content_id == week_content.id and t.attempt_round == 2)
                    
                    # Sınav Denemeleri
                    att_1 = next((a for a in s_attempts if a.quiz.material.parent_content_id == week_content.id and a.attempt_round == 1), None)
                    if att_1:
                        correct_1, wrong_1, score_1 = att_1.correct_answers, att_1.wrong_answers, att_1.score
                        
                    att_2 = next((a for a in s_attempts if a.quiz.material.parent_content_id == week_content.id and a.attempt_round == 2), None)
                    if att_2:
                        correct_2, wrong_2, score_2 = att_2.correct_answers, att_2.wrong_answers, att_2.score
                    
                    # Materyal Bazlı Süreler
                    for m in week_content.materials.all():
                        m_dur = sum(t.duration_seconds for t in s_times if t.material_id == m.id)
                        material_details.append({
                            "title": m.title,
                            "content_type": m.content_type,
                            "duration_seconds": m_dur
                        })

                # İlerleme Durumu
                prog_rec = next((p for p in s_progress if p.weekly_content_id == (week_content.id if week_content else None)), None)
                progress_value = prog_rec.completion_percentage if prog_rec else 0

                weekly_stats.append({
                    "week": i,
                    "progress": float(progress_value),
                    "material_details": material_details,
                    "duration_seconds": duration_1,
                    "correct": correct_1,
                    "wrong": wrong_1,
                    "score_1": score_1,
                    "duration_seconds_2": duration_2,
                    "correct_2": correct_2,
                    "wrong_2": wrong_2,
                    "score_2": score_2,
                    "has_quiz": True if (att_1 or att_2) else False,
                    "is_round_2_started": True if (duration_2 > 0 or att_2) else False
                })

            # 5. Öğrenci Paketini Ana Listeye Ekle
            report_data.append({
                "id": str(student.id),
                "full_name": f"{student.first_name} {student.last_name}".upper(),
                "email": student.email,
                "department": student.department,
                "total_points": getattr(student, 'total_points', 0),
                "total_time": overall_total_seconds,
                "weekly_breakdown": weekly_stats,
                "pre_test_score": pre_test_info,
            })

        return Response(report_data, status=status.HTTP_200_OK)
    
class PreTestSubmitView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        answers = request.data.get('answers', []) # [{'question_id': 1, 'option_id': 5}, ...]
        correct_count = 0
        total_questions = PreTestQuestion.objects.count()

        for ans in answers:
            opt = PreTestOption.objects.filter(
                id=ans['option_id'], 
                question_id=ans['question_id']
            ).first()
            if opt and opt.is_correct:
                correct_count += 1

        score = (correct_count / total_questions * 100) if total_questions > 0 else 0
        
        result, _ = PreTestResult.objects.update_or_create(
            student=request.user,
            defaults={
                'correct_answers': correct_count,
                'wrong_answers': total_questions - correct_count,
                'score': score,
                'is_completed': True
            }
        )

        return Response({"score": score, "status": "completed"}, status=200)

class PreTestStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # 1. Mevcut Ön Test Sorularını Getir
        questions = PreTestQuestion.objects.all()
        questions_serializer = PreTestQuestionSerializer(questions, many=True)
        
        # 2. Öğrencinin Test Sonucunu Getir
        result = PreTestResult.objects.filter(student=request.user).first()
        result_data = None
        if result:
            result_data = {
                "is_completed": result.is_completed,
                "score": result.score,
                "correct": result.correct_answers,
                "wrong": result.wrong_answers
            }
            
        return Response({
            "questions": questions_serializer.data,
            "result": result_data
        }, status=status.HTTP_200_OK)

User = get_user_model()

class ChatbotAnalyticsView(APIView):
    """
    Akademisyen Paneli için Chatbot kullanım raporu sağlar.
    """
    permission_classes = [IsAuthenticated, IsAdminUser]

    def get(self, request):
        dept = request.query_params.get('department')
        if not dept or dept == 'all':
            return Response({"error": "Bölüm seçimi zorunludur."}, status=400)

        # 1. Bölümdeki öğrencileri getir
        students = User.objects.filter(
            department=dept, 
            is_staff=False, 
            is_teacher=False
        ).order_by('first_name')
        
        student_ids = list(students.values_list('id', flat=True))

        # 2. Tüm soruları tek seferde, haftalık içerik bilgisiyle çek
        all_questions = list(StudentQuestion.objects.filter(
            student_id__in=student_ids
        ).select_related('weekly_content').order_by('-created_at'))

        report_data = []

        for student in students:
            # Bellek içi filtreleme (Veritabanına tekrar gitmez)
            s_questions = [q for q in all_questions if q.student_id == student.id]
            
            report_data.append({
                "student_name": f"{student.first_name} {student.last_name}".upper(),
                "total_count": len(s_questions),
                "questions": [
                    {
                        "text": q.question_text,
                        "week": q.weekly_content.week_number if q.weekly_content else "Genel",
                        "date": q.created_at.strftime('%d.%m.%Y %H:%M')
                    } for q in s_questions
                ]
            })

        return Response(report_data, status=200)

from django.shortcuts import get_object_or_404
from django.utils import timezone
from datetime import timedelta
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from .models import WeeklyContent, TemporaryUnlock, WeeklyPreTestResult

class WeeklyPreTestSubmitView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, week_number):
        # 1. Haftalık içeriği ve soruları al
        content = get_object_or_404(WeeklyContent, week_number=week_number)
        questions = content.entry_questions.all().prefetch_related('options')
        answers = request.data.get('answers', []) # [{'question_id': X, 'option_id': Y}, ...]
        
        wrong_target_weeks = set() 
        correct_count = 0
        wrong_count = 0

        # 2. Cevapları kontrol et
        for q in questions:
            # Öğrencinin bu soruya verdiği cevabı bul (Frontend'den gelen yapıya göre kontrol)
            # Eğer frontend'den direkt {q_id: opt_id} geliyorsa burayı ona göre revize edebilirsin
            user_answer = next((a for a in answers if str(a.get('question_id')) == str(q.id)), None)
            
            is_correct = False
            if user_answer:
                # Seçilen opsiyonun doğruluğunu kontrol et
                selected_opt_exists = q.options.filter(id=user_answer.get('option_id'), is_correct=True).exists()
                if selected_opt_exists:
                    is_correct = True
                    correct_count += 1
                else:
                    wrong_count += 1
            else:
                # Hiç cevap verilmemişse yanlış sayılır
                wrong_count += 1
            
            # 3. Eğer yanlışsa, bu sorunun hedeflediği haftayı "açılacaklar" listesine ekle
            if not is_correct:
                if q.target_week:
                    wrong_target_weeks.add(q.target_week)

        # 4. Yanlış yapılan haftalar için 2 günlük kilit açma kaydı oluştur
        unlock_duration = timezone.now() + timedelta(days=2)
        for target_week in wrong_target_weeks:
            TemporaryUnlock.objects.update_or_create(
                student=request.user,
                week=target_week,
                defaults={'unlock_until': unlock_duration}
            )

        # 5. TEST SONUÇLARINI KAYDET (Admin Panelini Dolduran Kısım Burası)
        # Hangi haftaların açıldığını da JSON listesi olarak tutuyoruz
        unlocked_week_numbers = [tw.week_number for tw in wrong_target_weeks]
        
        WeeklyPreTestResult.objects.update_or_create(
            student=request.user,
            week=content,
            defaults={
                'is_completed': True,
                'correct_count': correct_count,
                'wrong_count': wrong_count,
                'unlocked_weeks_json': unlocked_week_numbers
            }
        )

        # 6. Frontend Analiz Ekranı İçin Gerekli Verileri Dön
        return Response({
            "status": "success",
            "message": "Test tamamlandı, haftalık içeriklere erişebilirsiniz.",
            "correct_count": correct_count,
            "wrong_count": wrong_count,
            "unlocked_week_numbers": unlocked_week_numbers
        }, status=200)
    
class StudentBadgeListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            # 1. Rozet atama mantığını çalıştır
            try:
                self.check_and_assign_badges(request.user)
            except Exception as e:
                print(f"Atama Hatası: {e}")

            # 2. Rozetleri çek
            badges = Badge.objects.all()

            # 3. DÜZELTME: many=True ekliyoruz çünkü 'badges' bir listedir!
            serializer = BadgeStatusSerializer(
                badges, 
                many=True, # <--- Eksik olan ve 500 hatası veren kısım burasıydı!
                context={'request': request}
            )
            
            return Response(serializer.data, status=200)

        except Exception as e:
            print(f"Kritik Hata: {str(e)}")
            return Response({"error": str(e)}, status=500)

    def check_and_assign_badges(self, user):
        from .models import Badge, StudentBadge, StudentProgress, StudentQuizAttempt
        
        # --- ROZET 1: İLK MATERYAL ---
        try:
            if StudentProgress.objects.filter(student=user, is_completed=True).exists():
                badge = Badge.objects.filter(badge_type='first_material').first()
                if badge:
                    StudentBadge.objects.get_or_create(student=user, badge=badge)
        except Exception as e:
            print(f"HATA (İlk Materyal): {e}")

        # --- ROZET 2: 2 HAFTA ÜST ÜSTE FULL ---
        try:
            # Sadece puanı 100 olanları çekiyoruz
            attempts = StudentQuizAttempt.objects.filter(
                student=user, 
                score=100
            ).order_by('-completed_at')

            distinct_weeks = []
            seen_weeks = set()
            
            for att in attempts:
                # GÜVENLİ ERİŞİM: Hiçbir aşamada None hatası almamak için
                if hasattr(att, 'quiz') and att.quiz:
                    if hasattr(att.quiz, 'material') and att.quiz.material:
                        parent = att.quiz.material.parent_content
                        if parent and parent.week_number is not None:
                            w_num = parent.week_number
                            if w_num not in seen_weeks:
                                distinct_weeks.append(w_num)
                                seen_weeks.add(w_num)
                
                if len(distinct_weeks) == 2:
                    break

            if len(distinct_weeks) == 2:
                # Ardışık hafta kontrolü (11-10=1 gibi)
                if abs(distinct_weeks[0] - distinct_weeks[1]) == 1:
                    badge = Badge.objects.filter(badge_type='double_test_streak').first()
                    if badge:
                        StudentBadge.objects.get_or_create(student=user, badge=badge)
        except Exception as e:
            print(f"HATA (2 Hafta Seri): {e}")


class SurveyDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, week_number):
        # İlgili haftanın anketini ve sorularını getirir
        try:
            survey = Survey.objects.get(week_number=week_number)
            serializer = SurveySerializer(survey)
            return Response(serializer.data)
        except Survey.DoesNotExist:
            return Response({"detail": "Bu hafta için anket bulunamadı."}, status=404)

   # SurveyDetailView içindeki POST metodunu şu şekilde güncelle:
    def post(self, request, week_number):
        # Frontend'den gelen veri yapısını esnek şekilde karşıla
        data = request.data
        responses_list = data.get('answers', data) if isinstance(data, dict) else data

        if not isinstance(responses_list, list):
            return Response({"error": "Geçersiz veri formatı. Liste bekleniyor."}, status=400)

        responses_to_create = []
        from .models import SurveyOption, StudentSurveyResponse, SurveyQuestion

        try:
            for item in responses_list:
                q_id = item.get('question_id')
                val = item.get('answer_value')

                if q_id is None or val is None:
                    continue

                # --- DİNAMİK ŞIK BULMA MANTIĞI ---
                # Soruya ait şıklar içinden tam olarak o değere (1, 2, 3 vb.) sahip olanı getir
                opt = SurveyOption.objects.filter(question_id=q_id, value=val).first()
                
                if opt:
                    # Eğer DB'de şık tanımlıysa, hocanın yazdığı metni al
                    ans_metni = opt.option_text
                else:
                    # EĞER ŞIK BULUNAMAZSA:
                    # Sabit metin koymak yerine, o sorunun o andaki şıklarını debug etmek için
                    # şık metni yerine uyarı mesajı yazıyoruz. 
                    # Bu sayede admin panelinde hatanın nedenini anlarsın.
                    ans_metni = f"Hata: {val} değerine ait şık metni bulunamadı!"

                responses_to_create.append(StudentSurveyResponse(
                    student=request.user,
                    question_id=q_id,
                    answer_value=val,
                    answer_text=ans_metni
                ))

            # Kayıt işlemi
            if responses_to_create:
                # Mükerrer kaydı önlemek için (Aynı öğrenci aynı soruya tekrar cevap verirse)
                q_ids = [r.question_id for r in responses_to_create]
                StudentSurveyResponse.objects.filter(student=request.user, question_id__in=q_ids).delete()
                
                StudentSurveyResponse.objects.bulk_create(responses_to_create)
                return Response({"detail": "Anket cevapları dinamik olarak kaydedildi."}, status=201)
            
            return Response({"error": "İşlenecek veri bulunamadı."}, status=400)

        except Exception as e:
            return Response({"error": f"Sunucu hatası: {str(e)}"}, status=500)

from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import permissions
from django.db.models import Value, CharField
from django.db.models.functions import Concat

class AcademicSurveyAnalyticsView(APIView):
    permission_classes = [permissions.IsAdminUser] # Sadece Akademisyen/Admin

    def get(self, request):
        dept = request.query_params.get('department')
        survey_id = request.query_params.get('survey_id') # Frontend'den gelen hafta numarasıdır
        
        # Sadece 4. hafta ve sonrasındaki anketlerin yanıtlarını çekiyoruz
        responses = StudentSurveyResponse.objects.filter(
            question__survey__week_number__gte=4
        )
        
        # Filtreleri uygula
        if dept:
            responses = responses.filter(student__department=dept)
        if survey_id and survey_id != 'all':
            responses = responses.filter(question__survey__week_number=survey_id)
            
        # Orijinal Ölçek Sabitleri (Veritabanındaki null verileri tamir etmek için koruma kalkanı)
        scale_map = {
            1: "Hiçbir zaman",
            2: "Ender olarak",
            3: "Bazen",
            4: "Sıklıkla",
            5: "Her zaman"
        }
            
        # --- KESİN ÇÖZÜM VE SÜPER OPTİMİZASYON ALANI (TIMEOUT ENGELLEYİCİ) ---
        # N+1 query faciasını önlemek için Concat ile ad ve soyadı veritabanı seviyesinde birleştiriyoruz.
        # Modelleri ağır nesneler olarak değil, .values() ile sadece ihtiyacımız olan alanları hafif sözlük (dict) olarak çekiyoruz.
        raw_responses = responses.annotate(
            full_name=Concat(
                'student__first_name', Value(' '), 'student__last_name',
                output_field=CharField()
            )
        ).values(
            'full_name',
            'question__text',
            'answer_value',
            'answer_text',
            'question__category'
        )

        report = []
        for r in raw_responses:
            db_text = r['answer_text']
            val = r['answer_value']
            
            # Gelen verinin boş string, None veya string "null" olup olmadığını denetliyoruz
            is_valid = db_text and str(db_text).strip() and str(db_text).lower() != 'null'
            
            # Eğer veri bozuksa veya boşsa puana göre ölçek karşılığını veriyoruz
            final_text = db_text if is_valid else scale_map.get(val, f"{val} Puan")

            report.append({
                "student": r['full_name'] if r['full_name'] and r['full_name'].strip() else "Bilinmeyen Öğrenci",
                "question": r['question__text'] if r['question__text'] else "Soru Maddesi Yok",
                "answer": val,  # Grafik motoru için sayısal değer (1-5)
                "answer_text": final_text,  # Frontend'in parantez içine basacağı garantili temiz metin
                "category": r['question__category'] if r['question__category'] else "Genel"
            })
            
        return Response(report)

from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import permissions
from django.db.models import Sum, Value, CharField, FloatField
from django.db.models.functions import Concat, Cast
from django.contrib.auth import get_user_model

# Senin modellerinin imports alanları (Dosya yoluna göre revize edebilirsin)
from .models import TimeTracking 

User = get_user_model()

class StudentTimeAnalyticsView(APIView):
    permission_classes = [permissions.IsAdminUser] # Sadece Akademisyen/Admin görebilir

    def get(self, request):
        dept = request.query_params.get('department')
        
        # Öğrencilerin TimeTracking log veritabanını filtrele
        logs = TimeTracking.objects.all()
        
        if dept:
            logs = logs.filter(student__department=dept)
            
        # --- N+1 QUERY ENGELLİ SÜPER OPTİMİZASYON ALANI ---
        # duration_seconds alanını topluyoruz (Sum) ve veritabanı düzeyinde 3600'e bölerek Saate çeviriyoruz.
        # values() kullanarak Django'nun ağır model instance'larını belleğe yüklemeden hafif JSON datası üretiyoruz.
        time_reports = logs.values('student').annotate(
            full_name=Concat(
                'student__first_name', Value(' '), 'student__last_name',
                output_field=CharField()
            ),
            department_name=Cast('student__department', CharField()), # Bölüm string veya ilişki ise uyum sağlar
            total_hours=Sum(Cast('duration_seconds', FloatField())) / 3600.0
        ).order_by('-total_hours') # En çok süre geçirenden en aza doğru sıralama

        report = []
        for idx, item in enumerate(time_reports):
            hours_val = item['total_hours'] if item['total_hours'] else 0.0
            
            # Göz yormayan temiz bir süre formatı oluşturuyoruz (Örn: 12.45 Saat)
            formatted_time = f"{round(hours_val, 2)} Saat"
            
            report.append({
                "rank": idx + 1,
                "student": item['full_name'] if item['full_name'] and item['full_name'].strip() else "Bilinmeyen Öğrenci",
                "department": item['department_name'] if item['department_name'] else "Genel / Belirtilmemiş",
                "total_time": formatted_time
            })
            
        return Response(report)

from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import permissions
from django.db.models import Sum, Value, CharField, FloatField
from django.db.models.functions import Concat, Cast
from .models import TimeTracking

class SystemTimeAnalyticsView(APIView):
    permission_classes = [permissions.IsAdminUser]

    def get(self, request):
        dept = request.query_params.get('department')
        
        # Ana sorgu kalkanı
        logs = TimeTracking.objects.all()
        if dept:
            logs = logs.filter(student__department=dept)

        # 1. Genel Öğrenci Bazında Toplam Süreleri Hesapla
        student_totals = logs.values('student').annotate(
            full_name=Concat(
                'student__first_name', Value(' '), 'student__last_name',
                output_field=CharField()
            ),
            total_hours=Sum(Cast('duration_seconds', FloatField())) / 3600.0
        ).order_by('-total_hours')

        # Varsayılan genel değerler
        max_student = {"student": "Veri Yok", "time": "0 Saat"}
        min_student = {"student": "Veri Yok", "time": "0 Saat"}

        if student_totals.exists():
            most_active = student_totals.first()
            least_active = student_totals.last()
            
            max_student = {
                "student": most_active['full_name'] if most_active['full_name'].strip() else "Bilinmeyen Öğrenci",
                "time": f"{round(most_active['total_hours'], 2)} Saat"
            }
            min_student = {
                "student": least_active['full_name'] if least_active['full_name'].strip() else "Bilinmeyen Öğrenci",
                "time": f"{round(least_active['total_hours'], 2)} Saat"
            }

        # 2. Genel Etkinlik Türlerine Göre Zaman Dağılımı
        activity_totals = logs.values('material__content_type').annotate(
            total_hours=Sum(Cast('duration_seconds', FloatField())) / 3600.0
        ).order_by('-total_hours')

        type_mapping = {
            'video': 'Video İzleme',
            'podcast': 'Podcast Dinleme',
            'form': 'Bilgi Testi (Quiz)',
            'pdf': 'Ders Notu Okuma (PDF)',
            'assignment': 'Ödev Çözme'
        }

        activity_distribution = []
        for act in activity_totals:
            raw_type = act['material__content_type']
            if raw_type:
                activity_distribution.append({
                    "type": type_mapping.get(raw_type, raw_type.upper()),
                    "hours": round(act['total_hours'], 2)
                })

        # ----------------------------------------------------------------
        # 3. HAFTA HAFTA AKADEMİK KIRILIM VE ÖĞRENCİ SIRALAMA ANALİZLERİ
        # ----------------------------------------------------------------
        weekly_totals = logs.values('weekly_content__week_number').annotate(
            total_hours=Sum(Cast('duration_seconds', FloatField())) / 3600.0
        ).order_by('weekly_content__week_number')

        weekly_analysis = []
        for week_data in weekly_totals:
            w_num = week_data['weekly_content__week_number']
            if w_num is None:
                continue

            # O haftaya ait özel filtreleme kalkanı
            week_logs = logs.filter(weekly_content__week_number=w_num)

            # Hafta bazında tüm öğrencilerin sürelerini hesapla ve sırala
            week_student_totals = week_logs.values('student').annotate(
                full_name=Concat('student__first_name', Value(' '), 'student__last_name', output_field=CharField()),
                hours=Sum(Cast('duration_seconds', FloatField())) / 3600.0
            ).order_by('-hours')

            w_max = {"student": "Veri Yok", "time": "0 Saat"}
            w_min = {"student": "Veri Yok", "time": "0 Saat"}

            if week_student_totals.exists():
                w_most = week_student_totals.first()
                w_least = week_student_totals.last()
                w_max = {
                    "student": w_most['full_name'] if w_most['full_name'].strip() else "Bilinmeyen Öğrenci",
                    "time": f"{round(w_most['hours'], 2)} Saat"
                }
                w_min = {
                    "student": w_least['full_name'] if w_least['full_name'].strip() else "Bilinmeyen Öğrenci",
                    "time": f"{round(w_least['hours'], 2)} Saat"
                }

            # Hafta bazında etkinlik dağılımını hesapla
            week_activity_totals = week_logs.values('material__content_type').annotate(
                hours=Sum(Cast('duration_seconds', FloatField())) / 3600.0
            ).order_by('-hours')

            w_activity_dist = []
            for w_act in week_activity_totals:
                w_raw_type = w_act['material__content_type']
                if w_raw_type:
                    w_activity_dist.append({
                        "type": type_mapping.get(w_raw_type, w_raw_type.upper()),
                        "hours": round(w_act['hours'], 2)
                    })

            # EKSTRA İSTEK: O haftanın ilk 15 öğrenci sıralama listesini oluşturuyoruz
            w_student_list = [
                {
                    "rank": idx + 1,
                    "student": s['full_name'] if s['full_name'].strip() else "Bilinmeyen Öğrenci",
                    "time": f"{round(s['hours'], 2)} Saat"
                } for idx, s in enumerate(week_student_totals[:15])
            ]

            weekly_analysis.append({
                "week_number": w_num,
                "total_hours": f"{round(week_data['total_hours'], 2)} Saat",
                "max_engagement": w_max,
                "min_engagement": w_min,
                "activity_distribution": w_activity_dist,
                "student_list": w_student_list # Haftalık sıralama listesi backend'e eklendi
            })

        return Response({
            "max_engagement": max_student,
            "min_engagement": min_student,
            "activity_distribution": activity_distribution,
            "weekly_analysis": weekly_analysis,
            "raw_student_list": [
                {
                    "rank": idx + 1,
                    "student": s['full_name'] if s['full_name'].strip() else "Bilinmeyen Öğrenci",
                    "time": f"{round(s['total_hours'], 2)} Saat"
                } for idx, s in enumerate(student_totals[:15])
            ]
        })

from django.http import HttpResponse
from io import BytesIO
from contents.excel_generator import generate_survey_excel

class ExportSurveyExcelView(APIView):
    permission_classes = [permissions.IsAdminUser]  # Sadece Akademisyen/Admin indirebilir

    def get(self, request, week_number):
        try:
            wb = generate_survey_excel(week_number)
            
            # Bellek içi akışa kaydet
            response_stream = BytesIO()
            wb.save(response_stream)
            response_stream.seek(0)
            
            filename = f"survey_hafta_{week_number}_cevaplari.xlsx"
            response = HttpResponse(
                response_stream.getvalue(),
                content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            return response
        except ValueError as ve:
            return Response({"error": str(ve)}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({"error": f"Sunucu hatası: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)