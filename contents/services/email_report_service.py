import os
import io
import logging
from datetime import datetime
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.contrib.auth import get_user_model
from django.utils import timezone

from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, PageBreak, KeepTogether
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from contents.models import (
    WeeklyContent,
    TimeTracking,
    StudentQuizAttempt,
    StudentProgress,
    CompletedMaterial,
    PreTestResult,
    StudentQuestion,
    WeeklyPreTestResult,
    TemporaryUnlock,
    RemediationTimeTracking,
    RemediationCompletedMaterial,
    RemediationProgress,
    AcademicEmailLog
)

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

# --- FONT KAYDI (TÜRKÇE KARAKTER DESTEĞİ) ---
font_regular = 'Helvetica'
font_bold = 'Helvetica-Bold'
if os.path.exists(r'C:\Windows\Fonts\arial.ttf') and os.path.exists(r'C:\Windows\Fonts\arialbd.ttf'):
    try:
        pdfmetrics.registerFont(TTFont('Arial', r'C:\Windows\Fonts\arial.ttf'))
        pdfmetrics.registerFont(TTFont('Arial-Bold', r'C:\Windows\Fonts\arialbd.ttf'))
        font_regular = 'Arial'
        font_bold = 'Arial-Bold'
    except Exception as font_err:
        logger.warning(f"Arial font registration failed, using Helvetica: {font_err}")


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


def get_safe_filename(name):
    """Dosya isimleri için Türkçe karakterleri ASCII'ye dönüştürür."""
    tr_map = {
        'ı': 'i', 'ğ': 'g', 'ü': 'u', 'ş': 's', 'ö': 'o', 'ç': 'c',
        'İ': 'I', 'Ğ': 'G', 'Ü': 'U', 'Ş': 'S', 'Ö': 'O', 'Ç': 'C',
        ' ': '_'
    }
    res = str(name)
    for k, v in tr_map.items():
        res = res.replace(k, v)
    return "".join(c for c in res if c.isalnum() or c in ('_', '-'))


def fix_tr_pdf_chars(str_val):
    """Eğer Helvetica fontu kullanılırsa Türkçe karakterleri latin harflerine dönüştürür."""
    if not str_val:
        return ""
    if font_regular == 'Arial':
        return str(str_val)
    tr_map = {
        'ı': 'i', 'ğ': 'g', 'ü': 'u', 'ş': 's', 'ö': 'o', 'ç': 'c',
        'İ': 'I', 'Ğ': 'G', 'Ü': 'U', 'Ş': 'S', 'Ö': 'O', 'Ç': 'C'
    }
    res = str(str_val)
    for tr_c, latin_c in tr_map.items():
        res = res.replace(tr_c, latin_c)
    return res


# ==============================================================================
# 1. RAPOR: SİSTEM GENELİ ÖĞRENCİ ANALİZLERİ (14 HAFTALIK ÇİZELGE - YATAY A4)
# ==============================================================================

def get_bulk_report_data(dept):
    """
    14 haftalık akademik performans verilerini D1 öğrencileri için toplar.
    N+1 sorgusunu önleyecek şekilde optimize edilmiştir.
    """
    students = User.objects.filter(
        department=dept, category__iexact='d1', is_staff=False, is_teacher=False
    ).order_by('first_name', 'last_name')
    student_ids = list(students.values_list('id', flat=True))

    all_tts = list(TimeTracking.objects.filter(student_id__in=student_ids).select_related('weekly_content', 'material'))
    all_qas = list(StudentQuizAttempt.objects.filter(student_id__in=student_ids).select_related('quiz__material__parent_content'))
    all_sps = list(StudentProgress.objects.filter(student_id__in=student_ids).select_related('weekly_content'))
    all_cms = list(CompletedMaterial.objects.filter(student_id__in=student_ids).select_related('material'))
    all_pts = {pt.student_id: pt for pt in PreTestResult.objects.filter(student_id__in=student_ids)}
    wcs = list(WeeklyContent.objects.all().prefetch_related('materials'))

    report = []
    for s in students:
        s_times = [t for t in all_tts if t.student_id == s.id]
        s_attempts = [a for a in all_qas if a.student_id == s.id]
        s_progress = [p for p in all_sps if p.student_id == s.id]
        s_completed = [cm for cm in all_cms if cm.student_id == s.id]
        s_pt = all_pts.get(s.id)

        pre_test_info = "Girilmedi"
        if s_pt:
            pre_test_info = f"%{int(s_pt.score)}\n({s_pt.correct_answers}D/{s_pt.wrong_answers}Y)"

        overall_total_seconds = sum(t.duration_seconds for t in s_times)
        weekly_stats = []

        for i in range(1, 15):
            wc = next((w for w in wcs if w.week_number == i), None)
            dur_1, dur_2 = 0, 0
            c1, w1, score_1 = 0, 0, None
            c2, w2, score_2 = 0, 0, None
            mat_details = []
            t1_prog, t2_prog = 0.0, 0.0
            has_q1, has_q2 = False, False

            if wc:
                total_m = wc.materials.count()
                done_t1 = sum(1 for cm in s_completed if cm.material.parent_content_id == wc.id and cm.attempt_round == 1)
                t1_prog = round((done_t1 / total_m) * 100, 1) if total_m > 0 else 0.0
                done_t2 = sum(1 for cm in s_completed if cm.material.parent_content_id == wc.id and cm.attempt_round == 2)
                t2_prog = round((done_t2 / total_m) * 100, 1) if total_m > 0 else 0.0

                dur_1 = sum(t.duration_seconds for t in s_times if t.weekly_content_id == wc.id and t.attempt_round == 1)
                dur_2 = sum(t.duration_seconds for t in s_times if t.weekly_content_id == wc.id and t.attempt_round == 2)

                att_1 = next((a for a in s_attempts if a.quiz.material.parent_content_id == wc.id and a.attempt_round == 1), None)
                if att_1:
                    has_q1 = True
                    c1, w1, score_1 = att_1.correct_answers, att_1.wrong_answers, att_1.score
                att_2 = next((a for a in s_attempts if a.quiz.material.parent_content_id == wc.id and a.attempt_round == 2), None)
                if att_2:
                    has_q2 = True
                    c2, w2, score_2 = att_2.correct_answers, att_2.wrong_answers, att_2.score

                for m in wc.materials.all():
                    m_t1 = sum(t.duration_seconds for t in s_times if t.material_id == m.id and t.attempt_round == 1)
                    m_t2 = sum(t.duration_seconds for t in s_times if t.material_id == m.id and t.attempt_round == 2)
                    mat_details.append({
                        "id": m.id, "title": m.title, "content_type": m.content_type,
                        "duration_seconds_t1": m_t1, "duration_seconds_t2": m_t2
                    })

            prog_rec = next((p for p in s_progress if p.weekly_content_id == (wc.id if wc else None)), None)
            is_r2 = True if (dur_2 > 0 or has_q2 or t2_prog > 0 or (prog_rec and prog_rec.current_attempt_round == 2)) else False

            weekly_stats.append({
                "week": i,
                "has_content": wc is not None,
                "progress": t1_prog,
                "progress_2": t2_prog,
                "material_details": mat_details,
                "duration_seconds": dur_1,
                "duration_seconds_2": dur_2,
                "correct": c1, "wrong": w1, "score_1": score_1, "has_quiz_1": has_q1,
                "predicted_score_1": att_1.predicted_score if (wc and att_1) else None,
                "calibration_gap_1": att_1.calibration_gap if (wc and att_1) else None,
                "correct_2": c2, "wrong_2": w2, "score_2": score_2, "has_quiz_2": has_q2,
                "predicted_score_2": att_2.predicted_score if (wc and att_2) else None,
                "calibration_gap_2": att_2.calibration_gap if (wc and att_2) else None,
                "is_round_2_started": is_r2
            })

        t1_total = sum(t.duration_seconds for t in s_times if t.attempt_round == 1)
        t2_total = sum(t.duration_seconds for t in s_times if t.attempt_round == 2)

        report.append({
            "id": s.id,
            "full_name": f"{s.first_name} {s.last_name}".strip().upper() or s.username,
            "email": s.email,
            "total_points": getattr(s, 'total_points', 0),
            "total_time": overall_total_seconds,
            "total_time_t1": t1_total,
            "total_time_t2": t2_total,
            "pre_test_score": pre_test_info,
            "weekly_breakdown": weekly_stats
        })
    return report


