import random
from rest_framework import status, generics
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from django.core.mail import send_mail
from rest_framework_simplejwt.views import TokenObtainPairView

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
        
        if not email:
            return Response({"error": "E-posta adresi gerekli."}, status=status.HTTP_400_BAD_REQUEST)
        
        if not email.endswith('@bingol.edu.tr'):
            return Response({"error": "Sadece @bingol.edu.tr uzantılı adreslere izin verilir."}, status=status.HTTP_400_BAD_REQUEST)

        otp_code = str(random.randint(100000, 999999))
        
        EmailOTP.objects.update_or_create(
            email=email, 
            defaults={'code': otp_code}
        )

        try:
            send_mail(
                subject='LMS Kayıt Doğrulama Kodu',
                message=f'Bingöl Üniversitesi LMS sistemine kayıt için kodunuz: {otp_code}',
                from_email='ramazansaidgalip@gmail.com',
                recipient_list=[email],
                fail_silently=True,
            )
            return Response({"message": "Doğrulama kodu gönderildi."}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": "E-posta gönderilirken bir hata oluştu."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class RegisterView(generics.CreateAPIView):
    """
    Yeni öğrenci kaydı oluşturur.
    RegisterSerializer içindeki validation'ları kullanır.
    """
    queryset = User.objects.all()
    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]