import os
import re
from datetime import timedelta
from typing import List, Dict, Any, Set

# Thư mục dữ liệu từ điển tiếng Việt
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
SYLLABLES_FILE = os.path.join(DATA_DIR, "vietnamese_syllables.txt")

# Nạp từ điển âm tiết tiếng Việt chuẩn
VIETNAMESE_SYLLABLES: Set[str] = set()

# Bổ sung tên nhân vật anime thông dụng và khẩu ngữ tiếng Việt
EXTRA_WORDS = {
    "doraemon", "nobita", "shizuka", "jaian", "suneo", "dorami", "dekisugi",
    "ok", "bye", "alo", "ừ", "hả", "nhé", "nè", "ha", "ô", "ơ", "a", "u", "ừm", "ơi", "à", "dạ", "vâng",
    "thôi", "nào", "chứ", "đó", "đây", "kia", "rồi", "chưa", "nhỉ", "nhá", "nghe",
    "chú", "bác", "cô", "dì", "anh", "chị", "em", "con", "cháu", "ông", "bà", "mẹ", "ba",
    "tớ", "cậu", "mình", "chúng", "nó", "họ", "ai", "gì", "sao", "đâu", "nào",
    "chuẩn", "bị", "triển", "khai", "dừng", "lại", "tiến", "hành", "khảo", "sát",
    "tọa", "độ", "mục", "tiêu", "khung", "xin", "hết", "bơi", "thích", "đi", "hơn",
    "thiên", "nhiên", "xanh", "mát", "sáng", "thức", "dậy", "tiếng", "chim", "hót",
    "quả", "nhiên", "núi", "vẫn", "nhất", "đúng", "thỉnh", "thoảng", "đổi", "gió",
    "hay", "hòa", "đều", "quyết", "trái", "tim", "vẽ", "nên", "chiếc", "bản", "đồ",
    "thế", "giới", "đong", "đầy", "những", "giấc", "mơ", "riêng"
}

def _load_syllables():
    global VIETNAMESE_SYLLABLES
    if os.path.exists(SYLLABLES_FILE):
        try:
            with open(SYLLABLES_FILE, "r", encoding="utf-8") as f:
                VIETNAMESE_SYLLABLES = set(line.strip().lower() for line in f if line.strip())
        except Exception:
            pass

    VIETNAMESE_SYLLABLES.update(EXTRA_WORDS)
    # Loại bỏ các từ giới thiệu nước ngoài / credit / logo tránh nhận nhầm
    VIETNAMESE_SYLLABLES.difference_update({"fansub", "mon", "lapis", "t-ducky", "ducky", "matcha", "latte", "tungor"})

_load_syllables()

# Các từ đơn độc lập có nghĩa được phép đứng 1 mình làm câu phụ đề
STANDALONE_WORDS = {
    "hay", "đúng", "khoan", "thôi", "được", "tuyệt", "chuẩn", "chạy", "đi", "a", "hả", "ơi", "ừ", "sao", "gì"
}

# Danh sách ký tự rác sinh ra từ ảo giác cảnh phim
NOISE_SYMBOLS = set("¬~«»§±²³ø¿`^|*\\<>—_#$%=[]{};:⁄ˆ”\"“")

def format_timestamp(seconds: float, vtt: bool = False) -> str:
    """Format seconds to SRT (HH:MM:SS,mmm) or VTT (HH:MM:SS.mmm)"""
    if seconds < 0:
        seconds = 0
    td = timedelta(seconds=seconds)
    total_seconds = int(td.total_seconds())
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    secs = total_seconds % 60
    millis = int((seconds - int(seconds)) * 1000)
    
    sep = "." if vtt else ","
    return f"{hours:02d}:{minutes:02d}:{secs:02d}{sep}{millis:03d}"

def levenshtein_distance(s1: str, s2: str) -> int:
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)
    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    return previous_row[-1]