def generate_bulk_academic_report_pdf(department, dept_name=""):
    """
    1. Öğrenci Analizleri Raporu (Landscape A4 Tablo).
    Frontend'deki BulkReportPdf.tsx ile birebir aynı düzen ve stillere sahiptir.
    """
    dept_label = dept_name or DEPARTMENT_NAMES.get(department, str(department).upper())
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=12,
        rightMargin=12,
        topMargin=15,
        bottomMargin=15
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'DocTitle', fontName=font_bold, fontSize=11, leading=13, alignment=1, textColor=colors.HexColor('#000000')
    )
    subtitle_style = ParagraphStyle(
        'DocSub', fontName=font_bold, fontSize=8, leading=10, alignment=1, textColor=colors.HexColor('#374151')
    )
    th_style = ParagraphStyle(
        'TH', fontName=font_bold, fontSize=5.5, leading=7, alignment=1, textColor=colors.white
    )
    th_pre_style = ParagraphStyle(
        'THPre', fontName=font_bold, fontSize=5.5, leading=7, alignment=1, textColor=colors.black
    )
    cell_student_style = ParagraphStyle(
        'CellStudent', fontName=font_bold, fontSize=6, leading=7.5, textColor=colors.HexColor('#000000')
    )
    cell_email_style = ParagraphStyle(
        'CellEmail', fontName=font_regular, fontSize=4.5, leading=6, textColor=colors.HexColor('#6B7280')
    )
    cell_pre_style = ParagraphStyle(
        'CellPre', fontName=font_bold, fontSize=5.5, leading=7, alignment=1, textColor=colors.HexColor('#1E293B')
    )
    cell_text_style = ParagraphStyle(
        'CellText', fontName=font_regular, fontSize=4.5, leading=5.5, textColor=colors.HexColor('#1E293B')
    )
    cell_empty_style = ParagraphStyle(
        'CellEmpty', fontName=font_regular, fontSize=5, leading=6, alignment=1, textColor=colors.HexColor('#94A3B8')
    )

    data = get_bulk_report_data(department)
    elements = []

    STUDENTS_PER_PAGE = 3
    total_pages = max(1, (len(data) + STUDENTS_PER_PAGE - 1) // STUDENTS_PER_PAGE)

    for page_idx in range(total_pages):
        page_students = data[page_idx * STUDENTS_PER_PAGE : (page_idx + 1) * STUDENTS_PER_PAGE]

        # Başlık
        elements.append(Paragraph(fix_tr_pdf_chars("BİNGÖL ÜNİVERSİTESİ LMS — SİSTEM GENELİ AKADEMİK GELİŞİM VE PERFORMANS ÇİZELGESİ"), title_style))
        elements.append(Spacer(1, 2))
        elements.append(Paragraph(fix_tr_pdf_chars(f"Bölüm: {dept_label.upper()} • D1 KILAVUZLU YZ ÖĞRENME GRUBU (Sayfa {page_idx + 1} / {total_pages})"), subtitle_style))
        elements.append(Spacer(1, 6))

        # Tablo
        table_data = []
        header_row = [
            Paragraph(fix_tr_pdf_chars("ÖĞRENCİ"), th_style),
            Paragraph(fix_tr_pdf_chars("ÖN TEST"), th_pre_style)
        ]
        for w in range(1, 15):
            header_row.append(Paragraph(f"H.{w}", th_style))
        header_row.append(Paragraph(fix_tr_pdf_chars("GENEL TOPLAM"), th_style))
        table_data.append(header_row)

        for s in page_students:
            row = [
                [Paragraph(f"<b>{fix_tr_pdf_chars(s['full_name'])}</b>", cell_student_style), Paragraph(s['email'], cell_email_style)],
                Paragraph(fix_tr_pdf_chars(s['pre_test_score']), cell_pre_style)
            ]

            for w in s['weekly_breakdown']:
                if not w['has_content']:
                    row.append(Paragraph(fix_tr_pdf_chars("<i>İçerik Yok</i>"), cell_empty_style))
                else:
                    cell_flowables = []
                    # T1 Box
                    t1_title = f"<b><font color='#1e3a8a'>T1</font></b> <font color='#2563eb'><b>%{int(round(w['progress']))}</b></font>"
                    cell_flowables.append(Paragraph(t1_title, cell_text_style))
                    
                    q1_str = f"{w['correct']}D / {w['wrong']}Y" if w['has_quiz_1'] else fix_tr_pdf_chars("Sınav Girilmedi")
                    t1_dur = f"T1: {format_seconds(w['duration_seconds'])}"
                    cell_flowables.append(Paragraph(f"{q1_str} | {t1_dur}", cell_text_style))

                    if w['has_quiz_1']:
                        has_pred = w['predicted_score_1'] is not None
                        pred = int(round(w['predicted_score_1'])) if has_pred else "-"
                        real = int(round(w['score_1'])) if w['score_1'] is not None else "-"
                        diff_str = ""
                        if w['score_1'] is not None and w['predicted_score_1'] is not None:
                            diff = int(round(w['score_1'])) - int(round(w['predicted_score_1']))
                            diff_str = f" (F: {'+' if diff > 0 else ''}{diff})"
                        cell_flowables.append(Paragraph(f"T:%{pred} G:%{real}{diff_str}", cell_text_style))

                    # Materyaller
                    cell_flowables.append(Paragraph(fix_tr_pdf_chars("<b><font color='#64748b'>MATERYALLER</font></b>"), cell_text_style))
                    for m in w['material_details']:
                        cell_flowables.append(Paragraph(f"• {fix_tr_pdf_chars(m['title'][:20])}", cell_text_style))
                        cell_flowables.append(Paragraph(f"<font color='#dc2626'>[T1:{format_seconds(m['duration_seconds_t1'])}|T2:{format_seconds(m['duration_seconds_t2'])}]</font>", cell_text_style))

                    # T2 Box
                    has_quiz_2 = w['has_quiz_2']
                    has_t2 = w['is_round_2_started'] or (w['duration_seconds_2'] > 0) or has_quiz_2 or (w['progress_2'] > 0)
                    if has_t2:
                        t2_prog = int(round(w['progress_2'])) if w['progress_2'] is not None else 0
                        cell_flowables.append(Paragraph(f"<b><font color='#92400e'>T2</font></b> <b><font color='#92400e'>%{t2_prog}</font></b>", cell_text_style))
                        q2_str = f"{w['correct_2']}D / {w['wrong_2']}Y" if has_quiz_2 else fix_tr_pdf_chars("Sınav Çözülmedi")
                        t2_dur = f"T2: {format_seconds(w['duration_seconds_2'])}"
                        cell_flowables.append(Paragraph(f"{q2_str} | {t2_dur}", cell_text_style))

                    row.append(cell_flowables)

            # Genel Toplam
            gt_flowables = [
                Paragraph(f"<b><font color='#1e3a8a'>{s['total_points']} PUAN</font></b>", cell_student_style),
                Paragraph(f"T1: {format_seconds(s['total_time_t1'])}", cell_text_style),
                Paragraph(f"T2: {format_seconds(s['total_time_t2'])}", cell_text_style),
                Paragraph(f"<b>TOP: {format_seconds(s['total_time'])}</b>", cell_student_style)
            ]
            row.append(gt_flowables)
            table_data.append(row)

        col_widths = [72, 36] + [45] * 14 + [65]
        t = Table(table_data, colWidths=col_widths, repeatRows=1)
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#000000')),
            ('BACKGROUND', (1, 0), (1, 0), colors.HexColor('#E2E8F0')),
            ('BACKGROUND', (-1, 0), (-1, 0), colors.HexColor('#1E293B')),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#000000')),
            ('TOPPADDING', (0, 0), (-1, -1), 2),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
            ('LEFTPADDING', (0, 0), (-1, -1), 2),
            ('RIGHTPADDING', (0, 0), (-1, -1), 2),
        ]))
        elements.append(t)

        if page_idx < total_pages - 1:
            elements.append(PageBreak())

    doc.build(elements)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes


# ==============================================================================
# 2. RAPOR: CHATBOT ANALİZ RAPORU (PORTRAIT A4)
# ==============================================================================

def get_chatbot_data(dept):
    """Bölümdeki D1 öğrencilerinin Chatbot soru-cevap geçmişini çeker."""
    students = User.objects.filter(
        department=dept, category__iexact='d1', is_staff=False, is_teacher=False
    ).order_by('first_name', 'last_name')
    student_ids = list(students.values_list('id', flat=True))

    all_questions = list(StudentQuestion.objects.filter(
        student_id__in=student_ids
    ).select_related('weekly_content').order_by('-created_at'))

    report_data = []
    for s in students:
        s_questions = [q for q in all_questions if q.student_id == s.id]
        report_data.append({
            "student_name": f"{s.first_name} {s.last_name}".strip().upper() or s.username,
            "category": getattr(s, 'category', 'd1'),
            "total_count": len(s_questions),
            "questions": [
                {
                    "text": q.question_text,
                    "ai_response": q.ai_response_text or "",
                    "week": q.weekly_content.week_number if q.weekly_content else "Genel",
                    "date": q.created_at.strftime('%d.%m.%Y %H:%M') if q.created_at else "-"
                } for q in s_questions
            ]
        })
    return report_data


def generate_chatbot_analytics_pdf(department, dept_name=""):
    """
    2. Chatbot Analiz Raporu (Portrait A4).
    Frontend'deki ChatbotReportPdf.tsx ile birebir aynı düzen ve stillere sahiptir.
    """
    dept_label = dept_name or DEPARTMENT_NAMES.get(department, str(department).upper())
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=25,
        rightMargin=25,
        topMargin=25,
        bottomMargin=25
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'DocTitle', fontName=font_bold, fontSize=14, leading=17, alignment=1, textColor=colors.HexColor('#1A1A1A')
    )
    subtitle_style = ParagraphStyle(
        'DocSub', fontName=font_bold, fontSize=10, leading=13, alignment=1, textColor=colors.HexColor('#CE1212')
    )
    date_style = ParagraphStyle(
        'DocDate', fontName=font_bold, fontSize=8, leading=10, alignment=1, textColor=colors.HexColor('#6B7280')
    )
    card_header_name = ParagraphStyle(
        'CardHeaderName', fontName=font_bold, fontSize=11, leading=13, textColor=colors.white
    )
    card_header_count = ParagraphStyle(
        'CardHeaderCount', fontName=font_bold, fontSize=11, leading=13, alignment=2, textColor=colors.HexColor('#EF4444')
    )
    q_meta_style = ParagraphStyle(
        'QMeta', fontName=font_bold, fontSize=7.5, leading=9, textColor=colors.HexColor('#6B7280')
    )
    q_label_style = ParagraphStyle(
        'QLabel', fontName=font_bold, fontSize=8, leading=10, textColor=colors.HexColor('#CE1212')
    )
    q_text_style = ParagraphStyle(
        'QText', fontName=font_bold, fontSize=8.5, leading=11, textColor=colors.HexColor('#1A1A1A')
    )
    ans_label_style = ParagraphStyle(
        'AnsLabel', fontName=font_bold, fontSize=7.5, leading=9, textColor=colors.HexColor('#047857')
    )
    ans_text_style = ParagraphStyle(
        'AnsText', fontName=font_regular, fontSize=8, leading=10.5, textColor=colors.HexColor('#1F2937')
    )

    data = get_chatbot_data(department)
    active_students = [s for s in data if s['total_count'] > 0]
    total_q_count = sum(s['total_count'] for s in data)

    elements = []
    elements.append(Paragraph(fix_tr_pdf_chars("BİNGÖL ÜNİVERSİTESİ LMS"), title_style))
    elements.append(Paragraph(fix_tr_pdf_chars("YAPAY ZEKA ETKİLEŞİM VE SORU ANALİZİ RAPORU"), title_style))
    elements.append(Spacer(1, 4))
    elements.append(Paragraph(fix_tr_pdf_chars(f"{dept_label.upper()} BÖLÜMÜ • D1 KILAVUZLU YZ ÖĞRENME GRUBU"), subtitle_style))
    elements.append(Spacer(1, 4))
    elements.append(Paragraph(fix_tr_pdf_chars(f"Rapor Tarihi: {datetime.now().strftime('%d.%m.%Y')} | Toplam Chatbot Sorusu: {total_q_count}"), date_style))
    elements.append(Spacer(1, 10))
    elements.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor('#1A1A1A'), spaceAfter=14))

    if not active_students:
        elements.append(Paragraph(fix_tr_pdf_chars("Bu bölüme ait öğrencilerin chatbot / yapay zeka ile etkileşim kaydı bulunmamaktadır."), date_style))
    else:
        for idx, s in enumerate(active_students):
            h_data = [[
                Paragraph(fix_tr_pdf_chars(f"ÖĞRENCİ: <b>{s['student_name']}</b>"), card_header_name),
                Paragraph(fix_tr_pdf_chars(f"TOPLAM SORU: {s['total_count']}"), card_header_count)
            ]]
            h_table = Table(h_data, colWidths=[360, 180])
            h_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#1A1A1A')),
                ('PADDING', (0, 0), (-1, -1), 6),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ]))
            
            s_elements = [h_table, Spacer(1, 4)]
            for q in s['questions']:
                q_box = [
                    [Paragraph(fix_tr_pdf_chars(f"TARİH: {q['date']} | <b>HAFTA {q['week']}</b>"), q_meta_style)],
                    [Paragraph(fix_tr_pdf_chars("<b>Öğrenci Sorusu:</b>"), q_label_style)],
                    [Paragraph(fix_tr_pdf_chars(f'"{q["text"]}"'), q_text_style)]
                ]
                if q['ai_response']:
                    q_box.append([Spacer(1, 2)])
                    q_box.append([Paragraph(fix_tr_pdf_chars("<b>Chatbot Yanıtı:</b>"), ans_label_style)])
                    q_box.append([Paragraph(fix_tr_pdf_chars(q['ai_response']), ans_text_style)])

                q_table = Table(q_box, colWidths=[540])
                q_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F9FAFB')),
                    ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#E5E7EB')),
                    ('LINELEFT', (0, 0), (0, -1), 3, colors.HexColor('#CE1212')),
                    ('PADDING', (0, 0), (-1, -1), 6),
                ]))
                s_elements.append(q_table)
                s_elements.append(Spacer(1, 6))

            s_elements.append(Spacer(1, 10))
            elements.append(KeepTogether(s_elements))

    doc.build(elements)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes


