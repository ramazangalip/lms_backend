import os
import csv
import json
import re
import requests
from django.conf import settings

_KNOWLEDGE_BASE_CACHE = None

def get_knowledge_base():
    """
    CSV Bilgi Bankasını (D1_Kilavuzlu_YZ_Ajani_Bilgi_Tabani.csv) okur 
    ve sistem performansını korumak için hafızaya (cache) alır.
    """
    global _KNOWLEDGE_BASE_CACHE
    if _KNOWLEDGE_BASE_CACHE is not None:
        return _KNOWLEDGE_BASE_CACHE

    csv_filename = 'D1_Kilavuzlu_YZ_Ajani_Bilgi_Tabani.csv'
    
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
                    # Anahtarları temizle (BOM ve tırnak temizliği)
                    cleaned_row = {k.strip().replace('\ufeff', '').replace('"', ''): (v.strip() if v else '') for k, v in row.items() if k}
                    item_id = cleaned_row.get('id', '').strip()
                    if item_id:
                        kb[item_id] = cleaned_row
        except Exception as e:
            print(f"[HATA] CSV Bilgi bankası (D1_Kilavuzlu_YZ_Ajani_Bilgi_Tabani.csv) okunurken hata oluştu: {str(e)}")

    _KNOWLEDGE_BASE_CACHE = kb
    return _KNOWLEDGE_BASE_CACHE

def find_matching_csv_row(item_id_str, question_text, kb, item_index=1):
    """
    Soru ID'si veya metni üzerinden D1 Kılavuzlu YZ Ajanı Bilgi Tabanında en uygun row'u bulur.
    1. Doğrudan ID eşleşmesi (kb.get(item_id_str))
    2. Soru metni, alternatif sorular veya anahtar kelimeler üzerinden kelime çakışması
    3. Hafta bazlı filtreleme ve sıra indeksi eşleştirmesi
    """
    if not kb:
        return None

    item_id_str = str(item_id_str).strip()
    if item_id_str in kb:
        return kb[item_id_str]

    # 1. Hafta numarasını tespit et (örn: H05-001 -> hafta = 5 veya BT5 -> hafta = 5)
    hafta_num = None
    match_w = re.search(r'H(\d+)', item_id_str, re.IGNORECASE) or re.search(r'BT(\d+)', item_id_str, re.IGNORECASE)
    if match_w:
        try:
            hafta_num = int(match_w.group(1))
        except ValueError:
            pass

    # 2. Soru metni varsa kelime benzerliğiyle arama yap
    if question_text and len(str(question_text).strip()) > 5:
        q_text_clean = re.sub(r'[^\w\s]', ' ', str(question_text).lower())
        tokens = [w for w in q_text_clean.split() if w not in STOP_WORDS and len(w) > 2]
        
        if tokens:
            best_match = None
            best_score = 0
            for k, row in kb.items():
                row_hafta = str(row.get('hafta', '')).strip()
                if hafta_num and row_hafta and row_hafta.isdigit() and int(row_hafta) != hafta_num:
                    continue

                score = 0
                soru_csv = row.get('soru', '').lower()
                alt_sorular = row.get('alternatif_sorular', '').lower()
                konu_csv = row.get('konu', '').lower()
                anahtarlar = row.get('anahtar_kelimeler', '').lower()
                kazanim_csv = row.get('kazanim', '').lower()

                for token in tokens:
                    stem = token[:4] if len(token) >= 4 else token
                    if token in soru_csv or stem in soru_csv:
                        score += 12
                    if token in alt_sorular or stem in alt_sorular:
                        score += 10
                    if token in anahtarlar or stem in anahtarlar:
                        score += 8
                    if token in kazanim_csv or stem in kazanim_csv:
                        score += 6
                    if token in konu_csv or stem in konu_csv:
                        score += 4

                if score > best_score:
                    best_score = score
                    best_match = row

            if best_match and best_score >= 5:
                return best_match

    # 3. Hafta biliniyorsa, o haftanın CSV kayıtları arasından benzersiz sıra indeksi seç
    if hafta_num is not None:
        week_rows = [r for k, r in kb.items() if str(r.get('hafta', '')).strip() in [str(hafta_num), f"{hafta_num:02d}"]]
        if week_rows:
            clean_id = re.sub(r'-D\d+$', '', item_id_str, flags=re.IGNORECASE)
            digits = re.findall(r'\d+', clean_id)
            if len(digits) >= 2:
                q_num = int(digits[-1])
                return week_rows[(q_num + item_index - 1) % len(week_rows)]
            return week_rows[(item_index - 1) % len(week_rows)]

    # 4. Tüm CSV kayıtları arasından benzersiz seçim
    all_rows = list(kb.values())
    if all_rows:
        return all_rows[(item_index - 1) % len(all_rows)]

    return None

