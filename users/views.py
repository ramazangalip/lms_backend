import random
from rest_framework import status, generics
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from django.core.mail import send_mail
from rest_framework_simplejwt.views import TokenObtainPairView
import requests
from .models import User, EmailOTP
from .serializers import (
    RegisterSerializer, 
    MyTokenObtainPairSerializer
)

class MyTokenObtainPairView(TokenObtainPairView):
    """
    Özelleştirilmiş login view. 
    Token içine is_teacher, is_student gibi roller ekleyen serializer'ı kullanır.
    """
    serializer_class = MyTokenObtainPairSerializer


class SendOTPView(APIView):
    """
    Öğrenci e-postasını alır, @bingol.edu.tr kontrolü yapar ve OTP gönderir.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        email = request.data.get('email')
        
        # 1. Kontroller
        if not email:
            return Response({"error": "E-posta adresi gerekli."}, status=status.HTTP_400_BAD_REQUEST)
        
        if not email.endswith('@bingol.edu.tr'):
            return Response({"error": "Sadece @bingol.edu.tr uzantılı adreslere izin verilir."}, status=status.HTTP_400_BAD_REQUEST)

        # 2. OTP Oluşturma ve Kaydetme
        otp_code = str(random.randint(100000, 999999))
        EmailOTP.objects.update_or_create(
            email=email, 
            defaults={'code': otp_code}
        )

        # 3. Brevo API ile Mail Gönderme
        url = "https://api.brevo.com/v3/smtp/email"
        api_key = "CdxftNgFXEj2GKYZ" # Senin API anahtarın
        
        payload = {
            "sender": {"name": "Bingöl LMS", "email": "ramazansaidgalip@gmail.com"},
            "to": [{"email": email}],
            "subject": "LMS Kayıt Doğrulama Kodu",
            "htmlContent": f"""
                <html>
                    <body style="font-family: Arial, sans-serif;">
                        <h2>Bingöl Üniversitesi LMS Sistemi</h2>
                        <p>Kayıt işleminizi tamamlamak için doğrulama kodunuz:</p>
                        <h1 style="color: #d32f2f;">{otp_code}</h1>
                        <p>Bu kod tek kullanımlıktır.</p>
                    </body>
                </html>
            """
        }
        
        headers = {
            "accept": "application/json",
            "content-type": "application/json",
            "api-key": api_key
        }

        try:
            # SMTP yerine HTTP POST isteği gönderiyoruz (Engellenemez)
            response = requests.post(url, json=payload, headers=headers, timeout=10)
            
            if response.status_code == 201:
                return Response({"message": "Doğrulama kodu gönderildi."}, status=status.HTTP_200_OK)
            else:
                # Brevo bir hata dönerse (örn: 401, 403) loglarda gör
                print(f"Brevo API Hatası: {response.status_code} - {response.text}")
                return Response({"error": "Mail servisi şu an kullanılamıyor."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
                
        except requests.exceptions.RequestException as e:
            print(f"Bağlantı Hatası: {e}")
            return Response({"error": "Sunucu bağlantı hatası oluştu."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class RegisterView(generics.CreateAPIView):
    """
    Yeni öğrenci kaydı oluşturur.
    RegisterSerializer içindeki validation'ları kullanır.
    """
    queryset = User.objects.all()
    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]