# ==============================================================================
# 3. RAPOR: ÖN DEĞERLENDİRME ANALİZ RAPORU (PORTRAIT A4)
# ==============================================================================

def get_weekly_pretest_data(dept):
    """Bölümdeki D1 öğrencilerinin Ön Değerlendirme ve Telafi sürecini çeker."""
    students = User.objects.filter(
        department=dept, category__iexact='d1', is_staff=False, is_teacher=False
    ).order_by('first_name', 'last_name')
    student_ids = list(students.values_list('id', flat=True))

    all_results = list(WeeklyPreTestResult.objects.filter(student_id__in=student_ids).select_related('week'))
    all_unlocks = list(TemporaryUnlock.objects.filter(student_id__in=student_ids).select_related('week'))
    all_rem_times = list(RemediationTimeTracking.objects.filter(student_id__in=student_ids).select_related('weekly_content', 'material'))
    all_rem_completions = list(RemediationCompletedMaterial.objects.filter(student_id__in=student_ids).select_related('material__parent_content'))
    all_rem_progress = list(RemediationProgress.objects.filter(student_id__in=student_ids).select_related('weekly_content'))
    weekly_contents = list(WeeklyContent.objects.all().prefetch_related('materials'))

    now = timezone.now()
    report_data = []

    for s in students:
        s_results = [r for r in all_results if r.student_id == s.id]
        s_unlocks = [u for u in all_unlocks if u.student_id == s.id]
        s_rem_times = [t for t in all_rem_times if t.student_id == s.id]
        s_rem_completions = [c for c in all_rem_completions if c.student_id == s.id]
        s_rem_progress = [p for p in all_rem_progress if p.student_id == s.id]

        s_results.sort(key=lambda x: x.week.week_number)
        pretest_details = []
        for r in s_results:
            pretest_details.append({
                "appearing_week": r.week.week_number,
                "appearing_week_title": r.week.title or f"{r.week.week_number}. Hafta",
                "is_completed": r.is_completed,
                "completed_at": r.completed_at.strftime('%d.%m.%Y %H:%M') if r.completed_at else None,
                "correct_count": r.correct_count,
                "wrong_count": r.wrong_count,
                "score_percentage": r.score_percentage,
                "unlocked_weeks": r.unlocked_weeks_json,
                "wrong_answers": getattr(r, 'wrong_answers_detail', []) or []
            })

        relevant_week_ids = set()
        for u in s_unlocks:
            relevant_week_ids.add(u.week_id)
        for t in s_rem_times:
            relevant_week_ids.add(t.weekly_content_id)
        for p in s_rem_progress:
            relevant_week_ids.add(p.weekly_content_id)

        remediation_records = []
        for w_id in relevant_week_ids:
            w_content = next((wc for wc in weekly_contents if wc.id == w_id), None)
            if not w_content:
                continue
            w_num = w_content.week_number
            u_obj = next((u for u in s_unlocks if u.week_id == w_id), None)
            prog_obj = next((p for p in s_rem_progress if p.weekly_content_id == w_id), None)

            w_times = [t for t in s_rem_times if t.weekly_content_id == w_id]
            total_rem_duration = sum(t.duration_seconds for t in w_times)

            mat_stats = []
            w_mats = [m for m in w_content.materials.all() if m.content_type != 'form']
            done_count = 0
            for m in w_mats:
                m_time = sum(t.duration_seconds for t in w_times if t.material_id == m.id)
                is_done = any(c.material_id == m.id for c in s_rem_completions)
                if is_done:
                    done_count += 1
                mat_stats.append({
                    "material_id": m.id,
                    "title": m.title or f"Materyal #{m.id}",
                    "content_type": m.content_type,
                    "duration_seconds": m_time,
                    "is_completed": is_done
                })

            calc_percentage = round((done_count / len(w_mats)) * 100, 2) if len(w_mats) > 0 else 0.0
            rem_perc = prog_obj.completion_percentage if prog_obj else calc_percentage
            rem_is_done = (rem_perc >= 100)

            is_active_lock = False
            days_remaining = 0
            unlock_until_str = None
            if u_obj and getattr(u_obj, 'unlock_until', None):
                unlock_until_str = u_obj.unlock_until.strftime('%d.%m.%Y %H:%M')
                is_active_lock = u_obj.unlock_until > now
                if is_active_lock:
                    diff = u_obj.unlock_until - now
                    days_remaining = max(1, diff.days + (1 if diff.seconds > 0 else 0))

            remediation_records.append({
                "week_number": w_num,
                "week_title": w_content.title or f"{w_num}. Hafta",
                "is_active": is_active_lock,
                "expires_at": unlock_until_str,
                "days_remaining": days_remaining,
                "total_duration_seconds": total_rem_duration,
                "completion_percentage": rem_perc,
                "is_completed": rem_is_done,
                "materials": mat_stats
            })

        remediation_records.sort(key=lambda x: x['week_number'])

        report_data.append({
            "student_id": s.id,
            "full_name": f"{s.first_name} {s.last_name}".strip().upper() or s.username,
            "email": s.email,
            "category": getattr(s, 'category', 'd1'),
            "total_pretests_taken": len(pretest_details),
            "total_wrong_questions": sum(r['wrong_count'] for r in pretest_details),
            "active_locks_count": sum(1 for r in remediation_records if r['is_active']),
            "total_remediation_duration_seconds": sum(r['total_duration_seconds'] for r in remediation_records),
            "pretests": pretest_details,
            "remediation_weeks": remediation_records
        })

    return report_data