def extract_wrong_questions_detailed_guidance(yanlis_soru_id_listesi):
    """
    Öğrencinin haftalık testte yanlış yaptığı her bir soru için D1 Kılavuzlu YZ Ajanı Bilgi Tabanı 
    üzerinden soruya özel 2-3 cümlelik öğretici ve yönlendirici açıklamalar oluşturur.
    """
    if not yanlis_soru_id_listesi:
        return [], "Tüm sorular doğru yanıtlandı, yanlış yapılan soru bulunmamaktadır."

    kb = get_knowledge_base()
    guidance_items = []
    guidance_lines = []

    for idx, item in enumerate(yanlis_soru_id_listesi, 1):
        item_id_str = str(item.get('id') if isinstance(item, dict) else item).strip()
        custom_question_text = item.get('question_text') if isinstance(item, dict) else None
        custom_explanation = item.get('explanation') if isinstance(item, dict) else None

        row = find_matching_csv_row(item_id_str, custom_question_text, kb, item_index=idx)

        if row:
            konu = row.get('konu', '').strip() or "Bilişim Teknolojileri"
            alt_konu = row.get('alt_konu', '').strip()
            kazanim = row.get('kazanim', '').strip() or f"{konu} temel becerileri"
            soru = custom_question_text or row.get('soru', '').strip() or f"Soru {idx}"
            yaygin_hata = row.get('yaygin_hata', '').strip() or "kavram tanımının yanlış yorumlanmasıdır."
            
            ipucu_1 = row.get('ipucu_1_yonlendirici_soru', '').strip()
            ipucu_2 = row.get('ipucu_2_kavram_hatirlatma', '').strip()
            dogrulama = row.get('dogrulama_yaniti_ogrenciye_verilmez', '').strip()
            bilgi_notu = row.get('bilgi_notu_ogrenciye_dogrudan_verilmez', '').strip()

            correct_principle = ipucu_2 if ipucu_2 else (bilgi_notu if bilgi_notu else dogrulama)
            socratic_hint = ipucu_1 if ipucu_1 else "Ders materyalindeki uygulama adımlarını tekrar gözden geçiriniz."

            topic_label = f"{konu} ({alt_konu})" if alt_konu else konu

            sentence1 = f"'{soru}' sorusunda {kazanim} kazanımı ölçülmektedir."
            sentence2 = f"Bu konuda en sık düşülen yaygın hata: {yaygin_hata} Doğru kavramsal ilke ise: {correct_principle}."
            sentence3 = f"Pekiştirmek için Sokratik Yönlendirme: {socratic_hint}"
            
            full_text = f"{sentence1} {sentence2} {sentence3}"

            guidance_items.append({
                "question_index": idx,
                "question_id": item_id_str,
                "konu": topic_label,
                "soru": soru,
                "guidance_text": full_text
            })
            guidance_lines.append(f"📌 **Soru {idx} [{topic_label}]:** {full_text}")
        elif custom_explanation:
            full_text = custom_explanation.strip()
            guidance_items.append({
                "question_index": idx,
                "question_id": item_id_str,
                "konu": "Test Sorusu",
                "soru": custom_question_text or f"Soru {idx}",
                "guidance_text": full_text
            })
            guidance_lines.append(f"📌 **Soru {idx}:** {full_text}")
        else:
            q_label = custom_question_text if custom_question_text else f"Soru {item_id_str}"
            full_text = f"'{q_label}' sorusunda ölçülen temel kavramların ve uygulama adımlarının tekrar incelenmesi önerilir. Soruyu yanıtlarken teorik gerekçeye ve kavram tanımına dikkat ediniz. İlgili haftanın ders materyallerini gözden geçirerek bilginizi pekiştirebilirsiniz."
            guidance_items.append({
                "question_index": idx,
                "question_id": item_id_str,
                "konu": "Bilişim Teknolojileri",
                "soru": q_label,
                "guidance_text": full_text
            })
            guidance_lines.append(f"📌 **Soru {idx}:** {full_text}")

    guidance_block = "\n\n".join(guidance_lines)
    return guidance_items, guidance_block