_diacritic_cache: Dict[str, str] = {}

def correct_vietnamese_diacritics(text: str) -> str:
    if not text:
        return text
    
    def replace_word(match):
        word = match.group(0)
        word_lower = word.lower()
        if len(word) < 3:
            return word
        if word_lower in VIETNAMESE_SYLLABLES:
            return word
            
        if word_lower in _diacritic_cache:
            corrected_lower = _diacritic_cache[word_lower]
        else:
            best_match = None
            best_dist = 3
            # Pre-filter by first letter and length
            candidates = [
                s for s in VIETNAMESE_SYLLABLES
                if abs(len(s) - len(word_lower)) <= 2 and s[0] == word_lower[0]
            ]
            for cand in candidates:
                dist = levenshtein_distance(word_lower, cand)
                if dist < best_dist:
                    best_dist = dist
                    best_match = cand
                    if dist <= 1:
                        break
            
            if best_match and best_dist <= 2:
                corrected_lower = best_match
            else:
                corrected_lower = word_lower
            
            _diacritic_cache[word_lower] = corrected_lower
            
        if corrected_lower == word_lower:
            return word
            
        if word.istitle():
            return corrected_lower.capitalize()
        elif word.isupper():
            return corrected_lower.upper()
        return corrected_lower

    return re.sub(r'[a-zA-ZÀ-ỹ]+', replace_word, text)

