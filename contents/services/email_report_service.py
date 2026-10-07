import os
import io
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
    StudentQuestion,
    AcademicEmailLog
)

from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

logger = logging.getLogger(__name__)
User = get_user_model()

DEPARTMENT_NAMES = {
    'siyasetbilimi': 'Siyaset Bilimi ve Kamu Yönetimi',
    'turkdili': 'Türk Dili ve Edebiyatı',
    'matematik': 'Matematik',
    'sb': 'Siyaset Bilimi ve Kamu Yönetimi',
    'td': 'Türk Dili ve Edebiyatı',
    'mt': 'Matematik',
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

def fix_tr_pdf_chars(str_val):
    """ReportLab varsayılan font uyumluluğu için Türkçe karakter dönüştürücü."""
    if not str_val:
        return ""
    tr_map = {
        'ı': 'i', 'ğ': 'g', 'ü': 'u', 'ş': 's', 'ö': 'o', 'ç': 'c',
        'İ': 'I', 'Ğ': 'G', 'Ü': 'U', 'Ş': 'S', 'Ö': 'O', 'Ç': 'C'
    }
    res = str(str_val)
    for tr_c, latin_c in tr_map.items():
        res = res.replace(tr_c, latin_c)
    return res

def generate_department_weekly_analytics(department, week_number):
    """
    Belirli bir bölüm ve hafta için N+1 sorgusu olmadan yüksek performansla
    tüm öğrenci analitiklerini (T1/T2 süreleri, tahmin/gerçek skor, anketler, chatbot vb.) toplar.
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

    all_questions = list(
        StudentQuestion.objects.filter(
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
        s_questions = [q for q in all_questions if q.student_id == s_id]

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

        # Chatbot Yanıtları / Soruları
        chatbot_questions = []
        for q in s_questions:
            chatbot_questions.append({
                "text": q.question_text,
                "created_at": q.created_at.strftime('%d.%m.%Y %H:%M') if q.created_at else "-"
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
            "survey_answers": survey_answers,
            "chatbot_questions": chatbot_questions
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
                <div style="background:#eff6ff; border:1px solid #bfdbfe; color:#1e40af; padding:12px 16px; border-radius:8px; font-size:12px; margin-bottom:20px; font-weight:600;">
                    📎 Bu e-postanın ekinde <strong>3 Adet Detaylı PDF Raporu</strong> yer almaktadır:<br>
                    1. <strong>Genel Öğrenci Performansı PDF</strong> (Materyal Süreleri, Sınav & Kalibrasyon)<br>
                    2. <strong>Haftalık Anket Yanıtları PDF</strong> (Ölçek Yanıtları ve Detaylar)<br>
                    3. <strong>Chatbot & Yapay Zeka Etkileşim PDF</strong> (Soru ve Etkileşim Analitiği)
                </div>
    """

    if not students_data:
        html += "<p style='text-align:center; color:#94a3b8; padding:40px;'>Bu bölümde kayıtlı öğrenci veya haftalık veri bulunamadı.</p>"
    else:
        for idx, s in enumerate(students_data, 1):
            q_info = s['quiz_info']
            r1 = q_info['r1']
            r2 = q_info['r2']

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

            html += "</div>"

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
    text += f"E-posta ekinde 3 Adet PDF Raporu yer almaktadır.\n\n"

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


# --- 3 ADET AYRI PDF JENERATÖRÜ ---

def get_report_styles():
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=15,
        leading=18,
        textColor=colors.HexColor('#43186C')
    )
    subtitle_style = ParagraphStyle(
        'DocSubTitle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=10,
        leading=13,
        textColor=colors.HexColor('#64748B')
    )
    section_header_style = ParagraphStyle(
        'SectionHeader',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=11,
        leading=14,
        textColor=colors.HexColor('#1E1B4B')
    )
    body_style = ParagraphStyle(
        'Body',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor('#334155')
    )
    bold_body_style = ParagraphStyle(
        'BoldBody',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor('#1E1B4B')
    )
    return title_style, subtitle_style, section_header_style, body_style, bold_body_style


