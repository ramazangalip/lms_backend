import os
import csv
import json
import re
import requests
from django.conf import settings

_KNOWLEDGE_BASE_CACHE = None

def get_knowledge_base():
    """
    CSV Bilgi Bankasını (BT_Chatbot_KnowledgeBase_D1_Kilavuzlu.csv) okur 
    ve meşguliyeti engellemek için hafızaya (cache) alır.
    """
    global _KNOWLEDGE_BASE_CACHE
    if _KNOWLEDGE_BASE_CACHE is not None:
        return _KNOWLEDGE_BASE_CACHE

    csv_filename = 'BT_Chatbot_KnowledgeBase_D1_Kilavuzlu.csv'
    
    # Olası dosya yolları
    possible_paths = [
        os.path.join(settings.BASE_DIR, csv_filename),
        os.path.join(os.path.dirname(settings.BASE_DIR), 'lms_backend', csv_filename),
        os.path.join(os.path.dirname(settings.BASE_DIR), 'lms_frontend', csv_filename),
        os.path.join(os.path.dirname(settings.BASE_DIR), csv_filename)
    ]

    csv_path = None
    for path in possible_paths:
        if os.path.exists(path):
            csv_path = path
            break

    kb = {}
    if csv_path:
        try:
            with open(csv_path, 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    item_id = row.get('İd', '').strip()
                    if item_id:
                        kb[item_id] = row
        except Exception as e:
            print(f"[HATA] CSV Bilgi bankası okunurken hata oluştu: {str(e)}")

    _KNOWLEDGE_BASE_CACHE = kb
    return _KNOWLEDGE_BASE_CACHE

def extract_missing_concepts(yanlis_soru_id_listesi):
    """
    Öğrencinin yanlış yaptığı soru ID'lerini CSV Bilgi Bankası ile eşleştirerek 
    eksik kavramlar ve yaygın yanılgılar bloğunu oluşturur.
    """
    if not yanlis_soru_id_listesi:
        return "Tüm sorular doğru yanıtlandı, kavram yanılgısı tespit edilmedi."

    kb = get_knowledge_base()
    concept_lines = []

    for item_id in yanlis_soru_id_listesi:
        item_id_str = str(item_id).strip()
        row = kb.get(item_id_str)
        if row:
            konu = row.get('konu', '').strip()
            ilgili_kavramlar = row.get('ilgili_kavramlar', '').strip()
            yanlis_bilinen = row.get('yanlis_bilinen', '').strip()
            line = f"- Konu: {konu} (İlgili Kavramlar: {ilgili_kavramlar}) | Yaygın Yanılgı: {yanlis_bilinen}"
            concept_lines.append(line)
        else:
            concept_lines.append(f"- Soru ID: {item_id_str} | Detaylı konu kavramı sistem veritabanında incelendi.")

    if not concept_lines:
        return "Tüm sorular doğru yanıtlandı, kavram yanılgısı tespit edilmedi."

    return "\n".join(concept_lines)

def build_llm_prompt(ogrenci_tam_ad, bolum, hafta_konu, dogru, yanlis, bos, toplam, eksik_kavramlar_blogu):
    """
    İstenen pedagojik System Prompt şablonunu oluşturur.
    """
    basari_orani = round((dogru / toplam) * 100, 1) if toplam > 0 else 0.0

    prompt = f"""ROL:
Sen üniversite düzeyindeki Bilgi Teknolojilerine Giriş dersi için yapılandırılmış, öğrenci odaklı bir Akademik Ölçme-Değerlendirme Asistanısın.

GİRDİLER:
- Öğrenci: {ogrenci_tam_ad}
- Bölüm: {bolum}
- Hafta/Konu: {hafta_konu}
- Skor: {dogru} Doğru, {yanlis} Yanlış, {bos} Boş (Toplam: {toplam} | Başarı: %{basari_orani})
- Tespit Edilen Eksik Kavramlar ve Yanılgılar:
{eksik_kavramlar_blogu}

KURALLAR VE FORMAT:
1. İLK CÜMLE ZORUNLULUĞU:
Metne MUTLAKA istisnasız olarak "Merhaba {ogrenci_tam_ad}," hitabıyla başla ve testi tamamladığı için nazik bir tebrik ifadesi kullan.
2. GENEL DEĞERLENDİRME:
Öğrencinin başarı yüzdesini ve harcadığı emeği motive edici, yapıcı bir dille özetle.
3. GÜÇLÜ YÖNLER:
Doğru yaptığı konular üzerinden başarısını pekiştir.
4. KAVRAM YANILGILARI VE GELİŞİM ALANLARI:
Yukarıda listelenen eksik kavramları ve "Yaygın Yanılgı" açıklamalarını temel alarak öğrencinin hatasını anlamasını sağla. Ezber bilgi verme; neden karıştırıldığını günlük hayattan 1 somut analoji veya örnekle izah et.
5. SOKRATİK DÜŞÜNME SORUSU:
Analizin sonuna, eksik kalan kavramı pekiştirmesi için düşündürücü tek bir Sokratik yönlendirme sorusu ekle ve bir sonraki ünite için başarılar dileyerek bitir."""

    return prompt

STOP_WORDS = {'de', 'da', 'te', 'ta', 'nasıl', 'yapılır', 'nedir', 'ne', 'için', 've', 'ile', 'bir', 'bu', 'şu', 'o', 'var', 'yok', 'mi', 'mı', 'mu', 'mü', 'nelerdir'}

def search_knowledge_base_for_chat(user_message, chat_history=None):
    """
    LLM servisleri erişilemez olduğunda CSV Bilgi Bankası (BT_Chatbot_KnowledgeBase_D1_Kilavuzlu.csv) 
    veya sohbet geçmişi üzerinden öğrencinin sorusuna doğrudan ve öğretici yanıt arar.
    """
    msg_lower = str(user_message).lower()
    
    # Geçmiş Soru Sorgusu Kontrolü
    if any(kw in msg_lower for kw in ["az önce", "önceki soru", "ne sordum", "geçmiş soru", "son sorduğum", "ne demiştim"]):
        if chat_history and len(chat_history) > 0:
            last_item = chat_history[-1]
            last_q = getattr(last_item, 'question_text', None) or (last_item.get('question_text') if isinstance(last_item, dict) else None)
            if last_q:
                return f"Az önce bana şu soruyu sormuştunuz: **\"{last_q}\"**"

    # Özel Excel Hücre Birleştirme Kontrolü
    if "excel" in msg_lower and ("hücre" in msg_lower or "birleştir" in msg_lower):
        return (
            "Excel'de hücre birleştirmek için şu adımları izleyebilirsiniz:\n\n"
            "1. Birleştirmek istediğiniz hücreleri fare ile seçin (örneğin A1 ve B1).\n"
            "2. Üst menüdeki **Giriş (Home)** sekmesine tıklayın.\n"
            "3. **Hizalama (Alignment)** grubunda yer alan **Birleştir ve Ortala (Merge & Center)** düğmesine basın.\n\n"
            "İpucu: Birleştirme yaptığınızda sadece sol üstteki hücrenin verisi korunur, diğer hücrelerdeki veriler silinebilir."
        )

    # Word Yazı Kalınlaştırma / Biçimlendirme Kontrolü
    if "word" in msg_lower and ("kalın" in msg_lower or "bold" in msg_lower or "kalınlaş" in msg_lower):
        return (
            "Microsoft Word'de yazıyı kalınlaştırmak için şu yöntemleri kullanabilirsiniz:\n\n"
            "1. Kalınlaştırmak istediğiniz metni fare ile seçin.\n"
            "2. Üst menüdeki **Giriş (Home)** sekmesinde yer alan **K** (Bold - Kalın) simgesine tıklayın.\n"
            "3. Veya klavye kısayolu olarak **Ctrl + B** (veya Türkçe sürümlerde **Ctrl + K**) tuşlarına basın."
        )

    # Word Tablo Hücre Birleştirme Kontrolü
    if "word" in msg_lower and ("hücre" in msg_lower or "birleştir" in msg_lower or "tablo" in msg_lower):
        return (
            "Microsoft Word'de bir tabloda hücre birleştirmek için:\n\n"
            "1. Birleştirmek istediğiniz yan yana veya alt alta hücreleri seçin.\n"
            "2. Seçili alan üzerine sağ tıklayın.\n"
            "3. Açılan menüden **Hücreleri Birleştir (Merge Cells)** seçeneğine tıklayın.\n\n"
            "Veya hücreleri seçtikten sonra üst şeritte beliren **Düzen (Layout)** sekmesinden **Hücreleri Birleştir** butonunu kullanabilirsiniz."
        )

    # Akıllı CSV Bilgi Bankası Taraması
    kb = get_knowledge_base()
    if not kb:
        return f"Sorunuz ('{user_message}') alındı! Bilgi Teknolojileri ders materyallerini inceleyerek çalışmalarınıza devam edebilirsiniz."

    # Tüm noktalama işaretlerini, tırnak işaretlerini (", ', ”, “, vb.) temizle
    clean_query = re.sub(r'[^\w\s]', ' ', msg_lower, flags=re.UNICODE)
    tokens = [w for w in clean_query.split() if w not in STOP_WORDS and len(w) > 1]
    
    if not tokens:
        return f"Sorunuz ('{user_message}') alındı! Bilgi Teknolojileri ders materyallerini inceleyebilirsiniz."

    matches = []
    for item_id, row in kb.items():
        soru = row.get('soru', '').lower()
        konu = row.get('konu', '').lower()
        kavramlar = row.get('ilgili_kavramlar', '').lower()
        anahtarlar = row.get('anahtar_kelimeler', '').lower()
        
        score = 0
        for token in tokens:
            stem = token[:4] if len(token) >= 4 else token
            if token in soru or stem in soru:
                score += 12
            if token in anahtarlar or stem in anahtarlar:
                score += 10
            if token in kavramlar or stem in kavramlar:
                score += 8
            if token in konu or stem in konu:
                score += 5

        # Eksik veya taslak metin yerine tam açıklama oluştur
        kisa = (row.get('nihai_cevap_kisa') or row.get('kisa_cevap') or '').strip()
        uzun = (row.get('nihai_cevap_uzun') or row.get('uzun_cevap') or row.get('ornek') or '').strip()
        
        if "adımlarını görelim" in uzun.lower() or len(uzun) < 25:
            answer = kisa if kisa else uzun
        else:
            answer = f"{kisa}\n\n{uzun}" if (kisa and kisa not in uzun) else (uzun or kisa)

        if score > 0 and answer and len(answer.strip()) > 10:
            matches.append((score, row, answer.strip()))

    if matches:
        matches.sort(key=lambda x: x[0], reverse=True)
        best_score, best_row, best_answer = matches[0]
        if best_score >= 4:
            topic = best_row.get('konu', '')
            prefix = f"**{topic}** konusundaki sorunuza ilişkin açıklama:\n\n" if topic else ""
            return f"{prefix}{best_answer}"

    return f"Sorunuz ('{user_message}') alındı! Bilgi Teknolojileri dersi kapsamında sorularınızı sorabilir, ders materyallerini inceleyerek çalışmalarınıza devam edebilirsiniz."

def call_openrouter_or_llm(prompt, ogrenci_tam_ad=None, is_test_analysis=False, fallback_text=None, user_message=None, chat_history=None):
    """
    OpenRouter API (google/gemma-2-27b-it:free) veya Gemini API / Vertex AI üzerinden 
    LLM analizi veya sohbet yanıtı üretir. Hata durumunda uygun fallback yanıt döner.
    """
    full_prompt = prompt
    if chat_history and not is_test_analysis:
        history_lines = []
        for item in chat_history:
            q_text = getattr(item, 'question_text', None) or (item.get('question_text') if isinstance(item, dict) else None)
            a_text = getattr(item, 'ai_response_text', None) or (item.get('ai_response_text') if isinstance(item, dict) else None)
            if q_text:
                history_lines.append(f"Öğrenci: {q_text}")
            if a_text:
                history_lines.append(f"Asistan: {a_text}")
        if history_lines:
            history_str = "\n".join(history_lines[-10:])
            full_prompt = f"GEÇMİŞ SOHBET DİYALOĞU:\n{history_str}\n\nYENİ SORU / TALEP:\n{prompt}"

    # 1. OpenRouter API Denemesi
    openrouter_key = getattr(settings, 'OPENROUTER_API_KEY', os.environ.get('OPENROUTER_API_KEY'))
    if openrouter_key:
        try:
            url = "https://openrouter.ai/api/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {openrouter_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://bingol.edu.tr",
                "X-Title": "Bingol LMS AI Engine"
            }
            payload = {
                "model": "google/gemma-2-27b-it:free",
                "messages": [
                    {"role": "user", "content": full_prompt}
                ],
                "temperature": 0.7
            }
            resp = requests.post(url, headers=headers, json=payload, timeout=12)
            if resp.status_code == 200:
                result_json = resp.json()
                content = result_json['choices'][0]['message']['content'].strip()
                if content:
                    if is_test_analysis and ogrenci_tam_ad:
                        if not content.startswith(f"Merhaba {ogrenci_tam_ad}"):
                            content = f"Merhaba {ogrenci_tam_ad}, testi başarıyla tamamladığın için tebrik ederim!\n\n" + content
                    return content
        except Exception as e:
            print(f"[UYARI] OpenRouter API çağrısı başarısız, diğer modeller deneniyor: {str(e)}")

    # 2. Google Gemini API / REST Endpoint Denemesi
    gemini_key = getattr(settings, 'GEMINI_API_KEY', os.environ.get('GEMINI_API_KEY'))
    if gemini_key:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={gemini_key}"
            headers = {"Content-Type": "application/json"}
            payload = {
                "contents": [{"parts": [{"text": full_prompt}]}]
            }
            resp = requests.post(url, headers=headers, json=payload, timeout=12)
            if resp.status_code == 200:
                res_data = resp.json()
                content = res_data['candidates'][0]['content']['parts'][0]['text'].strip()
                if content:
                    if is_test_analysis and ogrenci_tam_ad:
                        if not content.startswith(f"Merhaba {ogrenci_tam_ad}"):
                            content = f"Merhaba {ogrenci_tam_ad}, testi başarıyla tamamladığın için tebrik ederim!\n\n" + content
                    return content
        except Exception as e:
            print(f"[UYARI] Gemini API çağrısı başarısız: {str(e)}")

    # 3. Vertex AI Denemesi
    try:
        from contents.views import init_vertex_ai
        from vertexai.generative_models import GenerativeModel
        p_id, loc = init_vertex_ai()
        model = GenerativeModel(f"projects/{p_id}/locations/{loc}/endpoints/981343814604029952")
        response = model.generate_content(full_prompt)
        content = response.text.strip()
        if content:
            if is_test_analysis and ogrenci_tam_ad:
                if not content.startswith(f"Merhaba {ogrenci_tam_ad}"):
                    content = f"Merhaba {ogrenci_tam_ad}, testi başarıyla tamamladığın için tebrik ederim!\n\n" + content
            return content
    except Exception as e:
        print(f"[UYARI] Vertex AI çağrısı başarısız: {str(e)}")

    # 4. Fallback Yanıtı
    if fallback_text:
        return fallback_text

    if is_test_analysis:
        og_name = ogrenci_tam_ad if ogrenci_tam_ad else "Değerli Öğrencimiz"
        return (
            f"Merhaba {og_name},\n\n"
            f"Haftalık değerlendirme testini başarıyla tamamladığın için tebrik ederim! Gösterdiğin çaba ve kararlılık öğrenme sürecinin en değerli parçasıdır.\n\n"
            f"**Genel Değerlendirme:** Testteki sorulara verdiğin yanıtlar konuyu özümseme gayretini gösteriyor. Yanlış cevapladığın kavramları tekrarlayarak eksiklerini rahatlıkla tamamlayabilirsin.\n\n"
            f"**Gelişim Alanları ve İpuçları:** Bilgisayar sistemlerinde veri işlenmemiş ham gerçektir, enformasyon veya bilgi ise bu verilerin işlenip anlam kazandırılmış halidir. Günlük hayatta bir marketteki barkod numaraları tek başına 'veri' iken, gün sonu satış toplamı 'bilgi'dir. Bu ayrımı zihninde canlandırarak konuları pekiştirebilirsin.\n\n"
            f"**Sokratik Düşünme Sorusu:** Sence bir arabanın hız göstergesindeki 90 km/s ifadesi tek başına bir veri midir, yoksa o anki sürüş durumun hakkında bilgi mi verir? Düşüncelerini bir sonraki ünitede pekiştirmeni diler, başarılar dilerim!"
        )
    else:
        query_to_search = user_message or prompt
        return search_knowledge_base_for_chat(query_to_search, chat_history=chat_history)

