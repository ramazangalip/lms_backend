from django.db import models
from django.contrib.auth.models import AbstractUser

class User(AbstractUser):
    DEPARTMENT_CHOICES = [
        ('siyasetbilimi', 'Siyaset Bilimi ve Kamu Yönetimi'),
        ('turkdili', 'Türk Dili ve Edebiyatı'),
        ('matematik', 'Matematik'),
    ]

    email = models.EmailField(unique=True, verbose_name="E-posta Adresi")
    is_teacher = models.BooleanField(default=False, db_index=True, verbose_name="Akademisyen mi?")
    is_student = models.BooleanField(default=False, db_index=True, verbose_name="Öğrenci mi?")
    

    department = models.CharField(
        max_length=50, 
        choices=DEPARTMENT_CHOICES, 
        null=True, 
        blank=True, 
        db_index=True,
        verbose_name="Bölüm"
    )
    category = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        db_index=True,
        verbose_name="Kategori"
    )
    total_points = models.PositiveIntegerField(default=0, db_index=True, verbose_name="Toplam Puan")
    
    is_staff = models.BooleanField(default=False)
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']


    def __str__(self):
        return f"{self.get_full_name()} ({self.email})"

    class Meta:
        verbose_name = "Kullanıcı"
        verbose_name_plural = "Kullanıcılar"
        indexes = [
            models.Index(fields=['department', 'is_student']),
            models.Index(fields=['is_student', '-total_points']),
            models.Index(fields=['department', 'is_student', '-total_points']),
        ]


class EmailOTP(models.Model):
    """
    Kayıt öncesi mail doğrulaması için geçici kodları tutan tablo.
    """
    email = models.EmailField(unique=True, verbose_name="E-posta")
    code = models.CharField(max_length=6, verbose_name="Doğrulama Kodu")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Oluşturulma Tarihi")

    def __str__(self):
        return f"{self.email} - {self.code}"

    class Meta:
        verbose_name = "E-posta Doğrulama Kodu"
        verbose_name_plural = "E-posta Doğrulama Kodları"