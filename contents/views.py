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
from google.cloud import aiplatform # Yeni kütüphane
import requests
from google.auth import default
from google.auth.transport.requests import Request as AuthRequest
import vertexai
from vertexai.generative_models import GenerativeModel

# --- ANA İÇERİK VIEW ---

class WeeklyContentView(APIView):
    """
    Hem öğrencilerin içerikleri listelemesi hem de hocaların içerik eklemesi/güncellemesi
    için kullanılan ana View.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """
        Eğer sorguda ?week_number=1 varsa sadece o haftayı, yoksa tüm listeyi getirir.
        """
        week_number = request.query_params.get('week_number')
        if week_number:
            content = WeeklyContent.objects.filter(week_number=week_number).first()
            if content:
                serializer = WeeklyContentSerializer(content, context={'request': request})
                return Response(serializer.data, status=status.HTTP_200_OK)
            return Response({"detail": "Bu hafta henüz boş."}, status=status.HTTP_404_NOT_FOUND)
            
        contents = WeeklyContent.objects.all().order_by('week_number')
        serializer = WeeklyContentSerializer(contents, many=True, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        """
        Sadece hocaların içerik eklemesine veya mevcut haftayı güncellemesine izin verir.
        """
        if not getattr(request.user, 'is_teacher', False):
            return Response(
                {"error": "İçerik ekleme yetkiniz bulunmamaktadır."}, 
                status=status.HTTP_403_FORBIDDEN
            )

        serializer = WeeklyContentSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        
        # --- DEBUG ÇIKTISI (400 Hatasını Çözmek İçin Terminale Bak) ---
        print("\n" + "="*50)
        print("!!! SERIALIZER DOĞRULAMA HATASI (400 BAD REQUEST) !!!")
        print(f"Hata Detayı: {serializer.errors}")
        print("="*50 + "\n")
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class ContentDetailView(APIView):
    """
    Belirli bir haftanın tüm materyallerini getirmek için kullanılır.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, week_number):
        content = WeeklyContent.objects.filter(week_number=week_number).first()
        
        if not content:
            return Response(
                {"error": f"{week_number}. hafta içeriği henüz yüklenmemiş."},
                status=status.HTTP_404_NOT_FOUND
            )
            
        serializer = WeeklyContentSerializer(content, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)

# --- TAKİP VE İLERLEME SİSTEMİ ---

class TrackActivityView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ActivityTrackSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        weekly_content_id = serializer.validated_data.get('weekly_content_id')
        seconds = serializer.validated_data.get('seconds', 30)
        
        try:
            weekly_content = WeeklyContent.objects.get(id=weekly_content_id)
            
            tracking, created = TimeTracking.objects.get_or_create(
                student=request.user,
                weekly_content=weekly_content,
                date=date.today()
            )
            tracking.duration_seconds += seconds
            tracking.save()

            progress, _ = StudentProgress.objects.get_or_create(
                student=request.user,
                weekly_content=weekly_content
            )
            progress.save() 

            return Response({"status": "success"}, status=status.HTTP_200_OK)
            
        except WeeklyContent.DoesNotExist:
            return Response({"error": "Haftalık içerik bulunamadı."}, status=status.HTTP_404_NOT_FOUND)

class CompleteMaterialView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = CompleteMaterialSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        material_id = serializer.validated_data.get('material_id')
        material = get_object_or_404(Material, id=material_id)
        weekly_content = material.parent_content
        
        CompletedMaterial.objects.get_or_create(
            student=request.user,
            material=material
        )

        total_materials = weekly_content.materials.count()
        completed_count = CompletedMaterial.objects.filter(
            student=request.user,
            material__parent_content=weekly_content
        ).count()

        percentage = (completed_count / total_materials) * 100 if total_materials > 0 else 0

        progress, _ = StudentProgress.objects.get_or_create(
            student=request.user,
            weekly_content=weekly_content
        )
        
        progress.completion_percentage = round(percentage, 2)
        progress.is_completed = (percentage >= 100)
        progress.save()

        return Response({
            "status": "success",
            "current_percentage": progress.completion_percentage,
            "progress": f"{completed_count}/{total_materials} materyal tamamlandı"
        }, status=status.HTTP_200_OK)

class CompletedMaterialIdsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        completed_ids = CompletedMaterial.objects.filter(
            student=request.user
        ).values_list('material_id', flat=True)
        return Response(list(completed_ids))

class StudentProgressListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        progresses = StudentProgress.objects.filter(student=request.user).order_by('weekly_content__week_number')
        serializer = StudentProgressSerializer(progresses, many=True)
        return Response(serializer.data)

# --- ANALİZ VE HOCA PANELİ ---

