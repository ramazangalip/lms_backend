from django.contrib import admin
from django.urls import path, include
from users.views import MyTokenObtainPairView, MyTokenRefreshView

urlpatterns = [
    path('admin/', admin.site.urls),
    # JWT Login (Token alma ve yenileme)
    path('api/login/', MyTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', MyTokenRefreshView.as_view(), name='token_refresh'),
    # Kendi uygulamalarımız
    path('api/users/', include('users.urls')),
    path('api/contents/', include('contents.urls')),
]