def generate_weekly_pretest_report_pdf(department, dept_name=""):
    """
    3. Ön Değerlendirme Analiz Raporu (Portrait A4).
    Frontend'deki WeeklyPreTestReportPdf.tsx ile birebir aynı düzen ve stillere sahiptir.
    """
    dept_label = dept_name or DEPARTMENT_NAMES.get(department, str(department).upper())
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=25,
        rightMargin=25,
        topMargin=25,
        bottomMargin=25
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'DocTitle', fontName=font_bold, fontSize=13, leading=16, alignment=1, textColor=colors.HexColor('#1A1A1A')
    )
    subtitle_style = ParagraphStyle(
        'DocSub', fontName=font_bold, fontSize=9.5, leading=12, alignment=1, textColor=colors.HexColor('#CE1212')
    )
    date_style = ParagraphStyle(
        'DocDate', fontName=font_bold, fontSize=7.5, leading=9, alignment=1, textColor=colors.HexColor('#6B7280')
    )
    card_name = ParagraphStyle(
        'CardName', fontName=font_bold, fontSize=10, leading=12, textColor=colors.white
    )
    card_sub = ParagraphStyle(
        'CardSub', fontName=font_regular, fontSize=7, leading=8.5, textColor=colors.HexColor('#9CA3AF')
    )
    card_stat_num = ParagraphStyle(
        'CardStatNum', fontName=font_bold, fontSize=10, leading=12, alignment=1, textColor=colors.white
    )
    card_stat_lbl = ParagraphStyle(
        'CardStatLbl', fontName=font_bold, fontSize=5.5, leading=7, alignment=1, textColor=colors.HexColor('#D1D5DB')
    )
    sec_header = ParagraphStyle(
        'SecHeader', fontName=font_bold, fontSize=8.5, leading=11, textColor=colors.HexColor('#1E1B4B')
    )
    text_bold = ParagraphStyle(
        'TextBold', fontName=font_bold, fontSize=7.5, leading=9.5, textColor=colors.HexColor('#1E293B')
    )
    text_normal = ParagraphStyle(
        'TextNormal', fontName=font_regular, fontSize=7, leading=9, textColor=colors.HexColor('#334155')
    )

    data = get_weekly_pretest_data(department)
    elements = []

    elements.append(Paragraph(fix_tr_pdf_chars("BİNGÖL ÜNİVERSİTESİ LMS"), title_style))
    elements.append(Paragraph(fix_tr_pdf_chars("HAFTALIK ÖN DEĞERLENDİRME VE TELAFİ ANALİZ RAPORU"), title_style))
    elements.append(Spacer(1, 3))
    elements.append(Paragraph(fix_tr_pdf_chars(f"{dept_label.upper()} BÖLÜMÜ • D1 KILAVUZLU YZ ÖĞRENME GRUBU"), subtitle_style))
    elements.append(Spacer(1, 3))
    elements.append(Paragraph(fix_tr_pdf_chars(f"Rapor Tarihi: {datetime.now().strftime('%d.%m.%Y')}"), date_style))
    elements.append(Spacer(1, 8))
    elements.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor('#1A1A1A'), spaceAfter=12))

    has_data = any(len(s['pretests']) > 0 or len(s['remediation_weeks']) > 0 for s in data)

    if not has_data:
        elements.append(Paragraph(fix_tr_pdf_chars("Bu bölüme ait ön değerlendirme testi veya telafi kaydı bulunmamaktadır."), text_normal))
    else:
        for idx, s in enumerate(data):
            if len(s['pretests']) == 0 and len(s['remediation_weeks']) == 0:
                continue

            s_elements = []
            stat_boxes = [
                Paragraph(f"<b>{s['total_pretests_taken']}</b>", card_stat_num),
                Paragraph(f"<b><font color='#F87171'>{s['total_wrong_questions']}</font></b>", card_stat_num),
                Paragraph(f"<b><font color='#FBBF24'>{s['active_locks_count']}</font></b>", card_stat_num),
                Paragraph(f"<b><font color='#93C5FD'>{format_seconds(s['total_remediation_duration_seconds'])}</font></b>", card_stat_num)
            ]
            c_data = [[
                [Paragraph(fix_tr_pdf_chars(s['full_name']), card_name), Paragraph(s['email'], card_sub)],
                [stat_boxes[0], Paragraph(fix_tr_pdf_chars("GİRİLEN ÖN TEST"), card_stat_lbl)],
                [stat_boxes[1], Paragraph(fix_tr_pdf_chars("TOPLAM YANLIŞ"), card_stat_lbl)],
                [stat_boxes[2], Paragraph(fix_tr_pdf_chars("AKTİF TELAFİ KİLİDİ"), card_stat_lbl)],
                [stat_boxes[3], Paragraph(fix_tr_pdf_chars("TELAFİ SÜRESİ"), card_stat_lbl)]
            ]]
            c_table = Table(c_data, colWidths=[200, 85, 85, 85, 85])
            c_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#1A1A1A')),
                ('PADDING', (0, 0), (-1, -1), 5),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ]))
            s_elements.append(c_table)
            s_elements.append(Spacer(1, 6))

            # Bölüm 1: Ön Test Sonuçları
            s_elements.append(Paragraph(fix_tr_pdf_chars("<b>1. Haftalık Giriş Testleri ve Yanlış Yapılan Sorular</b>"), sec_header))
            s_elements.append(Spacer(1, 3))

            if len(s['pretests']) == 0:
                s_elements.append(Paragraph(fix_tr_pdf_chars("Öğrencinin ön test kaydı bulunmamaktadır."), text_normal))
            else:
                for pt in s['pretests']:
                    pt_header = fix_tr_pdf_chars(f"<b>{pt['appearing_week']}. Hafta Ön Değerlendirme Testi</b> | {pt['completed_at'] or '-'} | <font color='#15803D'>{pt['correct_count']} Doğru</font> - <font color='#DC2626'>{pt['wrong_count']} Yanlış</font> (%{pt['score_percentage']} Başarı)")
                    pt_rows = [[Paragraph(pt_header, text_bold)]]

                    if pt['wrong_answers']:
                        for wa in pt['wrong_answers']:
                            w_q_text = fix_tr_pdf_chars(f"• [Hedef Hafta {wa.get('target_week', '-')}] <b>Soru:</b> {wa.get('question_text', '')}")
                            w_sel = fix_tr_pdf_chars(f"  Seçilen Yanıt: <font color='#DC2626'><b>{wa.get('selected_option', '-')}</b></font> | Doğru Yanıt: <font color='#15803D'><b>{wa.get('correct_option', '-')}</b></font>")
                            pt_rows.append([Paragraph(w_q_text, text_normal)])
                            pt_rows.append([Paragraph(w_sel, text_normal)])
                    else:
                        pt_rows.append([Paragraph(fix_tr_pdf_chars("<i>Bu teste ait yanlış soru bulunmamaktadır (Tüm sorular doğru).</i>"), text_normal)])

                    pt_table = Table(pt_rows, colWidths=[540])
                    pt_table.setStyle(TableStyle([
                        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F8FAFC')),
                        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#E2E8F0')),
                        ('PADDING', (0, 0), (-1, -1), 4),
                    ]))
                    s_elements.append(pt_table)
                    s_elements.append(Spacer(1, 4))

            # Bölüm 2: Telafi Süreci
            s_elements.append(Spacer(1, 3))
            s_elements.append(Paragraph(fix_tr_pdf_chars("<b>2. Telafi Sürecinde Açılan Haftalar ve Tamamlama Durumu</b>"), sec_header))
            s_elements.append(Spacer(1, 3))

            if len(s['remediation_weeks']) == 0:
                s_elements.append(Paragraph(fix_tr_pdf_chars("Öğrenciye ait açılmış telafi haftası bulunmamaktadır."), text_normal))
            else:
                for rw in s['remediation_weeks']:
                    status_str = f"<font color='#059669'><b>KİLİT AÇIK ({rw['days_remaining']} Gün Kaldı)</b></font>" if rw['is_active'] else "<font color='#6B7280'>SÜRESİ DOLDU</font>"
                    comp_str = "<font color='#059669'><b>TAMAMLANDI</b></font>" if rw['is_completed'] else f"%{int(rw['completion_percentage'])} Tamamlandı"
                    dur_str = format_seconds(rw['total_duration_seconds'])

                    rw_hdr = fix_tr_pdf_chars(f"<b>{rw['week_number']}. Hafta Telafisi:</b> {rw['week_title']} | Durum: {status_str} | İlerleme: {comp_str} | Telafi Süresi: {dur_str}")
                    rw_rows = [[Paragraph(rw_hdr, text_bold)]]

                    for rm in rw['materials']:
                        icon_done = "[Tamamlandı]" if rm['is_completed'] else "[Eksik]"
                        color_done = "#059669" if rm['is_completed'] else "#DC2626"
                        rm_text = fix_tr_pdf_chars(f"• {rm['title']} ({rm['content_type'].upper()}) - Süre: {format_seconds(rm['duration_seconds'])} - <font color='{color_done}'><b>{icon_done}</b></font>")
                        rw_rows.append([Paragraph(rm_text, text_normal)])

                    rw_table = Table(rw_rows, colWidths=[540])
                    rw_table.setStyle(TableStyle([
                        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F8FAFC')),
                        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#E2E8F0')),
                        ('PADDING', (0, 0), (-1, -1), 4),
                    ]))
                    s_elements.append(rw_table)
                    s_elements.append(Spacer(1, 4))

            s_elements.append(Spacer(1, 10))
            elements.append(KeepTogether(s_elements))

    doc.build(elements)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes


# ==============================================================================
# 4. E-POSTA İÇERİK ŞABLONLARI (KULLANICI FORMATINA TAM UYUMLU)
# ==============================================================================

def build_academic_report_html(academician_name, dept_label):
    """
    Kullanıcının talep ettiği sade ve şık e-posta HTML içeriğini üretir.
    Gereksiz uzun tablolar içermez; sadece ekli 3 PDF'in bilgilendirmesini yapar.
    """
    html = f"""
    <!DOCTYPE html>
    <html lang="tr">
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
                background-color: #f1f5f9;
                margin: 0;
                padding: 24px 12px;
                color: #1e293b;
            }}
            .container {{
                max-width: 640px;
                margin: 0 auto;
                background: #ffffff;
                border-radius: 16px;
                overflow: hidden;
                border: 1px solid #e2e8f0;
                box-shadow: 0 4px 12px rgba(0,0,0,0.05);
            }}
            .header {{
                background: linear-gradient(135deg, #1e1b4b 0%, #312e81 100%);
                padding: 32px 28px;
                text-align: left;
                color: #ffffff;
            }}
            .header-title {{
                font-size: 20px;
                font-weight: 900;
                letter-spacing: 0.5px;
                margin: 0;
                text-transform: uppercase;
            }}
            .header-subtitle {{
                font-size: 13px;
                font-weight: 600;
                color: #c7d2fe;
                margin: 6px 0 0 0;
                letter-spacing: 0.5px;
            }}
            .content {{
                padding: 32px 28px;
            }}
            .salutation {{
                font-size: 15px;
                font-weight: 700;
                color: #0f172a;
                margin-bottom: 16px;
                margin-top: 0;
            }}
            .lead-text {{
                font-size: 14px;
                line-height: 1.6;
                color: #334155;
                margin-bottom: 24px;
            }}
            .attachment-box {{
                background-color: #f8fafc;
                border: 1px solid #e2e8f0;
                border-radius: 12px;
                padding: 20px;
                margin-bottom: 24px;
            }}
            .attachment-header {{
                font-size: 13px;
                font-weight: 800;
                color: #1e1b4b;
                text-transform: uppercase;
                letter-spacing: 0.5px;
                margin-bottom: 14px;
            }}
            .attachment-item {{
                margin-bottom: 14px;
                font-size: 13px;
                line-height: 1.5;
                color: #334155;
            }}
            .attachment-item:last-child {{
                margin-bottom: 0;
            }}
            .attachment-name {{
                font-weight: 700;
                color: #1e1b4b;
            }}
            .footer-note {{
                font-size: 13px;
                line-height: 1.5;
                color: #64748b;
                font-style: italic;
                border-top: 1px solid #f1f5f9;
                padding-top: 16px;
                margin: 0;
            }}
            .footer {{
                background: #f8fafc;
                padding: 16px 28px;
                text-align: center;
                font-size: 11px;
                color: #94a3b8;
                border-top: 1px solid #e2e8f0;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1 class="header-title">BİNGÖL ÜNİVERSİTESİ LMS  SINIF</h1>
                <p class="header-subtitle">Akademik Analiz ve İzleme Raporları</p>
            </div>
            <div class="content">
                <p class="salutation">Sayın {academician_name},</p>
                <p class="lead-text">
                    <strong>{dept_label}</strong> bölümüne ait Kategori D1 grubu öğrencilerinin akademisyen panelinde yer alan güncel analiz raporları ekte bilgilerinize sunulmuştur.
                </p>
                <div class="attachment-box">
                    <div class="attachment-header">E-Posta Ekinde Yer Alan Raporlar (3 Adet PDF):</div>
                    <div class="attachment-item">
                        📎 <span class="attachment-name">1. Öğrenci Analizleri Raporu:</span> 14 haftalık akademik performans, T1/T2 tamamlama yüzdeleri, çalışma süreleri ve sınav skorları.
                    </div>
                    <div class="attachment-item" style="margin-top: 12px;">
                        📎 <span class="attachment-name">2. Chatbot Analiz Raporu:</span> Öğrencilerin yapay zeka chatbot ile olan soru-yanıt etkileşimleri ve haftalık dökümleri.
                    </div>
                    <div class="attachment-item" style="margin-top: 12px;">
                        📎 <span class="attachment-name">3. Ön Değerlendirme Analiz Raporu:</span> Haftalık ön değerlendirme test sonuçları, tetiklenen telafi kilitleri ve telafi süreci ilerlemeleri.
                    </div>
                </div>
                <p class="footer-note">
                    Raporlara ait tüm ayrıntılı veriler ve istatistikler ekli PDF belgelerinde yer almaktadır.
                </p>
            </div>
            <div class="footer">
                Bingöl Üniversitesi Öğrenme Yönetim Sistemi (LMS) • Otomatik Raporlama Servisi
            </div>
        </div>
    </body>
    </html>
    """
    return html