def extract_missing_concepts(yanlis_soru_id_listesi):
    """
    Öğrencinin yanlış yaptığı soru ID'lerini D1 Kılavuzlu YZ Ajanı Bilgi Tabanı ile eşleştirerek 
    eksik kavramlar, kazanımlar ve yaygın yanılgılar bloğunu oluşturur.
    """
    if not yanlis_soru_id_listesi:
        return "Tüm sorular doğru yanıtlandı, kavram yanılgısı tespit edilmedi."

    kb = get_knowledge_base()
    concept_lines = []

    for item in yanlis_soru_id_listesi:
        item_id_str = str(item.get('id') if isinstance(item, dict) else item).strip()
        custom_q = item.get('question_text') if isinstance(item, dict) else None
        
        row = find_matching_csv_row(item_id_str, custom_q, kb)
        if row:
            konu = row.get('konu', '').strip()
            alt_konu = row.get('alt_konu', '').strip()
            kazanim = row.get('kazanim', '').strip()
            yaygin_hata = row.get('yaygin_hata', '').strip()
            anahtar_kelimeler = row.get('anahtar_kelimeler', '').strip()
            
            topic_str = f"{konu} - {alt_konu}" if alt_konu else konu
            line = f"- Konu: {topic_str} | Kazanım: {kazanim} | Sık Yapılan Hata: {yaygin_hata} | Anahtar Kavramlar: {anahtar_kelimeler}"
            concept_lines.append(line)
        else:
            q_label = custom_q if custom_q else item_id_str
            concept_lines.append(f"- Soru: {q_label} | Temel Bilişim Teknolojileri kavramı incelendi.")

    if not concept_lines:
        return "Tüm sorular doğru yanıtlandı, kavram yanılgısı tespit edilmedi."

    return "\n".join(concept_lines)

def build_llm_prompt(ogrenci_tam_ad, bolum, hafta_konu, dogru, yanlis, bos, toplam, eksik_kavramlar_blogu, soru_yonlendirmeleri_blogu=""):
    """
    D1 Kılavuzlu YZ Ajanı Bilgi Tabanı ilkelerine dayalı System Prompt şablonunu oluşturur.
    """
    basari_orani = round((dogru / toplam) * 100, 1) if toplam > 0 else 0.0

    prompt = f"""ROL VE MİSYON:
Sen üniversite düzeyindeki Bilgi Teknolojilerine Giriş dersi için 'D1 Kılavuzlu YZ Öğrenme Ajanı' ilkelerine dayalı, rehberli ve öğrenci odaklı bir Akademik Ölçme-Değerlendirme Asistanısın.
Tüm analizlerin ve yönlendirmelerin D1 Kılavuzlu Bilgi Tabanı ('D1_Kilavuzlu_YZ_Ajani_Bilgi_Tabani.csv') müfredatına, kavramsal hiyerarşiye ve pedagojik ilkelere tam uyumlu olmalıdır.

DEĞERLENDİRİLECEK VERİLER:
- Öğrenci: {ogrenci_tam_ad}
- Bölüm: {bolum}
- Hafta / Konu: {hafta_konu}
- Test Skoru: {dogru} Doğru, {yanlis} Yanlış, {bos} Boş (Toplam: {toplam} Soru | Başarı Oranı: %{basari_orani})
- Tespit Edilen Eksik Kavramlar ve Yanılgılar (D1 Bilgi Tabanından):
{eksik_kavramlar_blogu}

- Yanlış Yapılan Sorular ve D1 Kılavuzlu Yönlendirmeler:
{soru_yonlendirmeleri_blogu}

PEDAGOJİK VE BİÇİMSEL KURALLAR:
1. İLK CÜMLE VE TEBRİK ZORUNLULUĞU:
Metne MUTLAKA ve İSTİSNASIZ olarak "Merhaba {ogrenci_tam_ad}," hitabıyla başla. Öğrenciyi testi tamamladığı için samimi ve teşvik edici bir dille tebrik et.
2. GENEL PERFORMANS VE ÜSTBİLİŞSEL EMEK DEĞERLENDİRMESİ:
Öğrencinin başarı yüzdesini ve harcadığı gayreti değerlendir. Ne kadar bildiğini doğru değerlendirme (kalibrasyon) becerisini destekleyecek motive edici bir özet sun.
3. YANLIŞ YAPILAN HER SORUYA ÖZEL 2-3 CÜMLELİK KILAVUZLU YÖNLENDİRME:
Öğrencinin yanlış yaptığı HER BİR soru için (yukarıdaki D1 Bilgi Tabanı yönlendirmelerine dayanarak) tam 2-3 cümlelik özgün, öğretici ve yönlendirici bir açıklama yap. Asla tüm sorulara aynı jenerik kalıbı tekrarlama; soruya, konuya ve yaygın hataya özel açıklamalar ver.
4. D1 SOKRATİK DÜŞÜNME SORUSU VE KAPANIŞ:
Analizin sonuna, öğrencinin eksik kaldığı anahtar kavramı düşünerek keşfetmesini sağlayacak tek bir Sokratik yönlendirme sorusu (D1 Kılavuzlu İpucu ruhunda) ekle ve gelecek haftadaki ders için başarı dileğiyle tamamla."""

    return prompt

