import os
import time
import sqlite3
import json
import math
from PIL import Image, ImageDraw, ImageOps, ImageFilter

CONFIG_FILE = "bozorov_config.json"
DB_FILE = "bozorov_results.db"
CROPS_DIR = "crops"

os.makedirs(CROPS_DIR, exist_ok=True)


def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_note TEXT,
            total_score REAL,
            correct_count INTEGER,
            wrong_count INTEGER,
            invalid_count INTEGER,
            name_crop_path TEXT,
            annotated_path TEXT,
            details_json TEXT,
            created_at TEXT
        )
    ''')
    conn.commit()
    conn.close()


def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if "scores" in data and "keys" in data and len(data["scores"]) == 35:
                    return data
        except Exception:
            pass

    default_scores = {}
    default_keys = {}
    options_cycle = ["A", "B", "C", "D"]
    for i in range(1, 36):
        q = str(i)
        default_scores[q] = 2.2 if i >= 33 else 1.5
        default_keys[q] = options_cycle[(i - 1) % 4]

    config = {"scores": default_scores, "keys": default_keys}
    save_config(config)
    return config


def save_config(config):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4, ensure_ascii=False)


def save_result_to_db(student_note, total_score, correct_count, wrong_count, invalid_count, name_crop_path, annotated_path, details):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        INSERT INTO results (student_note, total_score, correct_count, wrong_count, invalid_count, name_crop_path, annotated_path, details_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        student_note,
        round(total_score, 2),
        correct_count,
        wrong_count,
        invalid_count,
        name_crop_path,
        annotated_path,
        json.dumps(details, ensure_ascii=False),
        time.strftime("%Y-%m-%d %H:%M:%S")
    ))
    conn.commit()
    conn.close()


def get_saved_results():
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT id, student_note, total_score, correct_count, wrong_count, invalid_count, name_crop_path, annotated_path, created_at FROM results ORDER BY id DESC')
    rows = c.fetchall()
    conn.close()
    return rows


def auto_trim_borders(pil_img):
    """
    Rasm atrofidagi qora/qorong'u fonni (masalan, stol yuzasini) avtomatik aniqlab,
    faqat oq titul qog'ozining o'zini qirqib va tekislab oladi.
    """
    small_w, small_h = 250, 350
    gray_small = pil_img.convert("L").resize((small_w, small_h))
    px = gray_small.load()

    # O'rtacha yorug'likni hisoblaymiz
    total_lum = 0
    for y in range(40, small_h - 40):
        for x in range(30, small_w - 30):
            total_lum += px[x, y]
    avg_lum = total_lum / float((small_h - 80) * (small_w - 60))

    # Oq qog'oz chegarasini topish
    paper_thresh = max(110, int(avg_lum * 0.72))
    min_x, min_y = small_w, small_h
    max_x, max_y = 0, 0

    for y in range(small_h):
        for x in range(small_w):
            if px[x, y] >= paper_thresh:
                if x < min_x: min_x = x
                if x > max_x: max_x = x
                if y < min_y: min_y = y
                if y > max_y: max_y = y

    if (max_x - min_x) > small_w * 0.5 and (max_y - min_y) > small_h * 0.5:
        orig_w, orig_h = pil_img.size
        left = int((min_x / small_w) * orig_w)
        top = int((min_y / small_h) * orig_h)
        right = int((max_x / small_w) * orig_w)
        bottom = int((max_y / small_h) * orig_h)
        pil_img = pil_img.crop((left, top, right, bottom))

    return pil_img.resize((1000, 1400), Image.Resampling.BILINEAR)


def process_sheet(image_path, config, student_note="Talabgor"):
    """
    Android APK uchun C++ kompilyatorisiz (100% Pure Python + Pillow) OMR tekshiruvchi dvigatel.
    35 ta savolni (1-32 A-D, 33-35 A-F) tekshiradi va ism-familiyani qirqib oladi.
    """
    if not os.path.exists(image_path):
        return {"error": f"Rasm topilmadi: {image_path}"}

    try:
        raw_img = Image.open(image_path)
        # Telefon kamerasining EXIF burilishini avtomatik to'g'rilash:
        raw_img = ImageOps.exif_transpose(raw_img).convert("RGB")
    except Exception as e:
        return {"error": f"Rasmni o'qib bo'lmadi: {e}"}

    # Agar rasm yotiq (landscape) olingan bo'lsa, tik holatga keltiramiz
    w, h = raw_img.size
    if w > h:
        raw_img = raw_img.rotate(90, expand=True)

    # 1. Varaqni 1000x1400 standart o'lchamga keltirish
    warped = auto_trim_borders(raw_img)
    ts = int(time.time() * 1000)

    # 2. Ism-familiya blokini qirqib olish (pastki o'ng burchak: X=515..965, Y=935..1245)
    name_crop = warped.crop((515, 935, 965, 1245))
    name_crop_path = os.path.join(CROPS_DIR, f"name_{ts}.jpg")
    name_crop.save(name_crop_path, "JPEG", quality=90)

    # 3. 35 talik test jadvalini qirqib olish (X=47..952, Y=468..895 -> 900x420)
    grid_img = warped.crop((47, 468, 952, 895)).resize((900, 420), Image.Resampling.BILINEAR)
    annotated_grid = grid_img.copy()
    draw = ImageDraw.Draw(annotated_grid)

    # Kontrastni kuchaytirib, kulrang (grayscale) piksellar matritsasini olamiz
    gray_grid = ImageOps.autocontrast(grid_img.convert("L"), cutoff=2)
    # Kichik shovqinlarni tekislash
    gray_grid = gray_grid.filter(ImageFilter.MedianFilter(size=3))
    px = gray_grid.load()

    # 900x420 o'lchamdagi test bloki ichida 5 ta ustun va 7 ta qatorning aniq markazlari:
    col_start_x = [68, 228, 389, 550, 710]
    bubble_dx = 26.2
    row_y = [60, 110, 160, 210, 260, 310, 360]
    r_inner = 9
    r_draw = 12

    scores_cfg = config.get("scores", {})
    keys_cfg = config.get("keys", {})

    total_score = 0.0
    correct_count = 0
    wrong_count = 0
    invalid_count = 0
    details = []

    for col in range(5):
        for row in range(7):
            q_num = col * 7 + row + 1
            q_str = str(q_num)
            options = ["A", "B", "C", "D", "E", "F"] if q_num >= 33 else ["A", "B", "C", "D"]

            q_score = float(scores_cfg.get(q_str, 1.5))
            correct_opt = keys_cfg.get(q_str, "A")

            # Mahalliy fon yorug'ligini aniqlash (shu savol atrofidagi oq qog'oz rangi)
            base_x = int(col_start_x[col])
            base_y = int(row_y[row])
            bg_samples = []
            for sy in range(max(0, base_y - 22), min(420, base_y + 22), 6):
                for sx in range(max(0, base_x - 15), min(900, base_x + 150), 8):
                    bg_samples.append(px[sx, sy])
            bg_samples.sort(reverse=True)
            # Eng yorug' 30% nuqtaning o'rtachasi = toza oq qog'oz yorug'ligi
            top_n = max(1, len(bg_samples) // 3)
            local_paper_lum = sum(bg_samples[:top_n]) / float(top_n)
            dark_threshold = local_paper_lum * 0.72  # Shundan qorong'u piksellar = ruchka siyohi

            fill_ratios = {}
            darkness_scores = {}
            coords = {}

            for idx, opt in enumerate(options):
                cx = int(round(col_start_x[col] + idx * bubble_dx))
                cy = int(round(row_y[row]))
                coords[opt] = (cx, cy)

                dark_pixels = 0
                total_pixels = 0
                lum_sum = 0

                for dy in range(-r_inner, r_inner + 1):
                    for dx in range(-r_inner, r_inner + 1):
                        if dx * dx + dy * dy <= r_inner * r_inner:
                            nx, ny = cx + dx, cy + dy
                            if 0 <= nx < 900 and 0 <= ny < 420:
                                val = px[nx, ny]
                                total_pixels += 1
                                lum_sum += val
                                if val < dark_threshold:
                                    dark_pixels += 1

                total_pixels = max(1, total_pixels)
                fill_ratios[opt] = dark_pixels / float(total_pixels)
                mean_lum = lum_sum / float(total_pixels)
                # Qorayish darajasi (0.0 = oppoq, 1.0 = qop-qora)
                darkness_scores[opt] = max(0.0, (local_paper_lum - mean_lum) / max(1.0, local_paper_lum))

                # Kalibrlash nuqtasi (markazda kichik ko'k nuqta)
                draw.ellipse((cx - 2, cy - 2, cx + 2, cy + 2), fill=(0, 120, 255))

            # Eng ko'p bo'yalgan doirachani aniqlash
            combined = {opt: (fill_ratios[opt] * 0.65 + darkness_scores[opt] * 0.35) for opt in options}
            max_opt = max(combined, key=combined.get)
            max_val = combined[max_opt]
            min_val = min(combined.values())

            marked = []
            # Agar doiracha aniq bo'yalgan bo'lsa (bo'sh doirachalardan kamida 0.16 ga farq qilsa):
            if max_val >= 0.32 and (max_val - min_val) >= 0.15:
                for opt in options:
                    if combined[opt] >= 0.32 and combined[opt] >= max_val * 0.78:
                        marked.append(opt)

            status = ""
            earned = 0.0
            user_ans = "-"

            if len(marked) == 0:
                status = "BELGILANMAGAN"
                wrong_count += 1
                if correct_opt in coords:
                    cx, cy = coords[correct_opt]
                    draw.ellipse((cx - r_draw, cy - r_draw, cx + r_draw, cy + r_draw), outline=(255, 165, 0), width=2)
            elif len(marked) > 1:
                status = "2+ BELGI (0 BALL)"
                user_ans = ",".join(marked)
                invalid_count += 1
                wrong_count += 1
                for m in marked:
                    cx, cy = coords[m]
                    draw.ellipse((cx - r_draw, cy - r_draw, cx + r_draw, cy + r_draw), outline=(220, 38, 38), width=3)
            else:
                user_ans = marked[0]
                if user_ans == correct_opt:
                    status = "TO'G'RI"
                    earned = q_score
                    total_score += earned
                    correct_count += 1
                    cx, cy = coords[user_ans]
                    draw.ellipse((cx - r_draw, cy - r_draw, cx + r_draw, cy + r_draw), outline=(22, 163, 74), width=3)
                else:
                    status = "XATO"
                    wrong_count += 1
                    cx, cy = coords[user_ans]
                    draw.ellipse((cx - r_draw, cy - r_draw, cx + r_draw, cy + r_draw), outline=(220, 38, 38), width=3)
                    if correct_opt in coords:
                        kx, ky = coords[correct_opt]
                        draw.ellipse((kx - r_draw, ky - r_draw, kx + r_draw, ky + r_draw), outline=(22, 163, 74), width=2)

            details.append({
                "q": q_num,
                "user": user_ans,
                "correct": correct_opt,
                "status": status,
                "earned": round(earned, 2),
                "max_score": round(q_score, 2)
            })

    annotated_path = os.path.join(CROPS_DIR, f"checked_{ts}.jpg")
    annotated_grid.save(annotated_path, "JPEG", quality=92)

    save_result_to_db(
        student_note=student_note,
        total_score=total_score,
        correct_count=correct_count,
        wrong_count=wrong_count,
        invalid_count=invalid_count,
        name_crop_path=name_crop_path,
        annotated_path=annotated_path,
        details=details
    )

    return {
        "error": None,
        "total_score": round(total_score, 2),
        "correct_count": correct_count,
        "wrong_count": wrong_count,
        "invalid_count": invalid_count,
        "name_crop_path": os.path.abspath(name_crop_path),
        "annotated_path": os.path.abspath(annotated_path),
        "details": details
    }