class TeacherAnalyticsView(APIView):
    permission_classes = [IsAdminUser] 

    def get(self, request, student_id=None):
        if student_id:
            try:
                student = User.objects.get(id=student_id)
                one_week_ago = timezone.now().date() - timedelta(days=7)
                
                time_stats = TimeTracking.objects.filter(
                    student=student,
                    date__gte=one_week_ago
                ).values('weekly_content__title', 'weekly_content__week_number').annotate(
                    total_seconds=Sum('duration_seconds')
                ).order_by('weekly_content__week_number')

                progress_stats = StudentProgress.objects.filter(student=student).values(
                    'weekly_content__title', 'completion_percentage', 'is_completed'
                )

                return Response({
                    "student_info": f"{student.first_name} {student.last_name}",
                    "weekly_analysis": list(time_stats),
                    "progress_analysis": list(progress_stats)
                })
            except User.DoesNotExist:
                return Response({"error": "Öğrenci bulunamadı."}, status=404)
        else:
            students = User.objects.filter(is_staff=False)
            serializer = StudentAnalyticsSerializer(students, many=True)
            return Response(serializer.data)

class StudentAnalyticsView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        students = User.objects.filter(is_staff=False)
        serializer = StudentAnalyticsSerializer(students, many=True)
        return Response(serializer.data)

# --- YAPAY ZEKA SOHBET ---

class AIChatView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user_message = request.data.get("message")
        week_id = request.data.get("weekly_content_id")

        if not user_message:
            return Response({"error": "Mesaj boş olamaz."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # 1. Vertex AI Proje Ayarları
            PROJECT_ID = "398808058924"
            LOCATION = "us-central1"
            # Senin yeni Endpoint ID'n (aslında model adı olarak kullanılır)
            ENDPOINT_ID = "3795882475478056960"

            vertexai.init(project=PROJECT_ID, location=LOCATION)

            # 2. Eğittiğin Özel Modeli Yükle
            # Tuned (eğitilmiş) modelini endpoint ID'si üzerinden çağırıyoruz
            model = GenerativeModel(f"projects/{PROJECT_ID}/locations/{LOCATION}/endpoints/{ENDPOINT_ID}")

            # 3. Yanıt Oluştur
            response = model.generate_content(user_message)
            ai_response_text = response.text

            # 4. Veritabanı Kaydı (Mevcut mantığın)
            if week_id:
                try:
                    weekly_content = WeeklyContent.objects.get(id=week_id)
                    StudentQuestion.objects.create(
                        student=request.user,
                        weekly_content=weekly_content,
                        question_text=user_message
                    )
                except WeeklyContent.DoesNotExist:
                    pass

            return Response({"response": ai_response_text}, status=status.HTTP_200_OK)

        except Exception as e:
            print("GEMINI VERTEX ERROR:", str(e))
            return Response(
                {"response": "Yapay zeka asistanı şu an yanıt oluşturamıyor."}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
# --- QUIZ (SINAV) SİSTEMİ ---

class QuizSubmitView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, quiz_id):
        quiz = get_object_or_404(Quiz, id=quiz_id)
        user = request.user
        answers_data = request.data.get('answers', [])

        correct_count = 0
        wrong_count = 0
        
        attempt = StudentQuizAttempt.objects.create(
            student=user,
            quiz=quiz,
            score=0,
            correct_answers=0,
            wrong_answers=0
        )

        for ans in answers_data:
            q_id = ans.get('question_id')
            opt_id = ans.get('option_id')
            
            question = get_object_or_404(QuizQuestion, id=q_id, quiz=quiz)
            option = get_object_or_404(QuizOption, id=opt_id, question=question)

            is_correct = option.is_correct
            if is_correct:
                correct_count += 1
            else:
                wrong_count += 1

            StudentAnswer.objects.create(
                attempt=attempt,
                question=question,
                selected_option=option,
                is_correct=is_correct
            )

        total_questions = quiz.questions.count()
        score = (correct_count / total_questions) * 100 if total_questions > 0 else 0
        
        attempt.score = round(score)
        attempt.correct_answers = correct_count
        attempt.wrong_answers = wrong_count
        attempt.save()

        # --- DÜZELTME BURADA BAŞLIYOR ---
        
        # 1. Materyali tamamlandı olarak işaretle
        CompletedMaterial.objects.get_or_create(
            student=user,
            material=quiz.material
        )

        # 2. İLERLEME YÜZDESİNİ YENİDEN HESAPLA (Boş ilerleme hatasını çözer)
        weekly_content = quiz.material.parent_content
        total_materials = weekly_content.materials.count()
        completed_count = CompletedMaterial.objects.filter(
            student=user,
            material__parent_content=weekly_content
        ).count()

        new_percentage = (completed_count / total_materials) * 100 if total_materials > 0 else 0

        # 3. StudentProgress tablosunu güncelle
        progress_obj, _ = StudentProgress.objects.get_or_create(
            student=user,
            weekly_content=weekly_content
        )
        progress_obj.completion_percentage = round(new_percentage, 2)
        progress_obj.is_completed = (new_percentage >= 100)
        progress_obj.save()

        # --- DÜZELTME BURADA BİTİYOR ---

        return Response({
            "score": attempt.score,
            "correct": correct_count,
            "wrong": wrong_count,
            "current_week_progress": progress_obj.completion_percentage, # Bilgi için eklendi
            "message": "Sınav başarıyla tamamlandı ve ilerlemeniz güncellendi."
        }, status=status.HTTP_201_CREATED)