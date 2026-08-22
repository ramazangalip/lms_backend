import sys
from datetime import datetime, time, timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from contents.models import WeeklyContentSchedule, WeeklyContent
from contents.services.email_report_service import send_department_academic_report, DEPARTMENT_NAMES

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

class Command(BaseCommand):
    help = "Hafta aktif etme tarihlerini kontrol eder. Aktif etme tarihinden 1 gün önce saat 20:00'da ilgili bölümün 1 önceki haftalık öğrenci analitik raporunu akademisyenlere e-posta atar."

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Log kontrolünü atla ve raporu zorla gönder.',
        )
        parser.add_argument(
            '--department',
            type=str,
            help='Sadece belirli bir bölüm kodu için çalıştır (ör: cocukgelisimi)',
        )
        parser.add_argument(
            '--week',
            type=int,
            help='Sadece belirli bir hafta raporu için çalıştır (ör: 1)',
        )

    def handle(self, *args, **options):
        force = options['force']
        target_dept = options['department']
        target_week = options['week']

        now = timezone.now()
        self.stdout.write(self.style.SUCCESS(f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] Akademisyen e-posta rapor kontrolü başlatıldı..."))

        # Eğer manuel bölüm ve hafta girilmişse direkt çalıştır
        if target_dept and target_week:
            self.stdout.write(self.style.WARNING(f"Manuel Tetikleme: Bölüm={target_dept}, Hafta={target_week}"))
            success, msg = send_department_academic_report(target_dept, target_week, force=force)
            if success:
                self.stdout.write(self.style.SUCCESS(f"BAŞARILI: {msg}"))
            else:
                self.stdout.write(self.style.ERROR(f"HATA / BİLGİ: {msg}"))
            return

        # Otomatik Zamanlayıcı Kontrolü
        # Her bölüm için tüm haftalık takvimleri çek (W >= 2)
        schedules = WeeklyContentSchedule.objects.select_related('weekly_content').filter(
            weekly_content__week_number__gte=2,
            release_date__isnull=False
        )

        sent_count = 0
        skipped_count = 0

        for sched in schedules:
            dept = sched.department
            w_next = sched.weekly_content.week_number
            report_week = w_next - 1  # 2. Hafta açılıyorsa 1. Haftanın raporu gidecek
            rel_date = sched.release_date

            # Gelecek haftanın açılış tarihinden 1 gün önceki saat 20:00 hesabı
            release_dt_local = timezone.localtime(rel_date)
            target_date = release_dt_local.date() - timedelta(days=1)
            
            # Target Trigger DateTime: 1 gün önce saat 20:00:00
            trigger_dt = timezone.make_aware(
                datetime.combine(target_date, time(20, 0, 0)),
                timezone.get_current_timezone()
            )

            # Zaman kontrolü: Şu anki zaman trigger_dt'yi geçmiş mi?
            if now >= trigger_dt or force:
                self.stdout.write(self.style.MIGRATE_HEADING(
                    f"Kontrol Ediliyor: Bölüm={dept}, Rapor Haftası={report_week} (Gelecek Hafta {w_next} Açılış: {release_dt_local.strftime('%d.%m.%Y %H:%M')}, Tetikleme Saat: {trigger_dt.strftime('%d.%m.%Y %H:%M')})"
                ))

                success, msg = send_department_academic_report(dept, report_week, force=force)
                if success:
                    sent_count += 1
                    self.stdout.write(self.style.SUCCESS(f"  └─ BAŞARILI: {msg}"))
                else:
                    skipped_count += 1
                    self.stdout.write(self.style.NOTICE(f"  └─ {msg}"))
            else:
                skipped_count += 1
                self.stdout.write(f"Zamanı Gelmedi: Bölüm={dept}, Hafta={report_week} (Zamanı: {trigger_dt.strftime('%d.%m.%Y %H:%M')})")

        self.stdout.write(self.style.SUCCESS(f"İşlem Tamamlandı. Gönderilen: {sent_count}, Atlanan/Bekleyen: {skipped_count}"))
