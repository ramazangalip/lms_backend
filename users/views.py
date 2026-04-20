import random
from rest_framework import status, generics
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from rest_framework.permissions import IsAuthenticated
from django.core.mail import send_mail
from django.db.models import Min
from rest_framework_simplejwt.views import TokenObtainPairView

from .models import User, EmailOTP
from .serializers import *

class MyTokenObtainPairView(TokenObtainPairView):
    serializer_class = MyTokenObtainPairSerializer

class SendOTPView(APIView):
    """Kayıt için OTP gönderir (Email sistemde olmamalı)"""
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        email = request.data.get('email')
        if not email or not email.endswith('@bingol.edu.tr'):
            return Response({"error": "Geçerli bir kurum adresi giriniz."}, status=400)

        if User.objects.filter(email=email).exists():
            return Response({"error": "Bu e-posta zaten kayıtlı."}, status=400)

        return self.send_otp(email, "Kayıt Doğrulama")

    def send_otp(self, email, subject_text):
        otp_code = str(random.randint(100000, 999999))
        EmailOTP.objects.update_or_create(email=email, defaults={'code': otp_code})
        
        try:
            send_mail(
                subject=f'LMS {subject_text} Kodu',
                message=f'İşleminiz için doğrulama kodunuz: {otp_code}',
                from_email='ramazansaidgalip@gmail.com',
                recipient_list=[email],
                fail_silently=False,
            )
            return Response({"message": "Kod gönderildi."}, status=200)
        except:
            return Response({"error": "E-posta hatası."}, status=500)

class SendResetOTPView(SendOTPView):
    authentication_classes = []
    """Şifre sıfırlama için OTP gönderir (Email sistemde kayıtlı olmalı)"""
    def post(self, request):
        email = request.data.get('email')
        if not email:
            return Response({"error": "E-posta gerekli."}, status=400)

        if not User.objects.filter(email=email).exists():
            return Response({"error": "Bu e-posta adresiyle kayıtlı bir kullanıcı bulunamadı."}, status=404)

        return self.send_otp(email, "Şifre Sıfırlama")

class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]
    authentication_classes = []

class PasswordResetConfirmView(APIView):
    """Kodu ve yeni şifreyi alır, doğrularsa şifreyi günceller."""
    permission_classes = [AllowAny]
    
    def post(self, request):
        serializer = PasswordResetSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response({"message": "Şifreniz başarıyla sıfırlandı."}, status=200)
        return Response(serializer.errors, status=400)
    
class UserProfileView(APIView):
    """Giriş yapmış kullanıcının profil bilgilerini döner"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        
        # get_department_display() Django'nun choices yapısındaki okunaklı metni (sağ tarafı) getirir
        department_name = user.get_department_display() if user.department else "Bölüm Belirtilmemiş"

        data = {
            "first_name": user.first_name,
            "last_name": user.last_name,
            "department": department_name,
            "total_points": user.total_points,
            "email": user.email,
            "is_student": user.is_student,
            "is_teacher": user.is_teacher
        }
        return Response(data, status=200)
    




from django.db.models import Min, Value, DateTimeField
from django.db.models.functions import Coalesce
from datetime import datetime
from django.utils import timezone # En üste ekle

class DepartmentLeaderboardView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            user = request.user
            if not user.department:
                return Response({"error": "Bölüm bilgisi yok."}, status=400)

            # Doğru ilişki adı: 'completedmaterial' (Model isminin küçük harfi)
            # Sıralama: Önce Puan (Azalan), sonra en eski tamamlama tarihi (Artan)
            leaderboard = User.objects.filter(
                department=user.department, 
                is_student=True
            ).annotate(
                first_completion=Coalesce(
                    Min('completedmaterial__completed_at'), 
                    # 2099 yerine şu anın çok ilerisinde, timezone uyumlu bir tarih
                    Value(timezone.make_aware(datetime(2099, 1, 1)), output_field=DateTimeField())
                )
            ).order_by('-total_points', 'first_completion')[:5]

            data = []
            for index, student in enumerate(leaderboard):
                data.append({
                    "rank": index + 1,
                    "full_name": f"{student.first_name} {student.last_name}".strip() or student.email,
                    "total_points": student.total_points,
                    "is_me": student.id == user.id
                })

            return Response({
                "department_name": user.get_department_display(),
                "students": data
            }, status=200)

        except Exception as e:
            # Hatanın tam yerini görmek için terminale yazdırıyoruz
            print(f"LİDERLİK TABLOSU KRİTİK HATA: {str(e)}")
            return Response({"error": "Sıralama hesaplanamadı."}, status=500)