def generate_general_performance_pdf(report_data):
    """
    PDF 1: Genel Öğrenci Performans, Materyal Süreleri ve Sınav Kalibrasyonu Raporu
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    title_style, subtitle_style, section_header_style, body_style, bold_body_style = get_report_styles()

    elements = []
    dept_label = fix_tr_pdf_chars(report_data['department_label'])
    week_num = report_data['week_number']
    week_title = fix_tr_pdf_chars(report_data['week_title'])
    student_count = report_data['student_count']
    students_data = report_data['students_data']

    # Header
    elements.append(Paragraph(f"BINGOL UNIVERSITESI LMS — {dept_label.upper()}", title_style))
    elements.append(Paragraph(f"PDF 1: {week_num}. Hafta Genel Ogrenci Performans ve Izleme Raporu", subtitle_style))
    elements.append(Spacer(1, 8))
    elements.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor('#43186C'), spaceAfter=12))

    # Meta Table
    meta_data = [[
        Paragraph(f"<b>Bolum:</b> {dept_label}", body_style),
        Paragraph(f"<b>Raporlanan Hafta:</b> {week_title}", body_style),
        Paragraph(f"<b>Ogrenci Sayisi:</b> {student_count}", body_style)
    ]]
    meta_table = Table(meta_data, colWidths=[180, 200, 150])
    meta_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F8FAFC')),
        ('PADDING', (0, 0), (-1, -1), 6),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#E2E8F0')),
    ]))
    elements.append(meta_table)
    elements.append(Spacer(1, 12))

    if not students_data:
        elements.append(Paragraph("Bu bolumde kayitli ogrenci verisi bulunamadi.", body_style))
    else:
        for idx, s in enumerate(students_data, 1):
            s_name = fix_tr_pdf_chars(s['full_name'])
            prog = int(s['progress_percentage'])
            pts = s['total_points']
            
            s_header_data = [[
                Paragraph(f"<b>#{idx} {s_name}</b>", section_header_style),
                Paragraph(f"<b>Ilerleme:</b> %{prog} | <b>Puan:</b> {pts}", bold_body_style)
            ]]
            s_header_table = Table(s_header_data, colWidths=[350, 180])
            s_header_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F3E8FF')),
                ('PADDING', (0, 0), (-1, -1), 5),
            ]))
            elements.append(s_header_table)
            elements.append(Spacer(1, 4))

            q_info = s['quiz_info']
            r1 = q_info['r1']
            r2 = q_info['r2']

            r1_str = "Cozulmedi"
            if r1['score'] is not None:
                pred = f"%{int(r1['predicted'])}" if r1['predicted'] is not None else "Yok"
                gap = f"+/-{r1['gap']}" if r1['gap'] is not None else "-"
                r1_str = f"Gercek: %{int(r1['score'])} | On Tahmin: {pred} (Sapma: {gap}) [{r1['correct']}D / {r1['wrong']}Y]"

            r2_str = "2. Tur Yok"
            if r2['score'] is not None:
                pred2 = f"%{int(r2['predicted'])}" if r2['predicted'] is not None else "Yok"
                gap2 = f"+/-{r2['gap']}" if r2['gap'] is not None else "-"
                r2_str = f"Gercek: %{int(r2['score'])} | On Tahmin: {pred2} (Sapma: {gap2}) [{r2['correct']}D / {r2['wrong']}Y]"

            metrics_data = [[
                Paragraph(f"<b>Materyal Calisma Suresi:</b><br/>T1: {s['total_t1_str']} | T2: {s['total_t2_str']} (Toplam: {s['overall_time_str']})", body_style),
                Paragraph(f"<b>1. Tur Sinav & Kalibrasyon:</b><br/>{fix_tr_pdf_chars(r1_str)}", body_style)
            ]]
            if r2['score'] is not None:
                metrics_data.append([
                    Paragraph(f"<b>2. Tur (Pekistirme) Sinavi:</b><br/>{fix_tr_pdf_chars(r2_str)}", body_style),
                    Paragraph("", body_style)
                ])

            metrics_table = Table(metrics_data, colWidths=[265, 265])
            metrics_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F8FAFC')),
                ('PADDING', (0, 0), (-1, -1), 5),
                ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#E2E8F0')),
            ]))
            elements.append(metrics_table)
            elements.append(Spacer(1, 4))

            if s['materials_breakdown']:
                mat_rows = [[
                    Paragraph("<b>Materyal Basligi</b>", bold_body_style),
                    Paragraph("<b>Tur</b>", bold_body_style),
                    Paragraph("<b>Tur 1 (T1)</b>", bold_body_style),
                    Paragraph("<b>Tur 2 (T2)</b>", bold_body_style),
                    Paragraph("<b>Toplam Sure</b>", bold_body_style)
                ]]
                for m in s['materials_breakdown']:
                    mat_rows.append([
                        Paragraph(fix_tr_pdf_chars(m['title']), body_style),
                        Paragraph(fix_tr_pdf_chars(m['type'].upper()), body_style),
                        Paragraph(m['t1_str'], body_style),
                        Paragraph(m['t2_str'], body_style),
                        Paragraph(f"<b>{m['total_str']}</b>", body_style)
                    ])

                mat_table = Table(mat_rows, colWidths=[210, 80, 80, 80, 80])
                mat_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#F1F5F9')),
                    ('PADDING', (0, 0), (-1, -1), 4),
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E2E8F0')),
                ]))
                elements.append(mat_table)

            elements.append(Spacer(1, 10))

    doc.build(elements)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes


def generate_survey_responses_pdf(report_data):
    """
    PDF 2: Haftalık Anket Yanıtları ve Ölçek Analizi Raporu
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    title_style, subtitle_style, section_header_style, body_style, bold_body_style = get_report_styles()

    elements = []
    dept_label = fix_tr_pdf_chars(report_data['department_label'])
    week_num = report_data['week_number']
    week_title = fix_tr_pdf_chars(report_data['week_title'])
    student_count = report_data['student_count']
    students_data = report_data['students_data']

    # Header
    elements.append(Paragraph(f"BINGOL UNIVERSITESI LMS — {dept_label.upper()}", title_style))
    elements.append(Paragraph(f"PDF 2: {week_num}. Hafta Anket Yanitlari ve Olcek Analiz Raporu", subtitle_style))
    elements.append(Spacer(1, 8))
    elements.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor('#0284C7'), spaceAfter=12))

    meta_data = [[
        Paragraph(f"<b>Bolum:</b> {dept_label}", body_style),
        Paragraph(f"<b>Anket Haftasi:</b> {week_title}", body_style),
        Paragraph(f"<b>Ogrenci Sayisi:</b> {student_count}", body_style)
    ]]
    meta_table = Table(meta_data, colWidths=[180, 200, 150])
    meta_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F0F9FF')),
        ('PADDING', (0, 0), (-1, -1), 6),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#BAE6FD')),
    ]))
    elements.append(meta_table)
    elements.append(Spacer(1, 12))

    has_any_survey = False
    for idx, s in enumerate(students_data, 1):
        if not s['survey_answers']:
            continue

        has_any_survey = True
        s_name = fix_tr_pdf_chars(s['full_name'])
        
        s_header_data = [[
            Paragraph(f"<b>#{idx} {s_name}</b>", section_header_style),
            Paragraph(f"<b>Yanitlanan Soru Sayisi:</b> {len(s['survey_answers'])}", bold_body_style)
        ]]
        s_header_table = Table(s_header_data, colWidths=[350, 180])
        s_header_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#E0F2FE')),
            ('PADDING', (0, 0), (-1, -1), 5),
        ]))
        elements.append(s_header_table)
        elements.append(Spacer(1, 4))

        srv_rows = [[
            Paragraph("<b>Anket Soru Maddesi</b>", bold_body_style),
            Paragraph("<b>Kategori / Alt Boyut</b>", bold_body_style),
            Paragraph("<b>Olcek Yaniti</b>", bold_body_style)
        ]]
        for srv in s['survey_answers']:
            srv_rows.append([
                Paragraph(fix_tr_pdf_chars(srv['question']), body_style),
                Paragraph(fix_tr_pdf_chars(srv['category']), body_style),
                Paragraph(f"<b>{fix_tr_pdf_chars(srv['answer_text'])}</b>", bold_body_style)
            ])

        srv_table = Table(srv_rows, colWidths=[300, 110, 120])
        srv_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#F1F5F9')),
            ('PADDING', (0, 0), (-1, -1), 4),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
        ]))
        elements.append(srv_table)
        elements.append(Spacer(1, 10))

    if not has_any_survey:
        elements.append(Paragraph("Bu haftaya ait doldurulmus anket yaniti bulunamadi.", body_style))

    doc.build(elements)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes


