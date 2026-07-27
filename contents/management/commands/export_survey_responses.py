from django.core.management.base import BaseCommand
from contents.excel_generator import generate_survey_excel

class Command(BaseCommand):
    help = 'Belirtilen haftaya ait anket cevaplarını bölüm ve öğrenci bazlı Excel formatında dışa aktarır.'

    def add_arguments(self, parser):
        parser.add_argument(
            'week_number', 
            type=int, 
            nargs='?', 
            default=4, 
            help='Dışa aktarılacak anketin hafta numarası (Varsayılan: 4)'
        )

    def handle(self, *args, **options):
        week_number = options['week_number']
        self.stdout.write(self.style.NOTICE(f"{week_number}. hafta anketi için Excel oluşturuluyor..."))
        
        try:
            wb = generate_survey_excel(week_number)
            file_name = f"survey_hafta_{week_number}_cevaplari.xlsx"
            wb.save(file_name)
            self.stdout.write(self.style.SUCCESS(f"Başarılı! Excel dosyası '{file_name}' adıyla kaydedildi."))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Hata oluştu: {str(e)}"))
