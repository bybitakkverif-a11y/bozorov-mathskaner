import flet as ft
import asyncio
import os
import time
import base64
from scanner import (
    load_config,
    save_config,
    process_sheet,
    get_saved_results,
    init_db
)


def image_to_base64(path):
    """Rasmni Android APK ekranida 100% ko'rinishi uchun Base64 formatga o'giradi."""
    if not path or not os.path.exists(path):
        return ""
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def make_image_widget(path, height=150):
    b64 = image_to_base64(path)
    if not b64:
        return ft.Text("Rasm topilmadi", size=11, color="#DC2626")
    try:
        return ft.Image(src_base64=b64, height=height)
    except Exception:
        return ft.Image(src=f"data:image/jpeg;base64,{b64}", height=height)


def make_button(text, on_click, bgcolor="#2563EB", text_color="white", expand=False, height=44, width=None, font_size=13):
    return ft.Container(
        content=ft.Row(
            alignment=ft.MainAxisAlignment.CENTER,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Text(text, color=text_color, weight=ft.FontWeight.BOLD, size=font_size)
            ],
        ),
        bgcolor=bgcolor,
        padding=10,
        border_radius=8,
        height=height,
        width=width,
        expand=expand,
        ink=True,
        on_click=on_click,
    )


def main(page: ft.Page):
    init_db()
    config = load_config()

    page.title = "Bozorov Math - Milliy Sertifikat OMR Skaner"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.padding = 0
    page.bgcolor = "#FFFFFF"

    try:
        page.window.width = 450
        page.window.height = 850
    except Exception:
        pass

    # ==========================================================
    # 1. LOADING (SPLASH) EKRANI - @Bozorovmath & BM SAT Math
    # ==========================================================
    splash_view = ft.Container(
        expand=True,
        bgcolor="#0F172A",
        padding=25,
        content=ft.Column(
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            expand=True,
            spacing=14,
            controls=[
                ft.Container(
                    width=110,
                    height=110,
                    border_radius=55,
                    bgcolor="#2563EB",
                    content=ft.Column(
                        alignment=ft.MainAxisAlignment.CENTER,
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            ft.Text("BM", size=42, weight=ft.FontWeight.BOLD, color="white")
                        ],
                    ),
                ),
                ft.Text("BOZOROV MATH", size=28, weight=ft.FontWeight.BOLD, color="white"),
                ft.Text("Milliy Sertifikat OMR Skaneri", size=15, color="#94A3B8"),
                ft.Container(height=10),
                ft.ProgressRing(width=38, height=38, stroke_width=3, color="#38BDF8"),
                ft.Text("Ilova yuklanmoqda...", size=13, color="#CBD5E1"),
                ft.Container(height=20),
                ft.Container(
                    padding=16,
                    border_radius=12,
                    bgcolor="#1E293B",
                    width=340,
                    content=ft.Column(
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=8,
                        controls=[
                            ft.Text("Rasmiy kanallarimizga obuna bo'ling:", size=12, color="#94A3B8"),
                            ft.Text("📢 Telegram: @Bozorovmath", size=15, weight=ft.FontWeight.BOLD, color="#38BDF8"),
                            ft.Text("▶️ YouTube: BM SAT Math", size=15, weight=ft.FontWeight.BOLD, color="#F87171"),
                        ],
                    ),
                ),
            ],
        ),
    )

    # ==========================================================
    # 2. ASOSIY ILOVA QISMLARI
    # ==========================================================
    student_note_input = ft.TextField(
        label="Talabgor eslatmasi (ixtiyoriy, masalan: 1-guruh)",
        height=44,
        text_size=13,
    )

    status_banner = ft.Text(
        "Yashil tugmani bosib titulni rasmga oling yoki galereyadan tanlang.",
        size=13,
        color="#475569",
        weight=ft.FontWeight.BOLD
    )
    result_summary_card = ft.Column(spacing=10)
    details_list_column = ft.Column(spacing=4, scroll=ft.ScrollMode.AUTO, height=250)

    def render_scan_results(res):
        if res.get("error"):
            status_banner.value = f"❌ {res['error']}"
            status_banner.color = "#DC2626"
            page.update()
            return

        status_banner.value = "✅ Tekshiruv yakunlandi va natija saqlandi!"
        status_banner.color = "#16A34A"

        result_summary_card.controls.clear()
        result_summary_card.controls.append(
            ft.Container(
                padding=12,
                border_radius=10,
                bgcolor="#F1F5F9",
                content=ft.Column(
                    spacing=8,
                    controls=[
                        ft.Text(f"UMUMIY BALL: {res['total_score']}", size=24, weight=ft.FontWeight.BOLD, color="#1D4ED8"),
                        ft.Row(
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                            controls=[
                                ft.Text(f"To'g'ri: {res['correct_count']} ta", color="#16A34A", weight=ft.FontWeight.BOLD),
                                ft.Text(f"Xato: {res['wrong_count']} ta", color="#DC2626", weight=ft.FontWeight.BOLD),
                                ft.Text(f"2+ belgi: {res['invalid_count']} ta", color="#D97706", weight=ft.FontWeight.BOLD),
                            ],
                        ),
                        ft.Divider(height=8),
                        ft.Text("1. Tekshirilgan 35 talik test bloki:", size=12, weight=ft.FontWeight.BOLD),
                        make_image_widget(res["annotated_path"], height=190),
                        ft.Text("2. Tituldagi Ism-Familiya qismi (avto-qirqim):", size=12, weight=ft.FontWeight.BOLD),
                        make_image_widget(res["name_crop_path"], height=95),
                    ],
                ),
            )
        )

        details_list_column.controls.clear()
        for item in res["details"]:
            is_ok = item["status"] == "TO'G'RI"
            row_bg = "#DCFCE7" if is_ok else "#FEE2E2"
            txt_col = "#15803D" if is_ok else "#B91C1C"
            details_list_column.controls.append(
                ft.Container(
                    padding=8,
                    border_radius=6,
                    bgcolor=row_bg,
                    content=ft.Row(
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        controls=[
                            ft.Text(f"{item['q']}-savol", weight=ft.FontWeight.BOLD, size=13),
                            ft.Text(f"Belgi: {item['user']} | Kalit: {item['correct']}", size=12),
                            ft.Text(f"+{item['earned']} ball", weight=ft.FontWeight.BOLD, color=txt_col, size=13),
                        ],
                    ),
                )
            )

        refresh_history()
        page.update()

    def run_omr_on_path(file_path):
        status_banner.value = "⏳ Titul tahlil qilinmoqda, kuting..."
        status_banner.color = "#D97706"
        page.update()
        note = (student_note_input.value or "").strip() or "Talabgor"
        res = process_sheet(file_path, config, student_note=note)
        render_scan_results(res)

    # Android APK va Kompyuter uchun FilePicker
    def on_file_picked(e):
        if e.files and len(e.files) > 0:
            fpath = getattr(e.files[0], "path", None)
            if fpath and os.path.exists(fpath):
                run_omr_on_path(fpath)
            else:
                status_banner.value = "⚠️ Fayl yo'li topilmadi."
                page.update()

    file_picker = None
    try:
        file_picker = ft.FilePicker(on_result=on_file_picked)
        page.overlay.append(file_picker)
    except Exception:
        file_picker = None

    def scan_button_clicked(e):
        if file_picker is not None and hasattr(file_picker, "pick_files"):
            try:
                file_picker.pick_files(allow_multiple=False)
                return
            except Exception:
                pass

        # Faqat kompyuterda Flet 1.0.5 uchun zaxira oyna:
        try:
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            path = filedialog.askopenfilename(
                title="Titul varaqasi rasmini tanlang",
                filetypes=[("Rasmlar", "*.jpg *.jpeg *.png *.bmp *.webp"), ("Barcha fayllar", "*.*")]
            )
            root.destroy()
            if path:
                run_omr_on_path(path)
        except Exception as ex:
            status_banner.value = f"Xatolik: {ex}"
            page.update()

    # ==========================================================
    # TAB 1: SKANERLASH
    # ==========================================================
    scanner_tab_content = ft.Container(
        padding=12,
        expand=True,
        content=ft.Column(
            scroll=ft.ScrollMode.AUTO,
            spacing=10,
            controls=[
                student_note_input,
                make_button(
                    "📷 SKANERLASH (KAMERA YOKI GALEREYA)",
                    scan_button_clicked,
                    bgcolor="#16A34A",
                    height=50,
                    font_size=14
                ),
                status_banner,
                result_summary_card,
                ft.Text("Savollar kesimida tahlil (1-35):", weight=ft.FontWeight.BOLD, size=14),
                details_list_column,
            ],
        ),
    )

    # ==========================================================
    # TAB 2: 35 TA SAVOL UCHUN KALIT VA BALL SOZLAMALARI
    # ==========================================================
    score_inputs = {}
    selected_keys = {}
    key_btn_groups = {}
    settings_status = ft.Text("", size=13, color="#16A34A", weight=ft.FontWeight.BOLD)
    questions_config_column = ft.Column(spacing=6, scroll=ft.ScrollMode.AUTO, height=430)

    def select_key_option(q_str, opt):
        selected_keys[q_str] = opt
        for o, btn in key_btn_groups[q_str].items():
            if o == opt:
                btn.bgcolor = "#2563EB"
                btn.content.controls[0].color = "white"
            else:
                btn.bgcolor = "#E2E8F0"
                btn.content.controls[0].color = "#1E293B"
        page.update()

    for i in range(1, 36):
        q_str = str(i)
        opts = ["A", "B", "C", "D", "E", "F"] if i >= 33 else ["A", "B", "C", "D"]
        current_key = config["keys"].get(q_str, "A")
        if current_key not in opts:
            current_key = "A"
        selected_keys[q_str] = current_key
        key_btn_groups[q_str] = {}

        opt_buttons_row = ft.Row(spacing=4)
        for o in opts:
            is_sel = (o == current_key)
            btn = make_button(
                text=o,
                on_click=lambda e, q=q_str, opt=o: select_key_option(q, opt),
                bgcolor="#2563EB" if is_sel else "#E2E8F0",
                text_color="white" if is_sel else "#1E293B",
                height=32,
                width=28,
                font_size=12,
            )
            key_btn_groups[q_str][o] = btn
            opt_buttons_row.controls.append(btn)

        tf = ft.TextField(
            value=str(config["scores"].get(q_str, 1.5)),
            width=75,
            height=38,
            text_size=13,
            label="Ball",
        )
        score_inputs[q_str] = tf

        questions_config_column.controls.append(
            ft.Container(
                padding=8,
                border_radius=8,
                bgcolor="#F8FAFC",
                content=ft.Row(
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    controls=[
                        ft.Text(f"{i}-savol", weight=ft.FontWeight.BOLD, size=13, width=62),
                        opt_buttons_row,
                        tf,
                    ],
                ),
            )
        )

    bulk_1_32 = ft.TextField(label="1-32 balli", value="1.5", width=95, height=40, text_size=12)
    bulk_33_35 = ft.TextField(label="33-35 balli", value="2.2", width=95, height=40, text_size=12)

    def apply_bulk_scores(e):
        for i in range(1, 33):
            score_inputs[str(i)].value = bulk_1_32.value
        for i in range(33, 36):
            score_inputs[str(i)].value = bulk_33_35.value
        settings_status.value = "⚡ Ballar kataklarga yozildi! Endi 'Saqlash' tugmasini bosing."
        settings_status.color = "#2563EB"
        page.update()

    def save_all_settings(e):
        new_scores = {}
        new_keys = {}
        for i in range(1, 36):
            q_str = str(i)
            val_str = (score_inputs[q_str].value or "1.0").replace(",", ".").strip()
            try:
                new_scores[q_str] = float(val_str)
            except ValueError:
                new_scores[q_str] = 1.0
            new_keys[q_str] = selected_keys.get(q_str, "A")

        config["scores"] = new_scores
        config["keys"] = new_keys
        save_config(config)
        settings_status.value = "✅ Barcha 35 ta savol ballari va kalitlari saqlandi!"
        settings_status.color = "#16A34A"
        page.update()

    settings_tab_content = ft.Container(
        padding=12,
        expand=True,
        content=ft.Column(
            spacing=8,
            controls=[
                ft.Text("Har bir savol uchun to'g'ri kalitni va ballni belgilang:", size=13, weight=ft.FontWeight.BOLD),
                ft.Row(
                    spacing=8,
                    controls=[
                        bulk_1_32,
                        bulk_33_35,
                        make_button("⚡ Tezkor to'ldirish", apply_bulk_scores, bgcolor="#475569", expand=True, height=40, font_size=12),
                    ],
                ),
                make_button("💾 Barcha 35 ta savol sozlamasini saqlash", save_all_settings, bgcolor="#16A34A", height=42),
                settings_status,
                questions_config_column,
            ],
        ),
    )

    # ==========================================================
    # TAB 3: SAQLANGAN NATIJALAR TARIXI
    # ==========================================================
    history_column = ft.Column(spacing=8, scroll=ft.ScrollMode.AUTO, height=520)

    def refresh_history():
        history_column.controls.clear()
        rows = get_saved_results()
        if not rows:
            history_column.controls.append(ft.Text("Hozircha saqlangan natijalar yo'q.", size=13, color="#64748B"))
            return

        for r in rows:
            rec_id, note, score, corr, wrg, inv, crop_p, ann_p, dt = r
            history_column.controls.append(
                ft.Container(
                    padding=10,
                    border_radius=10,
                    bgcolor="#F1F5F9",
                    content=ft.Column(
                        spacing=6,
                        controls=[
                            ft.Row(
                                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                                controls=[
                                    ft.Text(f"#{rec_id} | {note}", weight=ft.FontWeight.BOLD, size=14),
                                    ft.Text(f"{score} ball", weight=ft.FontWeight.BOLD, size=16, color="#1D4ED8"),
                                ],
                            ),
                            ft.Text(f"To'g'ri: {corr} | Xato: {wrg} (2+ belgi: {inv}) | Vaqt: {dt}", size=11, color="#475569"),
                            make_image_widget(crop_p, height=75),
                        ],
                    ),
                )
            )

    refresh_history()

    history_tab_content = ft.Container(
        padding=12,
        expand=True,
        content=ft.Column(
            spacing=10,
            controls=[
                ft.Row(
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    controls=[
                        ft.Text("Saqlangan natijalar bazasi:", weight=ft.FontWeight.BOLD, size=14),
                        make_button("🔄 Yangilash", lambda _: (refresh_history(), page.update()), bgcolor="#334155", height=34, width=110, font_size=12),
                    ],
                ),
                history_column,
            ],
        ),
    )

    # ==========================================================
    # YUQORI HEADER VA NAVIGATION
    # ==========================================================
    body_container = ft.Container(expand=True, content=scanner_tab_content)

    def switch_tab(idx):
        if idx == 0:
            body_container.content = scanner_tab_content
        elif idx == 1:
            settings_status.value = ""
            body_container.content = settings_tab_content
        else:
            refresh_history()
            body_container.content = history_tab_content
        page.update()

    header_bar = ft.Container(
        padding=12,
        bgcolor="#0F172A",
        content=ft.Column(
            spacing=8,
            controls=[
                ft.Row(
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    controls=[
                        ft.Text("Bozorov OMR Skaner", size=17, weight=ft.FontWeight.BOLD, color="white"),
                        ft.Text("@Bozorovmath | BM SAT Math", size=11, color="#38BDF8", weight=ft.FontWeight.BOLD),
                    ],
                ),
                ft.Row(
                    spacing=6,
                    controls=[
                        make_button("1. Skaner", lambda _: switch_tab(0), bgcolor="#1E293B", expand=True, height=38, font_size=12),
                        make_button("2. Ball & Kalit (35)", lambda _: switch_tab(1), bgcolor="#1E293B", expand=True, height=38, font_size=12),
                        make_button("3. Tarix", lambda _: switch_tab(2), bgcolor="#1E293B", expand=True, height=38, font_size=12),
                    ],
                ),
            ],
        ),
    )

    main_app_layout = ft.Column(
        expand=True,
        spacing=0,
        controls=[
            header_bar,
            body_container,
        ],
    )

    root_switcher = ft.Container(expand=True, content=splash_view)
    page.add(root_switcher)

    async def hide_splash_after_delay():
        await asyncio.sleep(2.5)
        root_switcher.content = main_app_layout
        page.update()

    page.run_task(hide_splash_after_delay)


if __name__ == "__main__":
    if hasattr(ft, "app"):
        ft.app(target=main)
    else:
        ft.run(main)