def generate_chatbot_analytics_pdf(report_data):
    """
    PDF 3: Chatbot & Yapay Zeka Etkileşim ve Soru Analitiği Raporu
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    title_style, subtitle_style, section_header_style, body_style, bold_body_style = get_report_styles()

    elements = []
    dept_label = fix_tr_pdf_chars(report_data['department_label'])
    week_num = report_data['week_number']
    week_title = fix_tr_pdf_chars(report_data['week_title'])
    student_count = report_data['student_count']
    students_data = report_data['students_data']

    # Header
    elements.append(Paragraph(f"BINGOL UNIVERSITESI LMS — {dept_label.upper()}", title_style))
    elements.append(Paragraph(f"PDF 3: {week_num}. Hafta Chatbot ve Yapay Zeka Etkilesim Raporu", subtitle_style))
    elements.append(Spacer(1, 8))
    elements.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor('#059669'), spaceAfter=12))

    # Toplam Chatbot Soruları Sayısı
    total_cb_questions = sum(len(s['chatbot_questions']) for s in students_data)

    meta_data = [[
        Paragraph(f"<b>Bolum:</b> {dept_label}", body_style),
        Paragraph(f"<b>Hafta:</b> {week_title}", body_style),
        Paragraph(f"<b>Toplam AI Sorusu:</b> {total_cb_questions}", body_style)
    ]]
    meta_table = Table(meta_data, colWidths=[180, 200, 150])
    meta_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#ECFDF5')),
        ('PADDING', (0, 0), (-1, -1), 6),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#A7F3D0')),
    ]))
    elements.append(meta_table)
    elements.append(Spacer(1, 12))

    has_any_cb = False
    for idx, s in enumerate(students_data, 1):
        if not s['chatbot_questions']:
            continue

        has_any_cb = True
        s_name = fix_tr_pdf_chars(s['full_name'])
        
        s_header_data = [[
            Paragraph(f"<b>#{idx} {s_name}</b>", section_header_style),
            Paragraph(f"<b>Yapay Zekaya Sorulan Soru:</b> {len(s['chatbot_questions'])} Soru", bold_body_style)
        ]]
        s_header_table = Table(s_header_data, colWidths=[350, 180])
        s_header_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#D1FAE5')),
            ('PADDING', (0, 0), (-1, -1), 5),
        ]))
        elements.append(s_header_table)
        elements.append(Spacer(1, 4))

        cb_rows = [[
            Paragraph("<b>Ogrencinin Yapay Zekaya Sordugu Soru Metni</b>", bold_body_style),
            Paragraph("<b>Soru Tarihi ve Saati</b>", bold_body_style)
        ]]
        for q in s['chatbot_questions']:
            cb_rows.append([
                Paragraph(fix_tr_pdf_chars(q['text']), body_style),
                Paragraph(q['created_at'], body_style)
            ])

        cb_table = Table(cb_rows, colWidths=[380, 150])
        cb_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#F1F5F9')),
            ('PADDING', (0, 0), (-1, -1), 4),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
        ]))
        elements.append(cb_table)
        elements.append(Spacer(1, 10))

    if not has_any_cb:
        elements.append(Paragraph("Bu haftaya ait öğrencilerin chatbot / yapay zeka ile etkileşim kaydı bulunamadı.", body_style))

    doc.build(elements)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes


def send_department_academic_report(department, week_number, force=False):
    """
    Belirtilen bölüm ve hafta için raporu hazırlar, 3 AYRI PDF ekler ve akademisyenlere e-posta atar.
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
    subject = f"📊 [BÜ-LMS] {dept_label} — {week_number}. Hafta Öğrenci Gelişim ve Performans Raporu (3 PDF Ekli)"
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

        # 5. 3 ADET AYRI PDF EKLENTİSİ OLUŞTUR VE E-POSTAYA BAĞLA
        try:
            safe_dept = dept_label.replace(' ', '_').replace('Ç', 'C').replace('ç', 'c').replace('Ğ', 'G').replace('ğ', 'g').replace('İ', 'I').replace('ı', 'i').replace('Ö', 'O').replace('ö', 'o').replace('Ş', 'S').replace('ş', 's').replace('Ü', 'U').replace('ü', 'u')
            
            # PDF 1: Genel Öğrenci Performans ve İlerleme Raporu
            pdf1_bytes = generate_general_performance_pdf(report_data)
            pdf1_name = f"1_Genel_Performans_Raporu_{safe_dept}_Hafta_{week_number}.pdf"
            msg.attach(pdf1_name, pdf1_bytes, "application/pdf")

            # PDF 2: Haftalık Anket Yanıtları Raporu
            pdf2_bytes = generate_survey_responses_pdf(report_data)
            pdf2_name = f"2_Anket_Yanitlari_Raporu_{safe_dept}_Hafta_{week_number}.pdf"
            msg.attach(pdf2_name, pdf2_bytes, "application/pdf")

            # PDF 3: Chatbot & Yapay Zeka Etkileşim Raporu
            pdf3_bytes = generate_chatbot_analytics_pdf(report_data)
            pdf3_name = f"3_Chatbot_Etkilesim_Raporu_{safe_dept}_Hafta_{week_number}.pdf"
            msg.attach(pdf3_name, pdf3_bytes, "application/pdf")

        except Exception as pdf_err:
            logger.error(f"PDF eklentileri oluşturulurken hata ({department} Hafta {week_number}): {pdf_err}")

        msg.send(fail_silently=False)

        # 6. Başarılı Gönderim Logu
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
        logger.info(f"Başarıyla e-posta ve 3 PDF raporu gönderildi: {department} Hafta {week_number} -> {recipients}")
        return True, f"3 adet PDF eklentili rapor {len(recipients)} akademisyene başarıyla iletildi."

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
