from django.urls import path
from .views import WeeklyContentView, ContentDetailView

urlpatterns = [
    # Hem öğrencilerin listelemesi hem de hocaların içerik eklemesi için ortak endpoint
    path('list/', WeeklyContentView.as_view(), name='weekly_contents_list'),
    
    # Belirli bir haftanın detaylarını (video ve podcast listesini) getirmek için
    path('week/<int:week_number>/', ContentDetailView.as_view(), name='week_detail'),
]