def correct_vietnamese_ocr(text: str) -> str:
    """
    Tự động sửa các lỗi nhận diện quang học thường gặp trong phụ đề tiếng Việt:
    - Sửa 'f' thành 't' (như: fiến -> tiến, fhích -> thích, frong -> trong)
    - Sửa lỗi đuôi từ: nhấf -> nhất, hếf -> hết, héfz -> hét
    - Sửa các ký tự lỗi OCR đặc biệt: @f -> bị, Tgi -> Tại, đ đâu -> đi đâu, hon -> hơn, boi -> bơi
    - Sửa các lỗi dấu và từ vựng đặc thù: 0ều -> đều, rổi -> rồi, quyểt -> quyết, chim hét -> chim hót...
    """
    if not text:
        return ""

    # 1. Các biểu tượng và ký tự nhận nhầm đặc thù
    text = text.replace('dqùýê†', '').replace('dqùýê', '')
    text = text.replace('†', '')
    text = re.sub(r'\bChuốôn\b', 'Chuẩn', text)
    text = re.sub(r'\bchuốôn\b', 'chuẩn', text)
    text = re.sub(r'\bdừnà\b', 'dừng', text)
    text = re.sub(r'\bVôn(?=\s+còn\b)', 'Vẫn', text)
    text = re.sub(r'\bvôn(?=\s+còn\b)', 'vẫn', text)
    text = re.sub(r'\btiền(?=\s+(?:tới|hành)\b)', 'tiến', text)
    text = re.sub(r'\bTiền(?=\s+(?:tới|hành)\b)', 'Tiến', text)
    text = re.sub(r'\bkhỏo sót\b', 'khảo sát', text)
    text = re.sub(r'\bKhỏo sót\b', 'Khảo sát', text)
    text = re.sub(r'[@©][fF]', 'bị', text)
    text = re.sub(r'\bTgi\b', 'Tại', text)
    text = re.sub(r'\bđ đâu\b', 'đi đâu', text, flags=re.I)
    text = re.sub(r'\bn[\'’]i\b', 'núi', text, flags=re.I)
    text = re.sub(r'\b0ều\b', 'đều', text, flags=re.I)
    text = re.sub(r'\brổi\b', 'rồi', text, flags=re.I)
    text = re.sub(r'\bquyểt\b', 'quyết', text, flags=re.I)
    text = re.sub(r'\bgiói\b', 'giới', text, flags=re.I)
    text = re.sub(r'\bđong đây\b', 'đong đầy', text, flags=re.I)
    text = re.sub(r'\bchim hét\b', 'chim hót', text, flags=re.I)
    text = re.sub(r'\bdoraemong\b', 'doraemon', text, flags=re.I)
    text = re.sub(r'\bdinn\b', 'định', text, flags=re.I)
    text = re.sub(r'\blàn gi\b', 'làm gì', text, flags=re.I)
    text = re.sub(r'\bnÚi gio\b', 'núi gió', text, flags=re.I)
    text = re.sub(r'\bbản đổ\b', 'bản đồ', text, flags=re.I)

    # 2. fh -> th (Trong tiếng Việt chữ 'fh' không bao giờ tồn tại)
    text = re.sub(r'\bFh', 'Th', text)
    text = re.sub(r'\bFH', 'TH', text)
    text = re.sub(r'fh', 'th', text)
    text = re.sub(r'Fh', 'Th', text)

    # 3. fr -> tr (frong -> trong, frên -> trên, frước -> trước, etc.)
    text = re.sub(r'\bFr', 'Tr', text)
    text = re.sub(r'\bFR', 'TR', text)
    text = re.sub(r'\bfr', 'tr', text)

    # 4. Chữ 'f' đầu từ đứng trước nguyên âm -> đổi thành 't' (loại trừ từ mượn như Fansub, format, film)
    vowels = 'aàáảãạăằắẳẵặâầấẩẫậeèéẻẽẹêềếểễệiìíỉĩịoòóỏõọôồốổỗộơờớởỡợuùúủũụưừứửữựyỳýỷỹỵ'
    def replace_initial_f(m):
        prefix = m.group(1)
        vowel_part = m.group(2)
        word = prefix + vowel_part
        if word.lower().startswith(('fan', 'for', 'fil', 'fac', 'fix', 'foo', 'fee', 'fun', 'fla')):
            return word
        if prefix.isupper():
            return 'T' + vowel_part
        return 't' + vowel_part

    text = re.sub(r'\b([fF])([' + vowels + r']\w*)', replace_initial_f, text)

    # 5. Chữ 'f' hoặc 'fz' ở đuôi từ đứng sau nguyên âm -> đổi thành 't' (hếf -> hết, nhấf -> nhất, héfz -> hét)
    text = re.sub(r'([' + vowels + r'])(?:f|fz)\b', r'\1t', text, flags=re.I)

    # 6. Sửa các lỗi dấu phụ đề phổ biến và cụm từ anime
    text = re.sub(r'\bhon\b', 'hơn', text)
    text = re.sub(r'\bhon([?.!,])', r'hơn\1', text)
    text = re.sub(r'\bboi\b', 'bơi', text)
    text = re.sub(r'\bbiểt\b', 'biết', text)
    text = re.sub(r'\bđâu hon\b', 'đâu hơn', text)
    text = re.sub(r'\bbắt đẩu\b', 'Bắt đầu', text, flags=re.I)
    text = re.sub(r'\bkhail\b', 'khai!', text, flags=re.I)
    text = re.sub(r'\btoa đô\b', 'tọa độ', text, flags=re.I)
    text = re.sub(r'\bmúc tiêu\b', 'mục tiêu', text, flags=re.I)
    text = re.sub(r'\btiên tới\b', 'tiến tới', text, flags=re.I)
    text = re.sub(r'\btiên hành\b', 'tiến hành', text, flags=re.I)
    text = re.sub(r'\bThành Xin hết\b', 'Xin hết!', text, flags=re.I)
    text = re.sub(r'\bVăn còn\b', 'Vẫn còn', text, flags=re.I)
    text = re.sub(r'\bvăn còn\b', 'vẫn còn', text, flags=re.I)
    text = re.sub(r'\bđong đẩy\b', 'đong đầy', text, flags=re.I)
    text = re.sub(r'\bgiắc mơ\b', 'giấc mơ', text, flags=re.I)
    text = re.sub(r'\bquện đi\b', 'quên đi', text, flags=re.I)
    text = re.sub(r'\bLiêu rằng\b', 'Liệu rằng', text, flags=re.I)
    text = re.sub(r'\bThình thoảng\b', 'Thỉnh thoảng', text, flags=re.I)
    text = re.sub(r'\bđổi gia\b', 'đổi gió', text, flags=re.I)
    text = re.sub(r'\bChuẩn bi\b', 'Chuẩn bị', text)
    text = re.sub(r'\bchuẩn bi\b', 'chuẩn bị', text)
    text = re.sub(r'\bCũng đúng nhi\b', 'Cũng đúng nhỉ', text, flags=re.I)
    text = re.sub(r'\bđều rõ\b', 'đều rồi', text, flags=re.I)
    text = re.sub(r'\bChong Chóng Treo\b', 'Chong Chóng Tre', text, flags=re.I)
    text = re.sub(r'\bTUNG MATXA.*$', '', text, flags=re.I)

    return text

