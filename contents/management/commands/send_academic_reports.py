import sys
from datetime import datetime, time, timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.contrib.auth import get_user_model
from contents.models import WeeklyContentSchedule, WeeklyContent
from contents.services.email_report_service import send_department_academic_report, DEPARTMENT_NAMES

User = get_user_model()

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
        # 1. Sistemdeki tüm bölümleri dinamik tespit et (User model choices + DB'deki aktif tüm bölümler)
        db_departments = set(User.objects.exclude(department__isnull=True).exclude(department='').values_list('department', flat=True))
        choice_departments = set(dict(getattr(User, 'DEPARTMENT_CHOICES', [])).keys())
        all_departments = sorted(list(db_departments.union(choice_departments)))

        # 2. Tüm 2 ve üzeri haftalık içerikleri çek (W >= 2)
        weekly_contents = WeeklyContent.objects.filter(week_number__gte=2)

        # 3. Bölüm bazlı özel takvimleri haritalandır (N+1 engellemek için)
        custom_schedules = {
            (s.department, s.weekly_content.week_number): s.release_date
            for s in WeeklyContentSchedule.objects.filter(release_date__isnull=False).select_related('weekly_content')
        }

        sent_count = 0
        skipped_count = 0

        self.stdout.write(f"Sistemdeki {len(all_departments)} bölüm için tarih kontrolleri yapılıyor: {', '.join(all_departments)}")

        for dept in all_departments:
            for wc in weekly_contents:
                w_next = wc.week_number
                report_week = w_next - 1

                # Bölüme özel tarih varsa onu al, yoksa haftanın genel aktifleşme tarihini al
                rel_date = custom_schedules.get((dept, w_next)) or wc.release_date

                if not rel_date:
                    continue

                # Gelecek haftanın açılış tarihinden 1 gün önceki saat 20:00 hesabı
                release_dt_local = timezone.localtime(rel_date)
                target_date = release_dt_local.date() - timedelta(days=1)
                
                trigger_dt = timezone.make_aware(
                    datetime.combine(target_date, time(20, 0, 0)),
                    timezone.get_current_timezone()
                )

                # Zaman kontrolü: Şu anki zaman trigger_dt'yi geçmiş mi?
                if now >= trigger_dt or force:
                    success, msg = send_department_academic_report(dept, report_week, force=force)
                    if success:
                        sent_count += 1
                        self.stdout.write(self.style.SUCCESS(f"  [BAŞARILI] Bölüm={dept}, Rapor Haftası={report_week}: {msg}"))
                    else:
                        skipped_count += 1
                        self.stdout.write(self.style.NOTICE(f"  [BİLGİ] Bölüm={dept}, Rapor Haftası={report_week}: {msg}"))
                else:
                    skipped_count += 1

        self.stdout.write(self.style.SUCCESS(f"İşlem Tamamlandı. Gönderilen: {sent_count}, Atlanan/Bekleyen: {skipped_count}"))