def build_academic_report_text(academician_name, dept_label):
    """Plain-text e-posta fallback metni."""
    text = (
        "BİNGÖL ÜNİVERSİTESİ LMS  SINIF\n"
        "Akademik Analiz ve İzleme Raporları\n\n"
        f"Sayın {academician_name},\n\n"
        f"{dept_label} bölümüne ait Kategori D1 grubu öğrencilerinin akademisyen panelinde yer alan güncel analiz raporları ekte bilgilerinize sunulmuştur.\n\n"
        "E-Posta Ekinde Yer Alan Raporlar (3 Adet PDF):\n\n"
        "📎 1. Öğrenci Analizleri Raporu: 14 haftalık akademik performans, T1/T2 tamamlama yüzdeleri, çalışma süreleri ve sınav skorları.\n\n"
        "📎 2. Chatbot Analiz Raporu: Öğrencilerin yapay zeka chatbot ile olan soru-yanıt etkileşimleri ve haftalık dökümleri.\n\n"
        "📎 3. Ön Değerlendirme Analiz Raporu: Haftalık ön değerlendirme test sonuçları, tetiklenen telafi kilitleri ve telafi süreci ilerlemeleri.\n\n"
        "Raporlara ait tüm ayrıntılı veriler ve istatistikler ekli PDF belgelerinde yer almaktadır.\n"
    )
    return text


