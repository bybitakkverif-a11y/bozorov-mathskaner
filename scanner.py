import cv2
import numpy as np
import os
import time
import sqlite3
import json

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


def order_points(pts):
    rect = np.zeros((4, 2), dtype="float32")
    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]
    rect[2] = pts[np.argmax(s)]
    diff = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(diff)]
    rect[3] = pts[np.argmax(diff)]
    return rect


def four_point_transform(image, pts, W, H):
    rect = order_points(pts)
    dst = np.array([[0, 0], [W - 1, 0], [W - 1, H - 1], [0, H - 1]], dtype="float32")
    M = cv2.getPerspectiveTransform(rect, dst)
    return cv2.warpPerspective(image, M, (W, H))


def find_document_quad(image):
    """Kadr ichidan titulning tashqi katta ramkasini topadi."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    edged = cv2.Canny(blur, 40, 140)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    edged = cv2.dilate(edged, kernel, iterations=1)

    cnts, _ = cv2.findContours(edged, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cnts = sorted(cnts, key=cv2.contourArea, reverse=True)

    img_area = image.shape[0] * image.shape[1]
    for c in cnts[:5]:
        area = cv2.contourArea(c)
        if area < img_area * 0.20:
            continue
        peri = cv2.arcLength(c, True)
        approx = cv2.approxPolyDP(c, 0.02 * peri, True)
        if len(approx) == 4:
            return approx.reshape(4, 2)
    return None


def warp_full_sheet(image):
    """1-bosqich: Telefon rasmi yotiq bo'lsa tik qiladi va 1000x1400 o'lchamga tekislaydi."""
    h, w = image.shape[:2]
    if w > h:
        image = cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE)

    W, H = 1000, 1400
    quad = find_document_quad(image)
    if quad is not None:
        return four_point_transform(image, quad, W, H)
    return cv2.resize(image, (W, H))


def extract_test_grid(warped_sheet):
    """
    2-bosqich: 1000x1400 varaq ichidan aynan 35 talik test blokining
    o'z ramkasini topib, 900x420 o'lchamga 100% aniqlikda tekislaydi.
    """
    GW, GH = 900, 420
    gray = cv2.cvtColor(warped_sheet, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (3, 3), 0)
    thresh = cv2.adaptiveThreshold(blur, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 21, 5)

    cnts, _ = cv2.findContours(thresh, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    cnts = sorted(cnts, key=cv2.contourArea, reverse=True)

    for c in cnts:
        area = cv2.contourArea(c)
        if 200000 < area < 580000:
            x, y, w, h = cv2.boundingRect(c)
            aspect = w / float(h)
            if 1.65 < aspect < 3.3 and 330 < y < 630 and w > 720:
                peri = cv2.arcLength(c, True)
                approx = cv2.approxPolyDP(c, 0.02 * peri, True)
                if len(approx) == 4:
                    return four_point_transform(warped_sheet, approx.reshape(4, 2), GW, GH)
                else:
                    pts = np.array([[x, y], [x + w, y], [x + w, y + h], [x, y + h]], dtype="float32")
                    return four_point_transform(warped_sheet, pts, GW, GH)

    fallback_pts = np.array([[47, 468], [952, 468], [952, 895], [47, 895]], dtype="float32")
    return four_point_transform(warped_sheet, fallback_pts, GW, GH)


def process_sheet(image_path, config, student_note="Talabgor"):
    if not os.path.exists(image_path):
        return {"error": f"Rasm topilmadi: {image_path}"}

    file_bytes = np.fromfile(image_path, dtype=np.uint8)
    raw_img = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
    if raw_img is None:
        return {"error": "Rasmni o'qib bo'lmadi. Iltimos, sifatli rasm tanlang."}

    warped = warp_full_sheet(raw_img)
    ts = int(time.time() * 1000)

    # Ism-familiya blokini qirqib olish
    name_crop = warped[935:1245, 515:965]
    name_crop_path = os.path.join(CROPS_DIR, f"name_{ts}.jpg")
    cv2.imwrite(name_crop_path, name_crop)

    # 35 talik test jadvalini qulflab olish
    grid_img = extract_test_grid(warped)
    annotated_grid = grid_img.copy()

    gray_grid = cv2.cvtColor(grid_img, cv2.COLOR_BGR2GRAY)
    blur_grid = cv2.GaussianBlur(gray_grid, (3, 3), 0)

    thresh = cv2.adaptiveThreshold(
        blur_grid, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV, 25, 9
    )

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

            fill_ratios = {}
            coords = {}

            for idx, opt in enumerate(options):
                cx = int(round(col_start_x[col] + idx * bubble_dx))
                cy = int(round(row_y[row]))
                coords[opt] = (cx, cy)

                mask = np.zeros(thresh.shape, dtype="uint8")
                cv2.circle(mask, (cx, cy), r_inner, 255, -1)

                masked_thresh = cv2.bitwise_and(thresh, thresh, mask=mask)
                area_pixels = max(1, cv2.countNonZero(mask))
                fill_ratios[opt] = cv2.countNonZero(masked_thresh) / float(area_pixels)

                cv2.circle(annotated_grid, (cx, cy), 2, (255, 120, 0), -1)

            max_opt = max(fill_ratios, key=fill_ratios.get)
            max_fill = fill_ratios[max_opt]
            min_fill = min(fill_ratios.values())

            marked = []
            if max_fill >= 0.44 and (max_fill - min_fill) >= 0.18:
                for opt in options:
                    if fill_ratios[opt] >= 0.44 and fill_ratios[opt] >= max_fill * 0.80:
                        marked.append(opt)

            status = ""
            earned = 0.0
            user_ans = "-"

            if len(marked) == 0:
                status = "BELGILANMAGAN"
                wrong_count += 1
                if correct_opt in coords:
                    cv2.circle(annotated_grid, coords[correct_opt], r_draw, (0, 180, 255), 2)
            elif len(marked) > 1:
                status = "2+ BELGI (0 BALL)"
                user_ans = ",".join(marked)
                invalid_count += 1
                wrong_count += 1
                for m in marked:
                    cv2.circle(annotated_grid, coords[m], r_draw, (0, 0, 255), 2)
            else:
                user_ans = marked[0]
                if user_ans == correct_opt:
                    status = "TO'G'RI"
                    earned = q_score
                    total_score += earned
                    correct_count += 1
                    cv2.circle(annotated_grid, coords[user_ans], r_draw, (0, 200, 0), 3)
                else:
                    status = "XATO"
                    wrong_count += 1
                    cv2.circle(annotated_grid, coords[user_ans], r_draw, (0, 0, 255), 3)
                    if correct_opt in coords:
                        cv2.circle(annotated_grid, coords[correct_opt], r_draw, (0, 200, 0), 2)

            details.append({
                "q": q_num,
                "user": user_ans,
                "correct": correct_opt,
                "status": status,
                "earned": round(earned, 2),
                "max_score": round(q_score, 2)
            })

    annotated_path = os.path.join(CROPS_DIR, f"checked_{ts}.jpg")
    cv2.imwrite(annotated_path, annotated_grid)

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