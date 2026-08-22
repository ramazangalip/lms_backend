import os
import sys
import threading
import time
import logging
from django.apps import AppConfig

logger = logging.getLogger(__name__)

def start_academic_email_scheduler():
    def run_scheduler():
        # Django başlatıldıktan sonra ilk 10 saniye bekle
        time.sleep(10)
        logger.info("[Scheduler] Akademisyen e-posta otomatik zamanlayıcısı aktif edildi.")
        
        while True:
            try:
                from django.core.management import call_command
                call_command('send_academic_reports')
            except Exception as e:
                logger.error(f"[Scheduler Error] Otomatik e-posta zamanlayıcı hatası: {e}")
            
            # Her 15 dakikada bir (900 saniye) otomatik kontrol et
            time.sleep(900)

    thread = threading.Thread(target=run_scheduler, daemon=True, name="AcademicEmailSchedulerThread")
    thread.start()


class ContentsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'contents'

    def ready(self):
        # Sadece ana sunucu sürecinde çalıştır (Geliştirme sunucusundaki çift başlatmayı engellemek için)
        if os.environ.get('RUN_MAIN') == 'true' or 'manage.py' not in sys.argv:
            if not getattr(self, '_scheduler_started', False):
                self._scheduler_started = True
                start_academic_email_scheduler()
