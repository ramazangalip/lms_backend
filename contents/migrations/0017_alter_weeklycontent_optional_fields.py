from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('contents', '0016_weeklycontent_due_date'),
    ]

    operations = [
        migrations.AlterField(
            model_name='weeklycontent',
            name='title',
            field=models.CharField(blank=True, max_length=200, null=True, verbose_name='Hafta Başlığı'),
        ),
        migrations.AlterField(
            model_name='weeklycontent',
            name='description',
            field=models.TextField(blank=True, null=True, verbose_name='Ders Notları'),
        ),
        migrations.AlterField(
            model_name='weeklycontent',
            name='intro_title',
            field=models.CharField(blank=True, default='Genel Tanıtım', max_length=255, null=True, verbose_name='Tanıtım Başlığı'),
        ),
        migrations.AlterField(
            model_name='material',
            name='content_type',
            field=models.CharField(blank=True, choices=[('video', 'Video'), ('podcast', 'Podcast'), ('form', 'Bilgi Testi'), ('pdf', 'Ders Notu (PDF)'), ('assignment', 'Ödev (Microsoft Form)')], max_length=10, null=True),
        ),
        migrations.AlterField(
            model_name='material',
            name='embed_url',
            field=models.URLField(blank=True, help_text='Video/Podcast embed kodu veya OneDrive PDF indirme linki.', null=True, verbose_name='Materyal Linki'),
        ),
        migrations.AlterField(
            model_name='material',
            name='title',
            field=models.CharField(blank=True, max_length=200, null=True, verbose_name='Materyal Başlığı'),
        ),
        migrations.AlterField(
            model_name='material',
            name='point_value',
            field=models.PositiveIntegerField(blank=True, default=1, null=True, verbose_name='Tamamlama Puanı'),
        ),
    ]