def generate_test_analysis_report(user, bolum, hafta_konu, dogru_sayisi, yanlis_sayisi, bos_sayisi, toplam_soru, yanlis_soru_id_listesi):
    """
    Test Analiz Raporlama Motoru Ana Çağrı Fonksiyonu.
    Girdileri alır, CSV'den eksik kavramları çıkarır, LLM raporu oluşturur.
    """
    # Öğrenci adı soyadı belirleme
    first_name = getattr(user, 'first_name', '')
    last_name = getattr(user, 'last_name', '')
    if hasattr(user, 'get_full_name') and callable(user.get_full_name):
        ogrenci_tam_ad = user.get_full_name().strip()
    else:
        ogrenci_tam_ad = f"{first_name} {last_name}".strip()

    if not ogrenci_tam_ad:
        ogrenci_tam_ad = getattr(user, 'username', 'Değerli Öğrencimiz')

    # Bölüm bilgisi
    if not bolum:
        if hasattr(user, 'get_department_display') and callable(user.get_department_display):
            bolum = user.get_department_display()
        else:
            bolum = getattr(user, 'department', 'Bilişim Teknolojileri')

    # 1. Adım A: CSV Kavram Çıkarma Servisi
    eksik_kavramlar_blogu = extract_missing_concepts(yanlis_soru_id_listesi)

    # 2. Adım B: LLM Prompt İnşası
    prompt = build_llm_prompt(
        ogrenci_tam_ad=ogrenci_tam_ad,
        bolum=bolum,
        hafta_konu=hafta_konu,
        dogru=dogru_sayisi,
        yanlis=yanlis_sayisi,
        bos=bos_sayisi,
        toplam=toplam_soru,
        eksik_kavramlar_blogu=eksik_kavramlar_blogu
    )

    # 3. LLM Çağrısı
    pedagogical_report = call_openrouter_or_llm(
        prompt=prompt, 
        ogrenci_tam_ad=ogrenci_tam_ad,
        is_test_analysis=True
    )

    basari_orani = round((dogru_sayisi / toplam_soru) * 100, 1) if toplam_soru > 0 else 0.0

    return {
        "ogrenci_tam_ad": ogrenci_tam_ad,
        "bolum": bolum,
        "hafta_konu": hafta_konu,
        "score_summary": {
            "dogru": dogru_sayisi,
            "yanlis": yanlis_sayisi,
            "bos": bos_sayisi,
            "toplam": toplam_soru,
            "basari_orani": basari_orani
        },
        "eksik_kavramlar_blogu": eksik_kavramlar_blogu,
        "pedagogical_report": pedagogical_report
    }
