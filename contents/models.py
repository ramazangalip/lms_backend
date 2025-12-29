from django.db import models

class WeeklyContent(models.Model):
    """
    Her eğitim haftasını temsil eden ana model.
    Tüm bölümler için ortaktır.
    """
    week_number = models.IntegerField(unique=True, verbose_name="Hafta")
    title = models.CharField(max_length=200, verbose_name="Hafta Başlığı")
    description = models.TextField(blank=True, verbose_name="Ders Notları")

    class Meta:
        verbose_name = "Haftalık İçerik"
        verbose_name_plural = "Haftalık İçerikler"
        ordering = ['week_number']

    def __str__(self):
        return f"Hafta {self.week_number} - {self.title}"

class Material(models.Model):
    """
    Bir haftalık içeriğe bağlı materyalleri (Video/Podcast/Form) tutar.
    """
    CONTENT_TYPES = (
        ('video', 'Video'),
        ('podcast', 'Podcast'),
        ('form', 'Google Form'), # Google Form seçeneği eklendi
    )
    parent_content = models.ForeignKey(
        WeeklyContent, 
        related_name='materials', 
        on_delete=models.CASCADE
    )
    content_type = models.CharField(max_length=10, choices=CONTENT_TYPES)
    # Alan adı genel bir amaca hizmet ettiği için açıklamasını güncelledik
    embed_url = models.URLField(verbose_name="Materyal Linki (YouTube/Form Embed URL)")
    title = models.CharField(max_length=200, verbose_name="Materyal Başlığı")

    def __str__(self):
        return f"{self.get_content_type_display()} - {self.title} (Hafta {self.parent_content.week_number})"