# ==============================================================================
# 5. MAİL GÖNDERİM ANA SERVİSİ (SEND_DEPARTMENT_ACADEMIC_REPORT)
# ==============================================================================

def send_department_academic_report(department, week_number=1, force=False):
    """
    Belirtilen bölüm için akademisyen panelindeki 3 ayrı PDF raporunu oluşturur,
    akademisyene ekli olarak e-posta gönderir ve gönderim kaydını tutar.
    """
    week_num = week_number or 1

    # 1. Mükerrer Gönderim Kontrolü
    if not force:
        already_sent = AcademicEmailLog.objects.filter(
            department=department, week_number=week_num, status="SUCCESS"
        ).exists()
        if already_sent:
            logger.info(f"Rapor zaten gönderilmiş: {department} - Hafta {week_num}")
            return False, "Bu haftanın raporu daha önce gönderilmiştir."

    # 2. Bölüm ve Akademisyen Bilgisi
    dept_label = DEPARTMENT_NAMES.get(department, str(department))
    safe_dept = get_safe_filename(dept_label)

    # İlgili bölümün veya sistemin kayıtlı akademisyenini al
    teacher = User.objects.filter(is_teacher=True, department=department).first()
    if not teacher:
        teacher = User.objects.filter(is_teacher=True).first()

    if teacher:
        academician_name = f"{teacher.first_name} {teacher.last_name}".strip() or teacher.username
    else:
        academician_name = "Akademisyenimiz"

    # Alıcı E-postaları
    recipients = list(
        User.objects.filter(is_teacher=True, department=department)
        .values_list('email', flat=True)
    )
    if not recipients:
        recipients = list(
            User.objects.filter(is_teacher=True)
            .values_list('email', flat=True)
        )
    if not recipients:
        recipients = [settings.EMAIL_HOST_USER]

    host_email = getattr(settings, 'EMAIL_HOST_USER', None)
    if host_email and "@" in host_email and host_email not in recipients:
        recipients.append(host_email)

    recipients = list(set(r for r in recipients if r and "@" in r))

    # Öğrenci Sayısı (D1)
    student_count = User.objects.filter(
        department=department, category__iexact='d1', is_staff=False, is_teacher=False
    ).count()

    # 3. E-posta Başlığı ve İçeriği
    subject = f"BİNGÖL ÜNİVERSİTESİ LMS  SINIF — Akademik Analiz ve İzleme Raporları ({dept_label})"
    html_content = build_academic_report_html(academician_name, dept_label)
    text_content = build_academic_report_text(academician_name, dept_label)

    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', settings.EMAIL_HOST_USER)

    try:
        msg = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=from_email,
            to=recipients
        )
        msg.attach_alternative(html_content, "text/html")

        # 4. 3 ADET AYRI PDF EKLENTİSİNİ OLUŞTUR VE BAĞLA
        try:
            # 1. Öğrenci Analizleri Raporu (Landscape A4)
            pdf1_bytes = generate_bulk_academic_report_pdf(department, dept_name=dept_label)
            pdf1_name = f"1_Ogrenci_Analizleri_Raporu_{safe_dept}.pdf"
            msg.attach(pdf1_name, pdf1_bytes, "application/pdf")

            # 2. Chatbot Analiz Raporu (Portrait A4)
            pdf2_bytes = generate_chatbot_analytics_pdf(department, dept_name=dept_label)
            pdf2_name = f"2_Chatbot_Analiz_Raporu_{safe_dept}.pdf"
            msg.attach(pdf2_name, pdf2_bytes, "application/pdf")

            # 3. Ön Değerlendirme Analiz Raporu (Portrait A4)
            pdf3_bytes = generate_weekly_pretest_report_pdf(department, dept_name=dept_label)
            pdf3_name = f"3_On_Degerlendirme_Analiz_Raporu_{safe_dept}.pdf"
            msg.attach(pdf3_name, pdf3_bytes, "application/pdf")

        except Exception as pdf_err:
            logger.error(f"PDF eklentileri oluşturulurken hata ({department} Hafta {week_num}): {pdf_err}", exc_info=True)
            return False, f"PDF raporları oluşturulamadı: {pdf_err}"

        # 5. Gönder
        msg.send(fail_silently=False)

        # 6. Başarılı Gönderim Logu
        AcademicEmailLog.objects.update_or_create(
            department=department,
            week_number=week_num,
            defaults={
                'recipients': ", ".join(recipients),
                'student_count': student_count,
                'status': 'SUCCESS',
                'error_message': None
            }
        )
        logger.info(f"Başarıyla e-posta ve 3 PDF raporu gönderildi: {department} Hafta {week_num} -> {recipients}")
        return True, f"3 adet PDF eklentili akademik rapor {len(recipients)} akademisyene başarıyla iletildi."

    except Exception as e:
        err_msg = str(e)
        logger.error(f"E-posta raporu gönderim hatası ({department} Hafta {week_num}): {err_msg}", exc_info=True)
        AcademicEmailLog.objects.update_or_create(
            department=department,
            week_number=week_num,
            defaults={
                'recipients': ", ".join(recipients),
                'student_count': student_count,
                'status': 'FAILED',
                'error_message': err_msg
            }
        )
        return False, f"E-posta gönderim hatası: {err_msg}"
