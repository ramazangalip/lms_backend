import os
import logging
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.contrib.auth import get_user_model
from django.utils import timezone
from contents.models import (
    WeeklyContent,
    TimeTracking,
    StudentQuizAttempt,
    StudentSurveyResponse,
    StudentProgress,
    AcademicEmailLog
)

logger = logging.getLogger(__name__)
User = get_user_model()

DEPARTMENT_NAMES = {
    'cocukgelisimi': 'Çocuk Gelişimi',
    'diyaliz': 'Diyaliz',
    'disprotezteknolojisi': 'Diş Protez Teknolojisi',
    'eczanehizmetleri': 'Eczane Hizmetleri',
    'fizyoterapi': 'Fizyoterapi',
}

def format_seconds(seconds):
    """Saniyeyi Saat/Dakika biçimine çevirir."""
    if not seconds or seconds <= 0:
        return "0 dk"
    mins = int(seconds // 60)
    hrs = int(mins // 60)
    remaining_mins = mins % 60
    if hrs > 0:
        return f"{hrs} sa {remaining_mins} dk"
    return f"{mins} dk"

def generate_department_weekly_analytics(department, week_number):
    """
    Belirli bir bölüm ve hafta için N+1 sorgusu olmadan yüksek performansla
    tüm öğrenci analitiklerini (T1/T2 süreleri, tahmin/gerçek skor, anketler vb.) toplar.
    """
    dept_label = DEPARTMENT_NAMES.get(department, str(department).upper())
    
    # 1. Bölümdeki öğrencileri çek
    students = User.objects.filter(
        department=department,
        is_staff=False,
        is_teacher=False
    ).order_by('first_name', 'last_name')
    
    student_ids = list(students.values_list('id', flat=True))
    
    # 2. İlgili haftanın içerik nesnesini prefetch ile al
    week_content = WeeklyContent.objects.filter(week_number=week_number).prefetch_related('materials').first()
    
    if not week_content or not student_ids:
        return {
            "department": department,
            "department_label": dept_label,
            "week_number": week_number,
            "week_title": week_content.title if week_content else f"{week_number}. Hafta",
            "student_count": len(student_ids),
            "students_data": [],
            "materials": []
        }

    materials = list(week_content.materials.all())
    
    # 3. TOPLU VERİ ÇEKİMİ (Sıfır N+1 Sorgu Garantisi)
    all_times = list(
        TimeTracking.objects.filter(
            student_id__in=student_ids,
            weekly_content=week_content
        ).select_related('material')
    )
    
    all_attempts = list(
        StudentQuizAttempt.objects.filter(
            student_id__in=student_ids,
            quiz__material__parent_content=week_content
        ).order_by('-completed_at')
    )
    
    all_surveys = list(
        StudentSurveyResponse.objects.filter(
            student_id__in=student_ids,
            question__survey__week_number=week_number
        ).select_related('question')
    )
    
    all_progress = list(
        StudentProgress.objects.filter(
            student_id__in=student_ids,
            weekly_content=week_content
        )
    )

    # 4. Bellek içi öğrenci bazlı veri paketleme
    students_data = []

    for student in students:
        s_id = student.id
        s_times = [t for t in all_times if t.student_id == s_id]
        s_attempts = [a for a in all_attempts if a.student_id == s_id]
        s_surveys = [srv for srv in all_surveys if srv.student_id == s_id]
        s_prog = next((p for p in all_progress if p.student_id == s_id), None)

        # Materyal Bazlı Tur 1 (T1) ve Tur 2 (T2) Süreleri
        materials_breakdown = []
        total_t1 = 0
        total_t2 = 0

        for m in materials:
            t1_sec = sum(t.duration_seconds for t in s_times if t.material_id == m.id and t.attempt_round == 1)
            t2_sec = sum(t.duration_seconds for t in s_times if t.material_id == m.id and t.attempt_round == 2)
            total_sec = t1_sec + t2_sec
            
            total_t1 += t1_sec
            total_t2 += t2_sec

            materials_breakdown.append({
                "title": m.title,
                "type": m.content_type,
                "t1_sec": t1_sec,
                "t1_str": format_seconds(t1_sec),
                "t2_sec": t2_sec,
                "t2_str": format_seconds(t2_sec),
                "total_sec": total_sec,
                "total_str": format_seconds(total_sec)
            })

        overall_time_sec = total_t1 + total_t2

        # Sınav Performansı & Kalibrasyon (1. Tur ve 2. Tur)
        att_r1 = next((a for a in s_attempts if a.attempt_round == 1), None)
        att_r2 = next((a for a in s_attempts if a.attempt_round == 2), None)

        quiz_info = {
            "has_quiz": True if (att_r1 or att_r2) else False,
            "r1": {
                "score": att_r1.score if att_r1 else None,
                "predicted": att_r1.predicted_score if att_r1 else None,
                "gap": att_r1.calibration_gap if att_r1 else None,
                "correct": att_r1.correct_answers if att_r1 else 0,
                "wrong": att_r1.wrong_answers if att_r1 else 0,
            },
            "r2": {
                "score": att_r2.score if att_r2 else None,
                "predicted": att_r2.predicted_score if att_r2 else None,
                "gap": att_r2.calibration_gap if att_r2 else None,
                "correct": att_r2.correct_answers if att_r2 else 0,
                "wrong": att_r2.wrong_answers if att_r2 else 0,
            }
        }

        # Anket Cevapları
        survey_answers = []
        for srv in s_surveys:
            survey_answers.append({
                "question": srv.question.text,
                "category": srv.question.category or "Genel",
                "answer_text": srv.answer_text or f"{srv.answer_value} Puan",
                "value": srv.answer_value
            })

        students_data.append({
            "id": student.id,
            "full_name": f"{student.first_name} {student.last_name}".strip().upper() or student.username,
            "email": student.email,
            "total_points": getattr(student, 'total_points', 0),
            "progress_percentage": s_prog.completion_percentage if s_prog else 0,
            "is_completed": s_prog.is_completed if s_prog else False,
            "total_t1_str": format_seconds(total_t1),
            "total_t2_str": format_seconds(total_t2),
            "overall_time_str": format_seconds(overall_time_sec),
            "materials_breakdown": materials_breakdown,
            "quiz_info": quiz_info,
            "survey_answers": survey_answers
        })

    return {
        "department": department,
        "department_label": dept_label,
        "week_number": week_number,
        "week_title": week_content.title or f"{week_number}. Hafta",
        "student_count": len(students),
        "students_data": students_data
    }


def build_academic_report_html(report_data):
    """
    Akademisyen için temiz, modern ve mobil uyumlu HTML e-posta şablonu üretir.
    """
    dept_label = report_data['department_label']
    week_num = report_data['week_number']
    week_title = report_data['week_title']
    student_count = report_data['student_count']
    students_data = report_data['students_data']

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f4f5f8; margin: 0; padding: 20px; color: #333; }}
            .container {{ max-width: 800px; margin: 0 auto; background: #ffffff; border-radius: 16px; overflow: hidden; box-shadow: 0 10px 25px rgba(0,0,0,0.08); border: 1px solid #e5e7eb; }}
            .header {{ background: linear-gradient(135deg, #43186c 0%, #1e1b4b 100%); padding: 32px; color: #ffffff; text-align: left; }}
            .header h1 {{ margin: 0; font-size: 22px; font-weight: 900; letter-spacing: -0.5px; text-transform: uppercase; }}
            .header p {{ margin: 6px 0 0 0; color: #c7d2fe; font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: 1px; }}
            .stats-bar {{ background: #f8fafc; border-bottom: 1px solid #e2e8f0; padding: 16px 32px; display: flex; justify-content: space-between; font-size: 12px; font-weight: 700; color: #475569; }}
            .content {{ padding: 32px; }}
            .student-card {{ background: #ffffff; border: 1px solid #e2e8f0; border-radius: 12px; margin-bottom: 24px; padding: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.02); }}
            .student-header {{ display: flex; justify-content: space-between; align-items: center; border-bottom: 2px solid #f1f5f9; padding-bottom: 12px; margin-bottom: 16px; }}
            .student-name {{ font-size: 16px; font-weight: 800; color: #1e1b4b; margin: 0; }}
            .badge {{ display: inline-block; padding: 4px 10px; border-radius: 20px; font-size: 10px; font-weight: 800; text-transform: uppercase; }}
            .badge-purple {{ background: #f3e8ff; color: #6b21a8; }}
            .badge-green {{ background: #dcfce7; color: #15803d; }}
            .badge-amber {{ background: #fef3c7; color: #b45309; }}
            .metrics-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 16px; }}
            .metric-box {{ background: #f8fafc; border: 1px solid #f1f5f9; padding: 12px; border-radius: 8px; font-size: 11px; }}
            .metric-title {{ color: #64748b; font-weight: 700; text-transform: uppercase; font-size: 9px; letter-spacing: 0.5px; margin-bottom: 4px; }}
            .metric-value {{ font-size: 13px; font-weight: 800; color: #0f172a; }}
            table {{ width: 100%; border-collapse: collapse; margin-top: 12px; font-size: 11px; }}
            th {{ background: #f1f5f9; color: #334155; text-align: left; padding: 8px 10px; font-weight: 800; text-transform: uppercase; font-size: 9px; border-radius: 4px; }}
            td {{ padding: 8px 10px; border-bottom: 1px solid #f1f5f9; color: #334155; font-weight: 600; }}
            .footer {{ background: #f8fafc; padding: 20px; text-align: center; font-size: 11px; color: #94a3b8; border-top: 1px solid #e2e8f0; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>{dept_label} — {week_num}. Hafta Raporu</h1>
                <p>Bingöl LMS Akademik Öğrenci Analitiği & Performans Çizelgesi</p>
            </div>
            
            <div class="stats-bar">
                <span>Raporlanan Hafta: <strong>{week_title}</strong></span>
                <span>Öğrenci Sayısı: <strong>{student_count} Öğrenci</strong></span>
                <span>Tarih: <strong>{timezone.now().strftime('%d.%m.%Y')}</strong></span>
            </div>

            <div class="content">
    """

    if not students_data:
        html += "<p style='text-align:center; color:#94a3b8; padding:40px;'>Bu bölümde kayıtlı öğrenci veya haftalık veri bulunamadı.</p>"
    else:
        for idx, s in enumerate(students_data, 1):
            q_info = s['quiz_info']
            r1 = q_info['r1']
            r2 = q_info['r2']

            # Sınav skoru ve kalibrasyon stringi hazırlama
            quiz_str_r1 = "Çözülmedi"
            if r1['score'] is not None:
                pred = f"%{int(r1['predicted'])}" if r1['predicted'] is not None else "Yok"
                gap = f"±{r1['gap']}" if r1['gap'] is not None else "-"
                quiz_str_r1 = f"Gerçek: %{int(r1['score'])} | Ön Tahmin: {pred} (Sapma: {gap}) [{r1['correct']}D / {r1['wrong']}Y]"

            quiz_str_r2 = "2. Tur Yok"
            if r2['score'] is not None:
                pred2 = f"%{int(r2['predicted'])}" if r2['predicted'] is not None else "Yok"
                gap2 = f"±{r2['gap']}" if r2['gap'] is not None else "-"
                quiz_str_r2 = f"Gerçek: %{int(r2['score'])} | Ön Tahmin: {pred2} (Sapma: {gap2}) [{r2['correct']}D / {r2['wrong']}Y]"

            html += f"""
                <div class="student-card">
                    <div class="student-header">
                        <div>
                            <span style="font-size:10px; color:#94a3b8; font-weight:800;">#{idx}</span>
                            <span class="student-name" style="margin-left:6px;">{s['full_name']}</span>
                        </div>
                        <div>
                            <span class="badge badge-purple">{s['total_points']} Puan</span>
                            <span class="badge {'badge-green' if s['is_completed'] else 'badge-amber'}" style="margin-left:4px;">
                                %{int(s['progress_percentage'])} İlerleme
                            </span>
                        </div>
                    </div>

                    <div class="metrics-grid">
                        <div class="metric-box">
                            <div class="metric-title">Materyal Çalışma Süresi (Tur 1 / Tur 2)</div>
                            <div class="metric-value">
                                T1: {s['total_t1_str']} | T2: {s['total_t2_str']} 
                                <span style="font-size:10px; color:#64748b; font-weight:normal;">(Toplam: {s['overall_time_str']})</span>
                            </div>
                        </div>
                        <div class="metric-box">
                            <div class="metric-title">1. Tur Sınav & Kalibrasyon</div>
                            <div class="metric-value" style="font-size:11px;">{quiz_str_r1}</div>
                        </div>
                    </div>
            """

            if r2['score'] is not None:
                html += f"""
                    <div class="metric-box" style="margin-bottom:16px;">
                        <div class="metric-title">2. Tur (Pekiştirme) Sınavı & Kalibrasyon</div>
                        <div class="metric-value" style="font-size:11px; color:#059669;">{quiz_str_r2}</div>
                    </div>
                """

            # Materyal Bazlı Detay Tablosu
            if s['materials_breakdown']:
                html += """
                    <table>
                        <thead>
                            <tr>
                                <th>Materyal Başlığı</th>
                                <th>Tür</th>
                                <th>Tur 1 (T1) Süre</th>
                                <th>Tur 2 (T2) Süre</th>
                                <th>Toplam Süre</th>
                            </tr>
                        </thead>
                        <tbody>
                """
                for m in s['materials_breakdown']:
                    html += f"""
                        <tr>
                            <td>{m['title']}</td>
                            <td style="text-transform:uppercase; font-size:9px; color:#64748b;">{m['type']}</td>
                            <td>{m['t1_str']}</td>
                            <td>{m['t2_str']}</td>
                            <td><strong>{m['total_str']}</strong></td>
                        </tr>
                    """
                html += "</tbody></table>"

            # Anket Cevapları Tablosu
            if s['survey_answers']:
                html += """
                    <div style="margin-top:14px; font-weight:800; font-size:10px; color:#475569; text-transform:uppercase;">Haftalık Anket Yanıtları</div>
                    <table>
                        <thead>
                            <tr>
                                <th>Soru Maddesi</th>
                                <th>Kategori</th>
                                <th>Ölçek Yanıtı</th>
                            </tr>
                        </thead>
                        <tbody>
                """
                for srv in s['survey_answers']:
                    html += f"""
                        <tr>
                            <td>{srv['question']}</td>
                            <td>{srv['category']}</td>
                            <td><strong style="color:#6b21a8;">{srv['answer_text']}</strong></td>
                        </tr>
                    """
                html += "</tbody></table>"

            html += "</div>" # student-card sonu

    html += f"""
            </div>
            <div class="footer">
                Bu e-posta Bingöl Öğrenme Yönetim Sistemi (BÜ-LMS) tarafından otomatik olarak üretilmiştir.<br>
                © {timezone.now().year} Bingöl Üniversitesi. Tüm hakları saklıdır.
            </div>
        </div>
    </body>
    </html>
    """
    return html


def build_academic_report_text(report_data):
    """Plain text e-posta fallback metni üretir."""
    dept_label = report_data['department_label']
    week_num = report_data['week_number']
    week_title = report_data['week_title']
    students_data = report_data['students_data']

    text = f"--- {dept_label.upper()} {week_num}. HAFTA ÖĞRENCİ ANALİTİK RAPORU ---\n"
    text += f"Hafta: {week_title}\n"
    text += f"Tarih: {timezone.now().strftime('%d.%m.%Y %H:%M')}\n\n"

    for idx, s in enumerate(students_data, 1):
        text += f"{idx}. {s['full_name']} (Puan: {s['total_points']} | İlerleme: %{int(s['progress_percentage'])})\n"
        text += f"   • Süre: Tur 1={s['total_t1_str']}, Tur 2={s['total_t2_str']}, Toplam={s['overall_time_str']}\n"
        
        q1 = s['quiz_info']['r1']
        if q1['score'] is not None:
            text += f"   • 1. Tur Sınav: Gerçek=%{int(q1['score'])}, Ön Tahmin=%{q1['predicted']}, Sapma={q1['gap']} ({q1['correct']}D / {q1['wrong']}Y)\n"
        
        q2 = s['quiz_info']['r2']
        if q2['score'] is not None:
            text += f"   • 2. Tur Sınav: Gerçek=%{int(q2['score'])}, Ön Tahmin=%{q2['predicted']}, Sapma={q2['gap']} ({q2['correct']}D / {q2['wrong']}Y)\n"

        text += "\n"

    return text


def send_department_academic_report(department, week_number, force=False):
    """
    Belirtilen bölüm ve hafta için raporu hazırlar ve akademisyenlere e-posta atar.
    Mükerrer gönderimi engellemek için AcademicEmailLog tablosuna kaydeder.
    """
    # 1. Mükerrer Gönderim Kontrolü
    if not force:
        already_sent = AcademicEmailLog.objects.filter(department=department, week_number=week_number, status="SUCCESS").exists()
        if already_sent:
            logger.info(f"Rapor zaten gönderilmiş: {department} - Hafta {week_number}")
            return False, "Bu haftanın raporu daha önce gönderilmiştir."

    # 2. Alıcı Akademisyenlerin Maillerini Çek
    recipients = list(
        User.objects.filter(is_teacher=True, department=department)
        .values_list('email', flat=True)
    )

    # Eğer o bölüme atanmış spesifik hoca yoksa tüm aktif akademisyenlere / adminlere gönder
    if not recipients:
        recipients = list(
            User.objects.filter(is_teacher=True)
            .values_list('email', flat=True)
        )

    if not recipients:
        recipients = [settings.EMAIL_HOST_USER]

    # Unique mail adresleri
    recipients = list(set(r for r in recipients if r and "@" in r))

    # 3. Analiz Verilerini Topla
    report_data = generate_department_weekly_analytics(department, week_number)
    dept_label = report_data['department_label']
    student_count = report_data['student_count']

    # 4. E-posta İçeriğini Üret
    subject = f"📊 [BÜ-LMS] {dept_label} — {week_number}. Hafta Öğrenci Gelişim ve Performans Raporu"
    html_content = build_academic_report_html(report_data)
    text_content = build_academic_report_text(report_data)

    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', settings.EMAIL_HOST_USER)

    try:
        msg = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=from_email,
            to=recipients
        )
        msg.attach_alternative(html_content, "text/html")
        msg.send(fail_silently=False)

        # 5. Başarılı Gönderim Logu
        AcademicEmailLog.objects.update_or_create(
            department=department,
            week_number=week_number,
            defaults={
                'recipients': ", ".join(recipients),
                'student_count': student_count,
                'status': 'SUCCESS',
                'error_message': None
            }
        )
        logger.info(f"Başarıyla e-posta raporu gönderildi: {department} Hafta {week_number} -> {recipients}")
        return True, f"Rapor {len(recipients)} akademisyene başarıyla iletildi."

    except Exception as e:
        err_msg = str(e)
        logger.error(f"E-posta raporu gönderim hatası ({department} Hafta {week_number}): {err_msg}")
        AcademicEmailLog.objects.update_or_create(
            department=department,
            week_number=week_number,
            defaults={
                'recipients': ", ".join(recipients),
                'student_count': student_count,
                'status': 'FAILED',
                'error_message': err_msg
            }
        )
        return False, f"E-posta gönderim hatası: {err_msg}"