STOP_WORDS = {'de', 'da', 'te', 'ta', 'nasıl', 'yapılır', 'nedir', 'ne', 'için', 've', 'ile', 'bir', 'bu', 'şu', 'o', 'var', 'yok', 'mi', 'mı', 'mu', 'mü', 'nelerdir'}

def search_knowledge_base_for_chat(user_message, chat_history=None):
    """
    LLM servisleri erişilemez olduğunda D1 Kılavuzlu YZ Ajanı Bilgi Tabanı (D1_Kilavuzlu_YZ_Ajani_Bilgi_Tabani.csv) 
    üzerinden öğrencinin sorusuna kılavuzlu/rehberli ve öğretici yanıt arar.
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
            "Excel'de hücre birleştirmek için D1 Kılavuzlu adımlar:\n\n"
            "1. Yönlendirici İpucu: Birleştirmek istediğiniz hücreleri fare ile seçin (örneğin A1 ve B1).\n"
            "2. Kavram Hatırlatma: Üst menüdeki **Giriş (Home)** sekmesine tıklayın.\n"
            "3. Uygulama Adımı: **Hizalama (Alignment)** grubunda yer alan **Birleştir ve Ortala (Merge & Center)** düğmesine basın.\n\n"
            "⚠️ Yaygın Hata Uyarısı: Birleştirme yaptığınızda sadece sol üstteki hücrenin verisi korunur, diğer hücrelerdeki veriler silinebilir!"
        )

    # Word Yazı Kalınlaştırma / Biçimlendirme Kontrolü
    if "word" in msg_lower and ("kalın" in msg_lower or "bold" in msg_lower or "kalınlaş" in msg_lower):
        return (
            "Microsoft Word'de yazıyı kalınlaştırmak için D1 Kılavuzlu adımlar:\n\n"
            "1. Kalınlaştırmak istediğiniz metni fare ile seçin.\n"
            "2. Üst menüdeki **Giriş (Home)** sekmesinde yer alan **K** (Bold - Kalın) simgesine tıklayın.\n"
            "3. Veya klavye kısayolu olarak **Ctrl + B** (Türkçe sürümlerde **Ctrl + K**) tuşlarına basın."
        )

    # Akıllı D1 CSV Bilgi Bankası Taraması
    kb = get_knowledge_base()
    if not kb:
        return f"Sorunuz ('{user_message}') alındı! Bilgi Teknolojileri ders materyallerini inceleyerek çalışmalarınıza devam edebilirsiniz."

    # Noktalama ve temizleme
    clean_query = re.sub(r'[^\w\s]', ' ', msg_lower, flags=re.UNICODE)
    tokens = [w for w in clean_query.split() if w not in STOP_WORDS and len(w) > 1]
    
    if not tokens:
        return f"Sorunuz ('{user_message}') alındı! Bilgi Teknolojileri ders materyallerini inceleyebilirsiniz."

    matches = []
    for item_id, row in kb.items():
        soru = row.get('soru', '').lower()
        alt_sorular = row.get('alternatif_sorular', '').lower()
        konu = row.get('konu', '').lower()
        anahtarlar = row.get('anahtar_kelimeler', '').lower()
        kazanim = row.get('kazanim', '').lower()
        
        score = 0
        for token in tokens:
            stem = token[:4] if len(token) >= 4 else token
            if token in soru or stem in soru:
                score += 12
            if token in alt_sorular or stem in alt_sorular:
                score += 10
            if token in anahtarlar or stem in anahtarlar:
                score += 8
            if token in kazanim or stem in kazanim:
                score += 6
            if token in konu or stem in konu:
                score += 4

        # D1 Kılavuzlu İçerik İnşası
        ipucu1 = row.get('ipucu_1_yonlendirici_soru', '').strip()
        ipucu2 = row.get('ipucu_2_kavram_hatirlatma', '').strip()
        ipucu3 = row.get('ipucu_3_benzer_ornek', '').strip()
        ipucu4 = row.get('ipucu_4_adim_adim', '').strip()
        yaygin_hata = row.get('yaygin_hata', '').strip()
        bilgi_notu = row.get('bilgi_notu_ogrenciye_dogrudan_verilmez', '').strip() or row.get('dogrulama_yaniti_ogrenciye_verilmez', '').strip()

        parts = []
        if ipucu1:
            parts.append(f"💡 **Yönlendirici Soru:** {ipucu1}")
        if ipucu2:
            parts.append(f"📖 **Kavram Hatırlatma:** {ipucu2}")
        if ipucu3:
            parts.append(f"🔍 **Benzer Örnek:** {ipucu3}")
        if ipucu4:
            parts.append(f"🛠️ **Adım Adım Çözüm:** {ipucu4}")
        if bilgi_notu and len(parts) < 2:
            parts.append(f"📝 **Bilgi Notu:** {bilgi_notu}")
        if yaygin_hata:
            parts.append(f"⚠️ **Yaygın Yanılgı:** {yaygin_hata}")

        answer = "\n\n".join(parts)

        if score > 0 and answer and len(answer.strip()) > 10:
            matches.append((score, row, answer.strip()))

    if matches:
        matches.sort(key=lambda x: x[0], reverse=True)
        best_score, best_row, best_answer = matches[0]
        if best_score >= 4:
            topic = best_row.get('konu', '')
            alt = best_row.get('alt_konu', '')
            header_str = f"**{topic} ({alt})**" if alt else f"**{topic}**"
            prefix = f"D1 Kılavuzlu Bilgi Tabanından {header_str} konusuna ilişkin rehberlik:\n\n"
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
    Girdileri alır, D1 CSV'den eksik kavramları çıkarır, D1 Kılavuzlu LLM raporu oluşturur.
    """
    first_name = getattr(user, 'first_name', '')
    last_name = getattr(user, 'last_name', '')
    if hasattr(user, 'get_full_name') and callable(user.get_full_name):
        ogrenci_tam_ad = user.get_full_name().strip()
    else:
        ogrenci_tam_ad = f"{first_name} {last_name}".strip()

    if not ogrenci_tam_ad:
        ogrenci_tam_ad = getattr(user, 'username', 'Değerli Öğrencimiz')

    if not bolum:
        if hasattr(user, 'get_department_display') and callable(user.get_department_display):
            bolum = user.get_department_display()
        else:
            bolum = getattr(user, 'department', 'Bilişim Teknolojileri')

    # 1. Adım A: CSV Kavram Çıkarma Servisi
    eksik_kavramlar_blogu = extract_missing_concepts(yanlis_soru_id_listesi)

    # 1. Adım A2: Yanlış sorulara özel 2-3 cümlelik yönlendirme çıkarma
    guidance_items, soru_yonlendirmeleri_blogu = extract_wrong_questions_detailed_guidance(yanlis_soru_id_listesi)

    # 2. Adım B: LLM Prompt İnşası
    prompt = build_llm_prompt(
        ogrenci_tam_ad=ogrenci_tam_ad,
        bolum=bolum,
        hafta_konu=hafta_konu,
        dogru=dogru_sayisi,
        yanlis=yanlis_sayisi,
        bos=bos_sayisi,
        toplam=toplam_soru,
        eksik_kavramlar_blogu=eksik_kavramlar_blogu,
        soru_yonlendirmeleri_blogu=soru_yonlendirmeleri_blogu
    )

    fallback_report = None
    if yanlis_sayisi > 0:
        fallback_report = (
            f"Merhaba {ogrenci_tam_ad},\n\n"
            f"Haftalık değerlendirme testini başarıyla tamamladığın için tebrik ederim! Gösterdiğin çaba ve kararlılık öğrenme sürecinin en değerli parçasıdır.\n\n"
            f"**Genel Değerlendirme:** Testteki sorulara verdiğin yanıtlar konuyu özümseme gayretini gösteriyor. Yanlış cevapladığın soruları aşağıda yer alan D1 Kılavuzlu yönlendirmelerle tekrarlayarak eksiklerini rahatlıkla tamamlayabilirsin.\n\n"
            f"**Yanlış Yapılan Sorulara Özel D1 Kılavuzlu Yönlendirmeler:**\n{soru_yonlendirmeleri_blogu}\n\n"
            f"**Sokratik Düşünme Sorusu:** Sence bu haftaki sorularda karşılaştığın kavramlar günlük hayatındaki dijital araçlarda nasıl karşılık buluyor? Düşüncelerini bir sonraki ünitede pekiştirmeni diler, başarılar dilerim!"
        )

    # 3. LLM Çağrısı
    pedagogical_report = call_openrouter_or_llm(
        prompt=prompt, 
        ogrenci_tam_ad=ogrenci_tam_ad,
        is_test_analysis=True,
        fallback_text=fallback_report
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
        "wrong_questions_guidance": guidance_items,
        "pedagogical_report": pedagogical_report
    }
