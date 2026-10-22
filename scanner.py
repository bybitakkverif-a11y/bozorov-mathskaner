import os
import time
import sqlite3
import json
import zlib
import struct

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


def write_png_pure(path, width, height, rgb_rows):
    """Zapisuje obraz PNG używając wyłącznie wbudowanych bibliotek Pythona (struct + zlib)."""
    raw_data = bytearray()
    for row in rgb_rows:
        raw_data.append(0)  # filter type 0
        raw_data.extend(row)

    def make_chunk(chunk_type, data):
        chunk = struct.pack(">I", len(data)) + chunk_type + data
        crc = zlib.crc32(chunk_type + data) & 0xffffffff
        return chunk + struct.pack(">I", crc)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    compressed = zlib.compress(bytes(raw_data), 6)

    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n")
        f.write(make_chunk(b"IHDR", ihdr))
        f.write(make_chunk(b"IDAT", compressed))
        f.write(make_chunk(b"IEND", b""))


def load_image_grayscale_and_rgb(image_path, target_w=1000, target_h=1400):
    """
    Próbuje wczytać obraz przez Pillow/OpenCV (na PC) lub png (pypng na Androidzie).
    Zwraca przeskalowaną macierz jasności (grayscale) i kolorów RGB.
    """
    # 1. Próba przez Pillow (jeśli dostępne)
    try:
        from PIL import Image, ImageOps
        img = Image.open(image_path)
        img = ImageOps.exif_transpose(img).convert("RGB")
        if img.size[0] > img.size[1]:
            img = img.rotate(90, expand=True)
        img = img.resize((target_w, target_h))
        px = img.load()
        gray = [[0] * target_w for _ in range(target_h)]
        rgb = [bytearray(target_w * 3) for _ in range(target_h)]
        for y in range(target_h):
            row_rgb = rgb[y]
            row_g = gray[y]
            for x in range(target_w):
                r, g, b = px[x, y]
                row_g[x] = (r * 299 + g * 587 + b * 114) // 1000
                idx = x * 3
                row_rgb[idx] = r
                row_rgb[idx + 1] = g
                row_rgb[idx + 2] = b
        return gray, rgb, None
    except Exception:
        pass

    # 2. Próba przez pypng (100% Pure Python dla plików PNG)
    try:
        import png
        reader = png.Reader(filename=image_path)
        w, h, pixels, meta = reader.asRGB8()
        raw_rows = list(pixels)
        gray = [[0] * target_w for _ in range(target_h)]
        rgb = [bytearray(target_w * 3) for _ in range(target_h)]
        for y in range(target_h):
            sy = min(h - 1, int(y * h / target_h))
            src_row = raw_rows[sy]
            row_rgb = rgb[y]
            row_g = gray[y]
            for x in range(target_w):
                sx = min(w - 1, int(x * w / target_w)) * 3
                r, g, b = src_row[sx], src_row[sx + 1], src_row[sx + 2]
                row_g[x] = (r * 299 + g * 587 + b * 114) // 1000
                idx = x * 3
                row_rgb[idx] = r
                row_rgb[idx + 1] = g
                row_rgb[idx + 2] = b
        return gray, rgb, None
    except Exception as e:
        return None, None, f"Format obrazu wymaga PNG lub wsparcia systemowego: {e}"


def draw_circle_rgb(rgb_rows, width, height, cx, cy, radius, color, thickness=2):
    r_col, g_col, b_col = color
    r_out_sq = (radius + thickness) ** 2
    r_in_sq = max(0, radius - thickness) ** 2
    for y in range(max(0, cy - radius - thickness), min(height, cy + radius + thickness + 1)):
        row = rgb_rows[y]
        for x in range(max(0, cx - radius - thickness), min(width, cx + radius + thickness + 1)):
            dist_sq = (x - cx) ** 2 + (y - cy) ** 2
            if r_in_sq <= dist_sq <= r_out_sq:
                idx = x * 3
                row[idx] = r_col
                row[idx + 1] = g_col
                row[idx + 2] = b_col


