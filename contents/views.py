from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from .models import WeeklyContent
from .serializers import WeeklyContentSerializer

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