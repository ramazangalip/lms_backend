from django.urls import path
from .views import MyTokenObtainPairView, SendOTPView, RegisterView
from rest_framework_simplejwt.views import TokenRefreshView

urlpatterns = [
    # Login ve Token İşlemleri
    path('login/', MyTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    
    # Kayıt İşlemleri
    path('send-otp/', SendOTPView.as_view(), name='send_otp'),
    path('register/', RegisterView.as_view(), name='register'),
]