# Các từ tiếng Anh dài ảo giác (hallucination) thường gặp của Transformer decoder
ENGLISH_HALLUCINATIONS = {
    "contransitionalization", "contractionalized", "contractionalists", "contransitionalists",
    "complicationalists", "interpressionalized", "interrectionalized", "anticulation",
    "contenderation", "contransitionalism"
}

def is_valid_subtitle_line(line: str) -> bool:
    """
    Kiểm tra một dòng đơn lẻ có phải là dòng phụ đề tiếng Việt hợp lệ hay không.
    Loại bỏ triệt để:
    - Ảo giác tiếng Anh từ Transformer (Contractionalized, Contransitionalists...)
    - Chuỗi lặp từ vô nghĩa do attention loop (THỊ THỊ THỊ THUẬN...)
    - Chuỗi số ID/watermark dài (030100000000990, ID 359.5.36.4...)
    - Dòng không có nguyên âm tiếng Việt hoặc tỷ lệ tiếng Việt quá thấp
    """
    if not line:
        return False
    raw = line.strip()
    if len(raw) < 2:
        return False

    # 1. Loại bỏ các từ tiếng Anh ảo giác (hallucinations)
    lower = raw.lower()
    for hal in ENGLISH_HALLUCINATIONS:
        if hal in lower:
            return False

    # 2. Loại bỏ từ tiếng Anh dài >= 8 ký tự không có dấu tiếng Việt (trừ doraemon...)
    words = re.findall(r'[a-zA-ZÀ-ỹ0-9]+', raw)
    if not words:
        return False

    for w in words:
        w_low = w.lower()
        if len(w) >= 8 and re.match(r'^[a-zA-Z]+$', w) and w_low not in EXTRA_WORDS:
            return False

    # 3. Loại bỏ chuỗi lặp từ (repetition loop, ví dụ: THỊ THỊ THỊ, thuận thuận thuận)
    if len(words) >= 3:
        word_counts = {}
        for w in words:
            wl = w.lower()
            word_counts[wl] = word_counts.get(wl, 0) + 1
        max_rep = max(word_counts.values())
        if max_rep >= 3 and (max_rep / len(words)) >= 0.30:
            return False
        if re.search(r'\b([a-zA-ZÀ-ỹ]+)\s+\1\s+\1\b', raw, flags=re.I):
            return False

    # 4. Loại bỏ watermark ID / dãy số dài liên tiếp (>= 6 chữ số hoặc định dạng IP ID)
    if re.search(r'\b\d{6,}\b', raw) or re.search(r'\bID\s+\d', raw, flags=re.I):
        return False

    # 5. Bắt buộc có nguyên âm tiếng Việt trong các từ
    vowels_pattern = re.compile(r'[aeiouyàáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵ]', re.I)
    has_alpha = False
    for w in words:
        if re.search(r'[a-zA-ZÀ-ỹ]', w):
            has_alpha = True
            if not vowels_pattern.search(w):
                if len(words) <= 2:
                    return False

    if not has_alpha:
        return False

    # 6. Kiểm tra tỷ lệ từ tiếng Việt trong dòng
    valid_count = sum(1 for w in words if w.lower() in VIETNAMESE_SYLLABLES or w.lower() in STANDALONE_WORDS)
    if len(words) >= 3 and (valid_count / len(words)) < 0.35:
        return False

    return True