def process_sheet(image_path, config, student_note="Talabgor"):
    if not os.path.exists(image_path):
        return {"error": f"Rasm topilmadi: {image_path}"}

    ts = int(time.time() * 1000)
    gray, rgb, err = load_image_grayscale_and_rgb(image_path, 1000, 1400)

    # Jeśli obraz to JPEG na Androidzie bez Pillow, kopiujemy oryginał jako podgląd i wykonujemy analizę
    if gray is None:
        return {"error": err or "Rasmni o'qib bo'lmadi."}

    # 1. Wycięcie sekcji Imię i Nazwisko (X: 515..965, Y: 935..1245)
    name_rows = []
    for y in range(935, 1245):
        name_rows.append(rgb[y][515 * 3:965 * 3])
    name_crop_path = os.path.join(CROPS_DIR, f"name_{ts}.png")
    write_png_pure(name_crop_path, 450, 310, name_rows)

    # 2. Wycięcie bloku testowego (X: 47..947, Y: 468..888 -> 900x420)
    grid_w, grid_h = 900, 420
    grid_gray = [[0] * grid_w for _ in range(grid_h)]
    grid_rgb = [bytearray(grid_w * 3) for _ in range(grid_h)]

    for y in range(grid_h):
        sy = 468 + int(y * 427 / grid_h)
        for x in range(grid_w):
            sx = 47 + int(x * 905 / grid_w)
            grid_gray[y][x] = gray[sy][sx]
            s_idx = sx * 3
            d_idx = x * 3
            grid_rgb[y][d_idx] = rgb[sy][s_idx]
            grid_rgb[y][d_idx + 1] = rgb[sy][s_idx + 1]
            grid_rgb[y][d_idx + 2] = rgb[sy][s_idx + 2]

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

            base_x = int(col_start_x[col])
            base_y = int(row_y[row])
            bg_samples = []
            for sy in range(max(0, base_y - 20), min(grid_h, base_y + 20), 5):
                for sx in range(max(0, base_x - 10), min(grid_w, base_x + 140), 8):
                    bg_samples.append(grid_gray[sy][sx])
            bg_samples.sort(reverse=True)
            top_n = max(1, len(bg_samples) // 3)
            local_paper_lum = sum(bg_samples[:top_n]) / float(top_n)
            dark_threshold = local_paper_lum * 0.72

            combined = {}
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
                            if 0 <= nx < grid_w and 0 <= ny < grid_h:
                                val = grid_gray[ny][nx]
                                total_pixels += 1
                                lum_sum += val
                                if val < dark_threshold:
                                    dark_pixels += 1

                total_pixels = max(1, total_pixels)
                fill_ratio = dark_pixels / float(total_pixels)
                mean_lum = lum_sum / float(total_pixels)
                darkness = max(0.0, (local_paper_lum - mean_lum) / max(1.0, local_paper_lum))
                combined[opt] = fill_ratio * 0.65 + darkness * 0.35

            max_opt = max(combined, key=combined.get)
            max_val = combined[max_opt]
            min_val = min(combined.values())

            marked = []
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
                    draw_circle_rgb(grid_rgb, grid_w, grid_h, cx, cy, r_draw, (255, 165, 0), 2)
            elif len(marked) > 1:
                status = "2+ BELGI (0 BALL)"
                user_ans = ",".join(marked)
                invalid_count += 1
                wrong_count += 1
                for m in marked:
                    cx, cy = coords[m]
                    draw_circle_rgb(grid_rgb, grid_w, grid_h, cx, cy, r_draw, (220, 38, 38), 2)
            else:
                user_ans = marked[0]
                if user_ans == correct_opt:
                    status = "TO'G'RI"
                    earned = q_score
                    total_score += earned
                    correct_count += 1
                    cx, cy = coords[user_ans]
                    draw_circle_rgb(grid_rgb, grid_w, grid_h, cx, cy, r_draw, (22, 163, 74), 3)
                else:
                    status = "XATO"
                    wrong_count += 1
                    cx, cy = coords[user_ans]
                    draw_circle_rgb(grid_rgb, grid_w, grid_h, cx, cy, r_draw, (220, 38, 38), 3)
                    if correct_opt in coords:
                        kx, ky = coords[correct_opt]
                        draw_circle_rgb(grid_rgb, grid_w, grid_h, kx, ky, r_draw, (22, 163, 74), 2)

            details.append({
                "q": q_num,
                "user": user_ans,
                "correct": correct_opt,
                "status": status,
                "earned": round(earned, 2),
                "max_score": round(q_score, 2)
            })

    annotated_path = os.path.join(CROPS_DIR, f"checked_{ts}.png")
    write_png_pure(annotated_path, grid_w, grid_h, grid_rgb)

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