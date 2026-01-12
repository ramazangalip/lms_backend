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

# contents/views.py

class WeeklyContentView(APIView):
    """
    Hem öğrencilerin içerikleri listelemesi hem de hocaların içerik eklemesi/güncellemesi
    için kullanılan ana View.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """
        Tüm öğrenciler ve hocalar tüm haftalık içerikleri ve bağlı materyalleri (video/podcast) görür.
        """
        # Bölüm filtresi kaldırıldı, tüm içerikler ortak havuzdan çekiliyor
        contents = WeeklyContent.objects.all().order_by('week_number')
        serializer = WeeklyContentSerializer(contents, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        """
        Sadece hocaların (is_teacher=True) içerik eklemesine veya mevcut haftayı güncellemesine izin verir.
        """
        if not getattr(request.user, 'is_teacher', False):
            return Response(
                {"error": "İçerik ekleme yetkiniz bulunmamaktadır."}, 
                status=status.HTTP_403_FORBIDDEN
            )

        # Serializer içindeki create/update_or_create mantığı ile Nested Data kaydedilir
        serializer = WeeklyContentSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class ContentDetailView(APIView):
    """
    Belirli bir haftanın tüm materyallerini getirmek için kullanılır.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, week_number):
        # Filtrelemeden department şartı çıkarıldı
        content = WeeklyContent.objects.filter(week_number=week_number).first()
        
        if not content:
            return Response(
                {"error": f"{week_number}. hafta içeriği henüz yüklenmemiş."},
                status=status.HTTP_404_NOT_FOUND
            )
            
        serializer = WeeklyContentSerializer(content)
        return Response(serializer.data, status=status.HTTP_200_OK)



# --- TAKİP SİSTEMİ GÜNCELLENMİŞ VERSİYON ---

class TrackActivityView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        # Serializer kullanarak veriyi valide ediyoruz
        serializer = ActivityTrackSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        weekly_content_id = serializer.validated_data.get('weekly_content_id')
        seconds = serializer.validated_data.get('seconds', 30)
        
        try:
            weekly_content = WeeklyContent.objects.get(id=weekly_content_id)
            
            # 1. Süre Takibi (TimeTracking modelindeki weekly_content alanına göre)
            tracking, created = TimeTracking.objects.get_or_create(
                student=request.user,
                weekly_content=weekly_content,
                date=date.today()
            )
            tracking.duration_seconds += seconds
            tracking.save()

            # 2. İlerleme Durumu (StudentProgress modelindeki weekly_content alanına göre)
            progress, _ = StudentProgress.objects.get_or_create(
                student=request.user,
                weekly_content=weekly_content
            )
            # İleride buraya materyal sayısına göre yüzde hesaplama eklenebilir
            progress.save() 

            return Response({"status": "success"}, status=status.HTTP_200_OK)
            
        except WeeklyContent.DoesNotExist:
            return Response({"error": "Haftalık içerik bulunamadı."}, status=status.HTTP_404_NOT_FOUND)
        
class TeacherAnalyticsView(APIView):
    permission_classes = [IsAdminUser] 

    def get(self, request, student_id=None):
        if student_id:
            try:
                student = User.objects.get(id=student_id)
                one_week_ago = timezone.now().date() - timedelta(days=7)
                
                # Modellerdeki weekly_content__title referansına dikkat
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
                    "weekly_analysis": time_stats,
                    "progress_analysis": progress_stats
                })
            except User.DoesNotExist:
                return Response({"error": "Öğrenci bulunamadı."}, status=404)

        else:
            students = User.objects.filter(is_staff=False)
            serializer = StudentAnalyticsSerializer(students, many=True)
            return Response(serializer.data)
        
from django.shortcuts import get_object_or_404

class CompleteMaterialView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = CompleteMaterialSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        material_id = serializer.validated_data.get('material_id')
        material = get_object_or_404(Material, id=material_id)
        weekly_content = material.parent_content
        
        # 1. Bu materyali "tamamlandı" olarak kaydet
        CompletedMaterial.objects.get_or_create(
            student=request.user,
            material=material
        )

        # 2. İlerlemeyi dinamik hesapla
        # O haftadaki toplam materyal sayısı (Video + Podcast + Test)
        total_materials = weekly_content.materials.count()
        
        # Öğrencinin O HAFTADA bitirdiği materyal sayısı
        completed_count = CompletedMaterial.objects.filter(
            student=request.user,
            material__parent_content=weekly_content
        ).count()

        # Hassas yüzde hesaplama
        if total_materials > 0:
            percentage = (completed_count / total_materials) * 100
        else:
            percentage = 0

        # 3. Öğrencinin genel ilerleme tablosunu (StudentProgress) güncelle
        progress, _ = StudentProgress.objects.get_or_create(
            student=request.user,
            weekly_content=weekly_content
        )
        
        progress.completion_percentage = round(percentage, 2)
        progress.is_completed = (percentage >= 100) # %100 ise True olur
        progress.save()

        return Response({
            "status": "success",
            "current_percentage": progress.completion_percentage,
            "progress": f"{completed_count}/{total_materials} materyal tamamlandı"
        }, status=status.HTTP_200_OK)
    
class CompletedMaterialIdsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # Giriş yapmış öğrencinin tamamladığı tüm materyallerin ID'lerini çekiyoruz
        completed_ids = CompletedMaterial.objects.filter(
            student=request.user
        ).values_list('material_id', flat=True)
        
        return Response(list(completed_ids))

class StudentProgressListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # Sadece giriş yapmış olan öğrencinin ilerlemelerini getir
        progresses = StudentProgress.objects.filter(student=request.user).order_by('weekly_content__week_number')
        serializer = StudentProgressSerializer(progresses, many=True)
        return Response(serializer.data)

class StudentAnalyticsView(APIView):
    permission_classes = [IsAdminUser] # Güvenlik: Öğrenciler bu veriye erişemez

    def get(self, request):
        # Sadece öğrenci (is_staff=False) olan kullanıcıları çekelim
        students = User.objects.filter(is_staff=False)
        
        # Daha önce oluşturduğumuz StudentAnalyticsSerializer'ı kullanıyoruz
        # Bu serializer her öğrenci için total_time_spent ve overall_progress hesaplar
        serializer = StudentAnalyticsSerializer(students, many=True)
        return Response(serializer.data)