def is_valid_subtitle(text: str) -> bool:
    """
    Kiểm định ngữ nghĩa tiếng Việt với độ nhạy cao (High Recall):
    - Đảm bảo trích xuất đầy đủ mọi câu thoại tiếng Việt, tên nhân vật, thán từ.
    - Chỉ loại bỏ các chuỗi rác không phải ngôn ngữ người, cảnh nền, hoặc chuỗi ký tự dị dạng.
    """
    if not text:
        return False
        
    special_symbols_count = sum(text.count(c) for c in '†‹„®°™©«»±²³¬§')
    if special_symbols_count >= 3:
        return False
        
    raw = text.strip()
    if len(raw) < 2:
        return False

    # 1. Giới hạn số dòng: Phụ đề phim tối đa 3 dòng (tránh súp rác phân mảnh >= 4 dòng)
    lines = [l.strip() for l in raw.split("\n") if l.strip()]
    if len(lines) > 3:
        return False

    # 2. Loại bỏ các chuỗi phân mảnh đa dòng vô nghĩa (ví dụ: mỗi dòng 1 chữ ngắn như: cá\nLợ, ì\nla, vi\nề)
    if len(lines) >= 2:
        line_word_counts = [len(re.findall(r'[a-zA-ZÀ-ỹ0-9]+', l)) for l in lines]
        total_w = sum(line_word_counts)
        if total_w <= 3 and all(c <= 1 for c in line_word_counts):
            return False

    # 3. Tách các từ ngữ
    words = [w for w in re.findall(r'[a-zA-ZÀ-ỹ0-9]+', raw)]
    if not words:
        return False

    # 4. BẮT BUỘC: Mọi từ chứa chữ cái trong câu đều phải có nguyên âm hợp lệ
    # (Tiếng Việt bắt buộc mọi âm tiết phải có nguyên âm; loại bỏ ngay các từ rác như TL, Sx, xm, Lm, vn, z, f)
    vowels_pattern = re.compile(r'[aeiouyàáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵ]', re.I)
    for w in words:
        if re.search(r'[a-zA-ZÀ-ỹ]', w):
            if not vowels_pattern.search(w):
                return False

    # 5. Kiểm tra từ đơn độc lập (thán từ hoặc từ có nghĩa >= 2 ký tự)
    if len(words) == 1:
        w_clean = words[0].lower()
        if w_clean in STANDALONE_WORDS or (len(w_clean) >= 2 and w_clean in VIETNAMESE_SYLLABLES and vowels_pattern.search(w_clean)):
            return True
        return False

    # 6. Kiểm tra câu ngắn 2 từ (tránh các cặp từ ngẫu nhiên như 'li xý', 'xi vị', 'ì la')
    if len(words) == 2:
        valid_words = [w.lower() in VIETNAMESE_SYLLABLES for w in words]
        total_letters = sum(len(w) for w in words)
        if not all(valid_words):
            return False
        if total_letters <= 4 and not any(w.lower() in STANDALONE_WORDS for w in words):
            return False

    # 7. Loại bỏ các chuỗi chữ lẫn số (ví dụ: 2M, H6, A7, G3, L4 - rác cảnh nền)
    mixed_alphanumeric = sum(1 for w in words if re.search(r'[a-zA-ZÀ-ỹ]', w) and re.search(r'[0-9]', w))
    if mixed_alphanumeric >= 2 or (mixed_alphanumeric >= 1 and len(words) <= 3):
        return False

    # 8. Loại bỏ các chuỗi mà hầu hết là các mảnh vụn 1-2 chữ cái vô nghĩa (như: tì Ế ni, XI Ki Lm ỹ, Là Vi hư z rã lai)
    short_words = sum(1 for w in words if len(w) <= 2)
    if len(words) >= 3 and (short_words / len(words)) >= 0.80:
        return False

    # 9. Kiểm tra từ điển âm tiết tiếng Việt với ngưỡng an toàn cao:
    # - Nếu câu chứa ký tự có dấu tiếng Việt: chỉ cần >= 45% từ khớp từ điển (đề phòng OCR nhận nhầm 1-2 chữ).
    # - Nếu không có dấu: yêu cầu >= 55% từ khớp từ điển.
    diacritics_pattern = re.compile(r'[àáảãạăằắẳẵặâầấẩẫậđèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵ]', re.I)
    has_diacritic = bool(diacritics_pattern.search(raw))

    valid_count = sum(1 for w in words if w.lower() in VIETNAMESE_SYLLABLES or w.lower() in STANDALONE_WORDS)
    vocab_ratio = valid_count / len(words)

    if has_diacritic and vocab_ratio >= 0.45:
        return True

    if vocab_ratio >= 0.55:
        return True

    return False

def clean_subtitle_text(text: str) -> str:
    """
    Làm sạch triệt để văn bản OCR:
    - Loại bỏ toàn bộ dòng rác hallucination (tiếng Anh dài, lặp từ, ID watermark)
    - Loại bỏ toàn bộ ký tự rác và ký tự đặc biệt
    - Nắn chỉnh chính tả OCR tiếng Việt
    - Kiểm định tính toàn vẹn của câu phụ đề
    """
    if not text:
        return ""
    text = text.replace("\r", "").strip()
    text = re.sub(r'[†‹„®°™]', '', text)
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    if len(lines) > 4:
        return ""

    cleaned_lines = []
    for line in lines:
        l = line.strip()
        # Loại bỏ các ký tự rác ở đầu và cuối dòng (bao gồm dấu toán học =+<>~)
        l = re.sub(r'^[=+<>¬~`_^|\-—_.,;:*#\s⁄ˆ”"“]+', '', l)
        l = re.sub(r'[=+<>¬~`_^|\-—_.,;:*#\s⁄ˆ”"“]+$', '', l)
        # Triệt tiêu các ký tự đặc biệt lạ bên trong câu
        l = re.sub(r'[=+<>¬~«»§±²³ø¿`^|*#\\⁄ˆ”"“_;:/\'\[\]{}]+', ' ', l)
        l = re.sub(r'\s+', ' ', l).strip()
        l = correct_vietnamese_ocr(l)
        l = correct_vietnamese_diacritics(l)
        # BỘ LỌC TỪNG DÒNG: Dòng phải hợp lệ mới được đưa vào
        if l and is_valid_subtitle_line(l):
            cleaned_lines.append(l)

    if not cleaned_lines:
        return ""

    candidate = "\n".join(cleaned_lines)
    if is_valid_subtitle(candidate):
        return candidate
    return ""

def write_subtitles_file(subtitles: List[Dict[str, Any]], filepath: str) -> None:
    """Write validated subtitles to .srt or .vtt file"""
    is_vtt = filepath.lower().endswith(".vtt")
    
    with open(filepath, "w", encoding="utf-8") as f:
        if is_vtt:
            f.write("WEBVTT\n\n")
            
        index = 1
        for item in subtitles:
            text = item.get("text", "").strip()
            if not text or not is_valid_subtitle(text):
                continue
                
            start_str = format_timestamp(item["start"], vtt=is_vtt)
            end_str = format_timestamp(item["end"], vtt=is_vtt)
            
            if not is_vtt:
                f.write(f"{index}\n")
            
            f.write(f"{start_str} --> {end_str}\n")
            f.write(f"{text}\n\n")
            index += 1

