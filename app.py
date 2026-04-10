"""
App_035 SteamPosterMaker
Steamゲーム布教まとめ画像（最大10本紹介）自動生成 Webアプリ
"""

# ── Standard Library ───────────────────────────────────────
import io
import os
import datetime
from collections import deque
from functools import lru_cache

# ── Third Party ────────────────────────────────────────────
import requests
import streamlit as st
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from streamlit_sortables import sort_items

# ═══════════════════════════════════════════════════════════
#  固定定数
#  ── 調整したい数値はすべてここに集約 ──────────────────────
# ═══════════════════════════════════════════════════════════

# ── キャンバス・グリッド ─────────────────────────────────
CANVAS_W, CANVAS_H = 1920, 1080
MARGIN     = 4      # カード間マージン（px）
COLS       = 2      # グリッド列数（固定）
MAX_GAMES  = 10     # スロット最大数（全体見出しなし時）
HEADER_H   = 120    # 全体見出しエリアの高さ（px）

# ── カード構造 ───────────────────────────────────────────
THUMB_W         = 380   # サムネ幅（px）
SEPARATOR_W     = 3     # アクセント縦区切り線幅（px）
TEXT_PAD        = 12    # テキストエリア内側パディング（px）
PLAYER_H        = 26    # プレイ人数行の高さ（px）
ROW_GAP         = 6     # テキスト行間（px）
TITLE_MAX_H_ON  = 52    # 全体見出しあり時のタイトル最大高さ（px）
TITLE_MAX_H_OFF = 42    # 全体見出しなし時のタイトル最大高さ（px）

# ── 価格バッジ ───────────────────────────────────────────
PRICE_BADGE_PAD  = 8    # バッジ内テキスト余白（px）
PRICE_BADGE_EDGE = 10   # バッジとサムネ端の余白（px）

# ── タイポグラフィ（ポスター画像上のフォントサイズ / pt）──
HEADER_FONT_PT   = 64   # 全体見出し
TITLE_FONT_PT    = 28   # ゲームタイトル（初期）
TITLE_MIN_PT     = 16   # ゲームタイトル（最小）
PLAYER_FONT_PT   = 19   # プレイ人数（初期）
PLAYER_MIN_PT    = 13   # プレイ人数（最小）
REVIEW_FONT_PT   = 19   # レビュー文（初期）
REVIEW_MIN_PT    = 11   # レビュー文（最小）
PRICE_FONT_PT    = 24   # 価格バッジ
SLOT_PH_FONT_PT  = 28   # 空スロットプレースホルダ
WM_FONT_PT       = 22   # ウォーターマーク

FONT_FILENAME = "NotoSansCJKjp-Bold.otf"
FONT_URL = (
    "https://github.com/googlefonts/noto-cjk/raw/main"
    "/Sans/OTF/Japanese/NotoSansCJKjp-Bold.otf"
)
APP_NAME = "SteamPosterMaker"

PLAYER_PRESETS = [
    "ソロ", "ローカル協力", "ローカル対戦",
    "オンライン協力", "オンライン対戦", "MMO", "その他",
]

THEMES: dict[str, dict] = {
    "Steam Classic": {
        "bg":      (27,  40,  56),
        "accent":  (102, 192, 244),
        "header":  (23,  26,  33),
        "text1":   (255, 255, 255),
        "text2":   (198, 212, 223),
        "card_bg": (42,  63,  95),
    },
    "Pixel Retro": {
        "bg":      (13,  13,  13),
        "accent":  (57,  255, 20),
        "header":  (5,   5,   5),
        "text1":   (57,  255, 20),
        "text2":   (170, 255, 170),
        "card_bg": (26,  26,  26),
    },
    "Cyber Neon": {
        "bg":      (10,  0,   21),
        "accent":  (0,   245, 255),
        "header":  (6,   0,   13),
        "text1":   (255, 255, 255),
        "text2":   (184, 184, 255),
        "card_bg": (21,  0,   48),
    },
    "Dark Fantasy": {
        "bg":      (26,  10,  0),
        "accent":  (212, 175, 55),
        "header":  (13,  5,   0),
        "text1":   (245, 230, 200),
        "text2":   (200, 169, 110),
        "card_bg": (45,  21,  0),
    },
    "Horror Void": {
        "bg":      (12,  12,  12),
        "accent":  (139, 0,   0),
        "header":  (5,   5,   5),
        "text1":   (221, 221, 221),
        "text2":   (153, 153, 153),
        "card_bg": (26,  0,   0),
    },
}


# ═══════════════════════════════════════════════════════════
#  動的レイアウト計算
# ═══════════════════════════════════════════════════════════

def compute_layout(show_title: bool) -> dict:
    """
    全体見出しの有無に応じてレイアウト定数を動的に計算する。
    数値はすべてモジュール定数（MARGIN / HEADER_H / PLAYER_H など）から取得。
    - show_title=True : HEADER_H px + 2列×4行 = 8ゲーム
    - show_title=False: ヘッダーなし + 2列×5行 = 10ゲーム
    いずれも出力は 1920×1080 px 固定。
    """
    header_h  = HEADER_H if show_title else 0
    num_games = 8        if show_title else MAX_GAMES
    rows      = num_games // COLS
    grid_h    = CANVAS_H - header_h

    card_w = (CANVAS_W - MARGIN * (COLS + 1)) // COLS
    card_h = (grid_h   - MARGIN * (rows + 1)) // rows

    text_x_offset = THUMB_W + SEPARATOR_W + TEXT_PAD
    text_area_w   = card_w - text_x_offset - TEXT_PAD

    title_max_h  = TITLE_MAX_H_ON if show_title else TITLE_MAX_H_OFF
    title_y      = TEXT_PAD

    player_y     = title_y + title_max_h + ROW_GAP
    review_y     = player_y + PLAYER_H + ROW_GAP
    review_max_h = card_h - review_y - TEXT_PAD

    return {
        "header_h":      header_h,
        "num_games":     num_games,
        "rows":          rows,
        "card_w":        card_w,
        "card_h":        card_h,
        "text_x_offset": text_x_offset,
        "text_area_w":   text_area_w,
        "title_y":       title_y,
        "title_max_h":   title_max_h,
        "player_y":      player_y,
        "review_y":      review_y,
        "review_max_h":  review_max_h,
    }


# ═══════════════════════════════════════════════════════════
#  フォント管理
# ═══════════════════════════════════════════════════════════

def ensure_font() -> bool:
    """フォントが存在しなければ GitHub からダウンロードする（初回起動時のみ）"""
    if os.path.exists(FONT_FILENAME):
        return True
    if st.session_state.get("_font_failed"):
        return False
    try:
        with st.spinner("フォントをセットアップしています（初回のみ）..."):
            resp = requests.get(FONT_URL, timeout=120)
            resp.raise_for_status()
            with open(FONT_FILENAME, "wb") as f:
                f.write(resp.content)
        return True
    except Exception as e:
        st.warning(
            f"フォントのダウンロードに失敗しました。システムフォントで代替します。\n詳細: {e}"
        )
        st.session_state["_font_failed"] = True
        return False


@lru_cache(maxsize=32)
def get_font(size: int) -> ImageFont.FreeTypeFont:
    """
    指定サイズの Noto フォントを返す。取得失敗時は Pillow デフォルトにフォールバック。
    lru_cache により同一サイズへの重複呼び出しでファイル I/O を省略する。
    """
    if os.path.exists(FONT_FILENAME):
        try:
            return ImageFont.truetype(FONT_FILENAME, size)
        except Exception:
            pass
    try:
        return ImageFont.load_default(size=size)  # type: ignore[call-arg]
    except TypeError:
        return ImageFont.load_default()


# ═══════════════════════════════════════════════════════════
#  Steam API
# ═══════════════════════════════════════════════════════════

@st.cache_data(ttl=3600)
def search_steam(query: str) -> list[dict]:
    """
    Steam ストア検索 API を呼び出してゲーム候補リストを返す。
    @st.cache_data 内では session_state を操作しない（キャッシュヒット時に
    サイドエフェクトが再実行されないため）。
    """
    url = (
        f"https://store.steampowered.com/api/storesearch/"
        f"?term={query}&l=japanese&cc=JP"
    )
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        return [
            {
                "app_id": item["id"],
                "name":   item["name"],
                "thumb":  item.get("tiny_image", ""),
            }
            for item in resp.json().get("items", [])
        ]
    except Exception:
        return []


@st.cache_data(ttl=3600)
def get_game_details(app_id: int) -> dict:
    """
    Steam appdetails API からゲーム詳細を取得する。
    年齢制限や API 障害時もクラッシュさせず、フォールバック値を返す。
    """
    # age_restricted=True: Steam が年齢制限で詳細を返さなかったことを示す
    # age_restricted=False: ネットワーク障害など age gate 以外の原因での失敗
    fallback_network = {
        "title":          "",
        "image_url":      f"https://cdn.akamai.steamstatic.com/steam/apps/{app_id}/header.jpg",
        "price":          "不明",
        "age_restricted": False,
    }
    fallback_age = {
        "title":          "",
        "image_url":      f"https://cdn.akamai.steamstatic.com/steam/apps/{app_id}/header.jpg",
        "price":          "取得不可",
        "age_restricted": True,
    }
    try:
        url = (
            f"https://store.steampowered.com/api/appdetails"
            f"?appids={app_id}&l=japanese&cc=JP"
        )
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        app_data = resp.json().get(str(app_id), {})
        if not app_data.get("success"):
            # success=False は年齢制限 or リージョン制限が主な原因
            return fallback_age

        info = app_data.get("data", {})

        if info.get("is_free"):
            price = "無料"
        else:
            po = info.get("price_overview")
            if po:
                discount  = po.get("discount_percent", 0)
                final_fmt = po.get("final_formatted", "")
                if final_fmt and discount > 0:
                    price = f"-{discount}%  {final_fmt}"
                elif final_fmt:
                    price = final_fmt
                else:
                    price = "不明"
            else:
                price = "不明"

        return {
            "title":          info.get("name", ""),
            "image_url":      info.get("header_image", fallback_network["image_url"]),
            "price":          price,
            "age_restricted": False,
        }
    except Exception:
        return fallback_network


# ═══════════════════════════════════════════════════════════
#  画像ユーティリティ
# ═══════════════════════════════════════════════════════════

@st.cache_data(ttl=3600)
def _fetch_raw_image(url: str) -> bytes:
    """画像URLのバイト列をキャッシュ付きで取得（重複リクエスト防止）"""
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        return resp.content
    except Exception:
        return b""


def load_pil_image(url: str, target_w: int, target_h: int) -> Image.Image:
    """
    URL から画像を読み込み、アスペクト比を保ちながら中央クロップして
    target_w × target_h にリサイズする。失敗時はグレー画像を返す。
    """
    dummy = Image.new("RGB", (target_w, target_h), (70, 70, 70))
    raw = _fetch_raw_image(url)
    if not raw:
        return dummy
    try:
        img = Image.open(io.BytesIO(raw)).convert("RGB")
        src_w, src_h = img.size
        scale = max(target_w / src_w, target_h / src_h)
        new_w = max(1, int(src_w * scale))
        new_h = max(1, int(src_h * scale))
        img = img.resize((new_w, new_h), Image.LANCZOS)
        left = (new_w - target_w) // 2
        top  = (new_h - target_h) // 2
        return img.crop((left, top, left + target_w, top + target_h))
    except Exception:
        return dummy


@lru_cache(maxsize=4)
def make_age_restricted_image(w: int, h: int) -> Image.Image:
    """
    年齢制限で詳細取得不可のゲームに使うプレースホルダ画像。
    Pillow の基本プリミティブで鍵アイコン + "18+" テキストを描画する。
    """
    img = Image.new("RGB", (w, h), (20, 8, 8))
    drw = ImageDraw.Draw(img)

    cx = w // 2
    cy = h * 2 // 5          # アイコン全体を上寄りに
    s  = max(12, min(w, h) // 6)   # 基本スケール単位

    # ── 錠前ボディ（角丸矩形）────────────────────────────
    bw, bh = s * 2, int(s * 1.6)
    bx1, by1 = cx - bw // 2, cy
    bx2, by2 = bx1 + bw, by1 + bh
    drw.rounded_rectangle(
        [bx1, by1, bx2, by2],
        radius=max(4, s // 5),
        fill=(130, 20, 20),
        outline=(210, 55, 55),
        width=2,
    )

    # ── 鍵穴（円 + 下向き三角形）────────────────────────
    kx, ky = cx, by1 + bh // 3
    kr = max(3, s // 5)
    drw.ellipse([kx - kr, ky - kr, kx + kr, ky + kr], fill=(20, 8, 8))
    drw.polygon(
        [(kx - kr + 1, ky), (kx + kr - 1, ky), (kx, ky + kr * 2)],
        fill=(20, 8, 8),
    )

    # ── シャックル（上弧 + 縦線 2本）─────────────────────
    # Pillow arc: 0°=右, 時計回りで増加, 270°=上
    # 215°→325° の弧が鍵前の上部アーチになる
    sw    = int(bw * 0.52)
    sh    = int(s * 1.1)
    thick = max(3, s // 5)
    ax1, ay1 = cx - sw, by1 - sh
    ax2, ay2 = cx + sw, by1 + sh // 6
    drw.arc([ax1, ay1, ax2, ay2], start=215, end=325, fill=(210, 55, 55), width=thick)
    lx = ax1 + thick // 2
    rx = ax2 - thick // 2
    mid_y = by1 - sh // 2
    drw.line([lx, mid_y, lx, by1], fill=(210, 55, 55), width=thick)
    drw.line([rx, mid_y, rx, by1], fill=(210, 55, 55), width=thick)

    # ── "18+" ラベル ──────────────────────────────────────
    fs    = max(10, s * 3 // 4)
    font  = get_font(fs)
    label = "18+"
    lw    = int(drw.textlength(label, font=font))
    drw.text((cx - lw // 2, by2 + max(4, s // 4)), label, font=font, fill=(210, 70, 70))

    # ── 薄い外枠 ──────────────────────────────────────────
    drw.rectangle([0, 0, w - 1, h - 1], outline=(55, 15, 15), width=2)

    return img


# ── テキスト描画ユーティリティ ─────────────────────────────

def wrap_text_pixels(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont,
    max_w: int,
) -> str:
    """
    日本語対応・ピクセル幅ベースのテキスト折り返し関数。
    draw.textlength() で 1 文字ずつ計測しながら改行位置を決定する。
    """
    lines: list[str] = []
    current = ""
    for char in text:
        if char == "\n":
            lines.append(current)
            current = ""
            continue
        candidate = current + char
        if int(draw.textlength(candidate, font=font)) <= max_w:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = char
    if current:
        lines.append(current)
    return "\n".join(lines)


def fit_text_in_box(
    draw: ImageDraw.ImageDraw,
    text: str,
    initial_size: int,
    max_w: int,
    max_h: int,
    min_size: int = 11,
) -> tuple[ImageFont.FreeTypeFont, str]:
    """
    テキストが max_w × max_h のボックスに収まるまでフォントサイズを
    1pt ずつ縮小するループ。
    """
    size = initial_size
    while size >= min_size:
        font    = get_font(size)
        wrapped = wrap_text_pixels(draw, text, font, max_w)
        bbox    = draw.textbbox((0, 0), wrapped, font=font)
        if (bbox[3] - bbox[1]) <= max_h:
            return font, wrapped
        size -= 1
    font = get_font(min_size)
    return font, wrap_text_pixels(draw, text, font, max_w)


# ═══════════════════════════════════════════════════════════
#  カード描画
# ═══════════════════════════════════════════════════════════

def draw_card(
    canvas: Image.Image,
    draw: ImageDraw.ImageDraw,
    idx: int,
    game: dict | None,
    theme: dict,
    bg_style: str,
    blur_r: int,
    layout: dict,
) -> None:
    """
    1 枚のゲームカードを canvas の所定グリッド位置に描画する。
    idx=0〜N: 左列上→下、右列上→下の順（col = idx%2, row = idx//2）
    """
    L   = layout
    col = idx % COLS
    row = idx // COLS
    x0  = MARGIN + col * (L["card_w"] + MARGIN)
    y0  = L["header_h"] + MARGIN + row * (L["card_h"] + MARGIN)

    # ─── カード背景 ───────────────────────────────────────
    # 年齢制限ゲームの CDN 画像は取得できないため blur を適用しない
    use_blur = game and bg_style == "blur" and not game.get("age_restricted")
    if use_blur:
        bg_img  = load_pil_image(game["image_url"], L["card_w"], L["card_h"])
        blurred = bg_img.filter(ImageFilter.GaussianBlur(radius=max(1, blur_r)))
        overlay = Image.new("RGBA", (L["card_w"], L["card_h"]), (0, 0, 0, 165))
        card_bg = Image.alpha_composite(blurred.convert("RGBA"), overlay).convert("RGB")
    else:
        bg_color = theme["card_bg"] if game else (45, 45, 45)
        card_bg  = Image.new("RGB", (L["card_w"], L["card_h"]), bg_color)

    canvas.paste(card_bg, (x0, y0))

    # ─── 空スロット ─────────────────────────────────────────
    if game is None:
        ph_font = get_font(SLOT_PH_FONT_PT)
        ph_text = f"SLOT  {idx + 1:02d}"
        pw = int(draw.textlength(ph_text, font=ph_font))
        draw.text(
            (x0 + (L["card_w"] - pw) // 2, y0 + (L["card_h"] - 32) // 2),
            ph_text, font=ph_font, fill=(85, 85, 85),
        )
        draw.rectangle(
            [x0 + 2, y0 + 2, x0 + L["card_w"] - 3, y0 + L["card_h"] - 3],
            outline=(65, 65, 65), width=2,
        )
        return

    # ─── サムネイル（通常 or 年齢制限アイコン）──────────────
    if game.get("age_restricted"):
        thumb = make_age_restricted_image(THUMB_W, L["card_h"])
    else:
        thumb = load_pil_image(game["image_url"], THUMB_W, L["card_h"])
    canvas.paste(thumb, (x0, y0))

    # ─── 価格バッジ（サムネ右下・半透明オーバーレイ） ────────
    price_font = get_font(PRICE_FONT_PT)
    price_text = game["price"]
    price_bb   = draw.textbbox((0, 0), price_text, font=price_font)
    price_tw   = price_bb[2] - price_bb[0]
    price_th   = price_bb[3] - price_bb[1]
    bx1 = x0 + THUMB_W - price_tw - PRICE_BADGE_PAD * 2 - PRICE_BADGE_EDGE
    bx2 = x0 + THUMB_W - PRICE_BADGE_EDGE
    by1 = y0 + L["card_h"] - price_th - PRICE_BADGE_PAD * 2 - PRICE_BADGE_EDGE
    by2 = y0 + L["card_h"] - PRICE_BADGE_EDGE
    badge_w = bx2 - bx1
    badge_h = by2 - by1
    # 半透明背景: クロップ → RGBA alpha_composite → RGB で貼り戻す
    badge_bg = Image.new("RGBA", (badge_w, badge_h), (0, 0, 0, 185))
    section  = canvas.crop((bx1, by1, bx2, by2)).convert("RGBA")
    canvas.paste(Image.alpha_composite(section, badge_bg).convert("RGB"), (bx1, by1))
    draw.text((bx1 + PRICE_BADGE_PAD, by1 + PRICE_BADGE_PAD), price_text, font=price_font, fill=theme["accent"])

    # ─── アクセントカラーの縦区切り線 ───────────────────────
    draw.rectangle(
        [x0 + THUMB_W, y0, x0 + THUMB_W + SEPARATOR_W - 1, y0 + L["card_h"] - 1],
        fill=theme["accent"],
    )

    tx = x0 + L["text_x_offset"]
    ty = y0

    # ── ゲームタイトル（小さめ・auto-scale） ─────────────────
    t_font, t_wrapped = fit_text_in_box(
        draw, game["title"], TITLE_FONT_PT, L["text_area_w"], L["title_max_h"],
        min_size=TITLE_MIN_PT,
    )
    draw.text((tx, ty + L["title_y"]), t_wrapped, font=t_font, fill=theme["text1"])

    # ── プレイ人数 ───────────────────────────────────────────
    players = game.get("players", [])
    if players:
        p_font, p_wrapped = fit_text_in_box(
            draw, "  /  ".join(players), PLAYER_FONT_PT, L["text_area_w"],
            PLAYER_H, min_size=PLAYER_MIN_PT,
        )
        draw.text((tx, ty + L["player_y"]), p_wrapped, font=p_font, fill=theme["text2"])

    # ── レビュー文 ───────────────────────────────────────────
    review = game.get("review", "").strip()
    if review and L["review_max_h"] > 0:
        r_font, r_wrapped = fit_text_in_box(
            draw, review, REVIEW_FONT_PT, L["text_area_w"], L["review_max_h"],
            min_size=REVIEW_MIN_PT,
        )
        draw.text((tx, ty + L["review_y"]), r_wrapped, font=r_font, fill=theme["text2"])


# ═══════════════════════════════════════════════════════════
#  ポスター生成
# ═══════════════════════════════════════════════════════════

def generate_poster(
    games: list[dict | None],
    poster_title: str,
    theme_name: str,
    bg_style: str,
    blur_r: int,
    show_title: bool,
) -> Image.Image:
    """
    1920 × 1080 の Steam 布教まとめポスターを生成して PIL Image として返す。
    show_title=True : ヘッダー 120px + 2列×4行（8ゲーム）
    show_title=False: ヘッダーなし    + 2列×5行（10ゲーム）
    """
    layout = compute_layout(show_title)
    theme  = THEMES[theme_name]
    canvas = Image.new("RGB", (CANVAS_W, CANVAS_H), theme["bg"])
    draw   = ImageDraw.Draw(canvas)

    if show_title:
        draw.rectangle([0, 0, CANVAS_W, layout["header_h"]], fill=theme["header"])
        draw.rectangle(
            [0, layout["header_h"] - 4, CANVAS_W, layout["header_h"]],
            fill=theme["accent"],
        )
        if poster_title.strip():
            h_font = get_font(HEADER_FONT_PT)
            tb = draw.textbbox((0, 0), poster_title, font=h_font)
            tw = tb[2] - tb[0]
            th = tb[3] - tb[1]
            draw.text(
                ((CANVAS_W - tw) // 2, (layout["header_h"] - 4 - th) // 2),
                poster_title, font=h_font, fill=theme["text1"],
            )

    for i, game in enumerate(games[: layout["num_games"]]):
        draw_card(canvas, draw, i, game, theme, bg_style, blur_r, layout)

    wm_font = get_font(WM_FONT_PT)
    wm_text = f"Generated by {APP_NAME}"
    wm_w    = int(draw.textlength(wm_text, font=wm_font))
    draw.text(
        (CANVAS_W - wm_w - 20, CANVAS_H - 36),
        wm_text, font=wm_font, fill=(90, 90, 90),
    )

    return canvas


# ═══════════════════════════════════════════════════════════
#  UI ヘルパー
# ═══════════════════════════════════════════════════════════

def _show_age_restricted_thumb(padding: str = "16px 0") -> None:
    """年齢制限スロットのサムネ代替表示（Streamlit UI 用）"""
    st.markdown(
        f"<div style='background:#1a0808;border:1px solid #4a1515;"
        f"border-radius:6px;padding:{padding};text-align:center;"
        f"color:#c0392b;font-size:1.5rem;font-weight:bold;letter-spacing:0.05em;'>18+</div>",
        unsafe_allow_html=True,
    )


# ═══════════════════════════════════════════════════════════
#  セッション状態初期化
# ═══════════════════════════════════════════════════════════

def init_session() -> None:
    """Streamlit セッション変数の初期値を設定する（最大 MAX_GAMES=10 スロット）"""
    if "games" not in st.session_state:
        st.session_state.games = [None] * MAX_GAMES
    if "search_results" not in st.session_state:
        st.session_state.search_results = [[] for _ in range(MAX_GAMES)]
    if "reorder_mode" not in st.session_state:
        st.session_state["reorder_mode"] = False


# ═══════════════════════════════════════════════════════════
#  編集ダイアログ（ポップアップ）
# ═══════════════════════════════════════════════════════════

@st.dialog("ゲームを編集", width="large")
def edit_dialog(i: int) -> None:
    """
    スロット i のゲーム検索・選択・テキスト入力をポップアップで行う。
    st.rerun() を呼んだ時点でダイアログが閉じる。
    """
    st.caption(f"スロット {i + 1:02d}")
    st.divider()

    # ── 検索フォーム（Enter キー or ボタンで送信）────────────
    with st.form(key=f"dlg_form_{i}", border=False):
        col_q, col_btn = st.columns([5, 1])
        with col_q:
            st.text_input(
                "ゲームを検索",
                key=f"dlg_q_{i}",
                placeholder="タイトルを入力して Enter（日本語・英語どちらでも）",
                label_visibility="collapsed",
            )
        with col_btn:
            search_clicked = st.form_submit_button(
                "検索", icon=":material/search:", use_container_width=True,
            )

    if search_clicked:
        q = st.session_state.get(f"dlg_q_{i}", "").strip()
        if q:
            with st.spinner(f"「{q}」を検索しています..."):
                results = search_steam(q)
            st.session_state.search_results[i] = results
            st.session_state.pop(f"dlg_sel_{i}", None)
            if not results:
                st.warning(
                    "該当するゲームが見つかりませんでした。"
                    "別のキーワードを試すか、しばらく待ってから再検索してください。"
                )
        else:
            st.warning("キーワードを入力してください。")

    # ── 検索結果 + サムネプレビュー ──────────────────────
    results = st.session_state.search_results[i]
    if results:
        options_map = {
            f"{r['name']}  (AppID: {r['app_id']})": r
            for r in results[:10]
        }
        col_drop, col_prev = st.columns([3, 2])
        with col_drop:
            sel_key = st.selectbox(
                "候補",
                list(options_map.keys()),
                key=f"dlg_sel_{i}",
                label_visibility="collapsed",
            )
            confirm_clicked = st.button(
                "このゲームに決定", key=f"dlg_confirm_{i}",
                icon=":material/check_circle:",
            )
        with col_prev:
            chosen_prev = options_map[sel_key]
            prev_url = (
                f"https://cdn.akamai.steamstatic.com/steam/apps"
                f"/{chosen_prev['app_id']}/header.jpg"
            )
            st.image(prev_url, use_container_width=True, caption=chosen_prev["name"])

        if confirm_clicked:
            chosen = options_map[sel_key]
            with st.spinner(f"「{chosen['name']}」のデータを取得しています..."):
                details = get_game_details(chosen["app_id"])
            if details.get("age_restricted"):
                st.warning(
                    "このタイトルは年齢制限コンテンツのため Steam API から詳細を取得できませんでした。"
                    "ポスターには制限マークが表示されます。",
                    icon=":material/block:",
                )
            st.session_state.games[i] = {
                "app_id":         chosen["app_id"],
                "title":          details["title"] or chosen["name"],
                "image_url":      details["image_url"],
                "price":          details["price"],
                "review":         "",
                "players":        [],
                "age_restricted": details.get("age_restricted", False),
            }
            # ウィジェット値リセット（session_state との競合防止）
            st.session_state[f"dlg_review_{i}"] = ""
            st.session_state[f"dlg_players_{i}"] = []
            st.session_state.search_results[i] = []

    # ── 選択済みゲームの入力フォーム ──────────────────────
    game = st.session_state.games[i]
    if game:
        st.divider()
        col_img, col_form = st.columns([1, 2])
        with col_img:
            if game.get("age_restricted"):
                _show_age_restricted_thumb(padding="24px 0")
            else:
                st.image(game["image_url"], use_container_width=True)
            st.markdown(f"**{game['price']}**")
        with col_form:
            st.markdown(f"### {game['title']}")
            # ウィジェットの戻り値を直接使用（session_state 経由より1リランぶん遅延しない）
            review_now = st.text_area(
                "レビュー文",
                height=100,
                key=f"dlg_review_{i}",
                help="X (Twitter) 投稿を意識して 140 文字以内で。絵文字もOK。",
            )
            review_len = len(review_now or "")
            over_limit = review_len > 140
            color = "#e74c3c" if over_limit else "#aaa"
            st.markdown(
                f"<p style='text-align:right;font-size:0.8rem;color:{color};"
                f"margin-top:-12px'>{review_len} / 140 文字</p>",
                unsafe_allow_html=True,
            )
            if over_limit:
                st.error("140 文字を超えています。文字数を減らしてから保存してください。")
            st.multiselect(
                "プレイ人数",
                PLAYER_PRESETS,
                key=f"dlg_players_{i}",
            )

        st.divider()
        col_save, col_clear, col_cancel = st.columns([3, 2, 2])
        with col_save:
            if st.button("保存して閉じる", key=f"dlg_save_{i}",
                         icon=":material/save:",
                         type="primary", use_container_width=True,
                         disabled=over_limit):
                st.session_state.games[i]["review"]  = st.session_state.get(f"dlg_review_{i}", "")
                st.session_state.games[i]["players"] = st.session_state.get(f"dlg_players_{i}", [])
                del st.session_state["editing_slot"]
                st.rerun()
        with col_clear:
            if st.button("クリア", key=f"dlg_clear_{i}",
                         icon=":material/delete:",
                         use_container_width=True):
                st.session_state.games[i] = None
                st.session_state.search_results[i] = []
                for k in [f"dlg_review_{i}", f"dlg_players_{i}", f"dlg_q_{i}"]:
                    st.session_state.pop(k, None)
                del st.session_state["editing_slot"]
                st.rerun()
        with col_cancel:
            if st.button("キャンセル", key=f"dlg_cancel_{i}",
                         icon=":material/close:",
                         use_container_width=True):
                del st.session_state["editing_slot"]
                st.rerun()
    else:
        st.info("ゲームを検索してスロットに追加してください。")
        if st.button("閉じる", key=f"dlg_close_{i}", icon=":material/close:"):
            del st.session_state["editing_slot"]
            st.rerun()


# ═══════════════════════════════════════════════════════════
#  スロットカード（グリッド表示用）
# ═══════════════════════════════════════════════════════════

def render_slot_card(i: int) -> None:
    """
    ポスターのカードレイアウト（サムネ左・テキスト右）に近しい
    ミニカードを Streamlit で描画する。
    編集ボタンクリック → edit_dialog を開く。
    """
    game = st.session_state.games[i]

    with st.container(border=True):
        if game:
            # ── 上段: サムネ + タイトル・価格・人数 ─────────────
            col_thumb, col_info = st.columns([2, 3])
            with col_thumb:
                if game.get("age_restricted"):
                    _show_age_restricted_thumb()
                else:
                    st.image(game["image_url"], use_container_width=True)
            with col_info:
                price_line = (
                    "18+ / 詳細取得不可"
                    if game.get("age_restricted")
                    else game["price"]
                )
                players_line = " / ".join(game["players"]) if game.get("players") else ""
                lines = [
                    f"<p style='margin:0;font-weight:bold;font-size:0.95rem;line-height:1.3'>{game['title']}</p>",
                    f"<p style='margin:0;font-size:0.88rem;color:#aaa;line-height:1.4'>{price_line}</p>",
                ]
                if players_line:
                    lines.append(
                        f"<p style='margin:0;font-size:0.88rem;color:#aaa;line-height:1.4'>{players_line}</p>"
                    )
                st.markdown("".join(lines), unsafe_allow_html=True)
            # ── 下段: レビュー文（カード全幅） ──────────────────
            review = game.get("review", "")
            if review:
                st.caption(review)
        else:
            # 空スロットのプレースホルダ
            st.markdown(
                f"<div style='text-align:center;padding:20px 0;"
                f"color:#555;font-size:0.85rem;'>スロット {i + 1:02d}</div>",
                unsafe_allow_html=True,
            )

        if st.button("編集", key=f"btn_edit_{i}", icon=":material/edit:", use_container_width=True):
            st.session_state["editing_slot"] = i
            # ダイアログを開く際にウィジェットをゲームの保存値でリセット
            if game:
                st.session_state[f"dlg_review_{i}"]  = game.get("review", "")
                st.session_state[f"dlg_players_{i}"] = game.get("players", [])


# ═══════════════════════════════════════════════════════════
#  メイン
# ═══════════════════════════════════════════════════════════

def main() -> None:
    st.set_page_config(
        page_title="SteamPosterMaker",
        layout="wide",
        initial_sidebar_state="collapsed",
    )

    init_session()
    ensure_font()

    # スロットカード間の縦ギャップを縮小
    st.markdown(
        "<style>"
        "div[data-testid='stColumn'] > div[data-testid='stVerticalBlock'] { gap: 2px; }"
        "</style>",
        unsafe_allow_html=True,
    )

    st.title("SteamPosterMaker")

    with st.sidebar:
        st.markdown("### 開発者をフォロー")
        st.link_button(
            "𝕏  @Yuki_HERO44",
            "https://x.com/Yuki_HERO44",
            use_container_width=True,
        )

    st.divider()

    # ── 見出し設定（常時表示）+ 表示設定ポップオーバー ────────
    # show_title をトグルより先にセッション状態から読み取り、compute_layout を
    # 1 度だけ呼ぶ。その後 3 カラムの with ブロックを連続して展開する。
    # ※ with ブロックの間に非 UI コードを挟むと Streamlit の列レンダリングが
    #   分断され、ダイアログ内の再描画タイミングが乱れるため。
    show_title = st.session_state.get("show_title", True)
    layout     = compute_layout(show_title)
    num_games  = layout["num_games"]

    col_tog, col_ttl, col_pop = st.columns([1, 3, 1])
    with col_tog:
        show_title = st.toggle(
            "全体見出し",
            value=True,
            key="show_title",
            help="OFF にすると見出しなし・10本紹介モードに切り替わります（常に 1920×1080 出力）",
        )
    with col_ttl:
        poster_title = st.text_input(
            "見出しテキスト",
            value="2026年 神ゲー8選",
            max_chars=25,
            placeholder="25文字以内",
            key="poster_title",
            disabled=not show_title,
            label_visibility="collapsed",
        )
    with col_pop:
        with st.popover("表示設定", icon=":material/settings:", use_container_width=True):
            theme_name = st.selectbox(
                "テーマ",
                list(THEMES.keys()),
                key="theme_sel",
            )
            bg_style = st.radio(
                "背景スタイル",
                ["blur", "solid"],
                format_func=lambda x: "ぼかし" if x == "blur" else "単色",
                horizontal=True,
                key="bg_style_sel",
            )
            blur_r = 0
            if bg_style == "blur":
                blur_r = st.slider(
                    "ぼかし強度", min_value=1, max_value=40, value=15,
                    key="blur_r_val",
                    help="数値が大きいほどぼかしが強くなります",
                )
            st.caption(
                f"{layout['num_games']} 本紹介  ·  "
                f"カード {layout['card_w']} × {layout['card_h']} px"
            )

    st.divider()

    # ── ゲームスロット（2列グリッド） ───────────────────────
    filled = sum(1 for g in st.session_state.games[:num_games] if g is not None)

    col_hdr, col_cnt, col_sort = st.columns([3, 1, 1])
    with col_hdr:
        st.subheader("ゲームスロット")
    with col_cnt:
        st.metric("登録数", f"{filled} / {num_games}")
    with col_sort:
        sort_label = "並び替え完了" if st.session_state["reorder_mode"] else "並び替え"
        sort_icon  = ":material/done_all:" if st.session_state["reorder_mode"] else ":material/swap_vert:"
        sort_type  = "primary"   if st.session_state["reorder_mode"] else "secondary"
        if st.button(sort_label, icon=sort_icon, use_container_width=True, type=sort_type):
            st.session_state["reorder_mode"] = not st.session_state["reorder_mode"]
            st.rerun()

    if st.session_state["reorder_mode"]:
        # ── 並び替えモード ────────────────────────────────────
        st.info(
            "ドラッグして順序を変更し、完了したら「並び替え完了」を押してください。",
            icon=":material/swap_vert:",
        )

        sort_labels = []
        for idx in range(num_games):
            g = st.session_state.games[idx]
            sort_labels.append(g["title"] if g else f"空きスロット {idx + 1:02d}")

        sorted_labels = sort_items(sort_labels, key="slot_sorter")

        if sorted_labels != sort_labels:
            remaining: dict[str, deque] = {}
            for idx, label in enumerate(sort_labels):
                remaining.setdefault(label, deque()).append(idx)

            new_order = [remaining[label].popleft() for label in sorted_labels]

            old_g = st.session_state.games[:num_games]
            old_r = st.session_state.search_results[:num_games]
            st.session_state.games          = [old_g[j] for j in new_order] + st.session_state.games[num_games:]
            st.session_state.search_results = [old_r[j] for j in new_order] + st.session_state.search_results[num_games:]
            st.rerun()
    else:
        # ── 通常グリッド表示 ─────────────────────────────────
        num_rows = (num_games + 1) // 2
        for row in range(num_rows):
            grid_cols = st.columns(2, gap="small")
            for col_idx, gcol in enumerate(grid_cols):
                slot_idx = row * 2 + col_idx
                if slot_idx < num_games:
                    with gcol:
                        render_slot_card(slot_idx)

    st.divider()

    # ── ポスター生成 ────────────────────────────────────────
    if filled > 0 and filled < num_games:
        st.info(
            f"現在 **{filled}** 本のゲームが登録されています。"
            f"未入力の枠 {num_games - filled} 個は「空欄カード」として出力されます。",
            icon=":material/info:",
        )
    already_generated = "last_poster_bytes" in st.session_state
    generate_btn = st.button(
        "再生成" if already_generated else "ポスターを生成",
        icon=":material/refresh:" if already_generated else ":material/palette:",
        type="primary",
        use_container_width=True,
        disabled=(filled == 0),
    )

    if generate_btn:
        games_slice = st.session_state.games[:num_games]

        with st.status("ポスターを生成しています...", expanded=True) as gen_status:
            try:
                # Step 1: Steam CDN から各ゲームのヘッダー画像をフェッチ（キャッシュ優先）
                # 年齢制限ゲームは CDN 画像が取得できないため除外する
                fetchable = [
                    g for g in games_slice
                    if g is not None and not g.get("age_restricted")
                ]
                if fetchable:
                    st.write(
                        f"Steam からゲーム画像を取得しています..."
                        f" ({len(fetchable)} 本 / {num_games} スロット)"
                    )
                    for g in fetchable:
                        _fetch_raw_image(g["image_url"])

                # Step 2: Pillow で 1920×1080 px に合成
                st.write("1920 × 1080 px の画像を合成しています...")
                poster = generate_poster(
                    games_slice,
                    poster_title,
                    theme_name,
                    bg_style,
                    blur_r,
                    show_title,
                )

                # Step 3: PNG エンコード
                st.write("PNG ファイルに書き出しています...")
                buf = io.BytesIO()
                poster.save(buf, format="PNG", compress_level=1)
                st.session_state["last_poster_bytes"] = buf.getvalue()
                date_str = datetime.date.today().strftime("%Y%m%d")
                suffix   = "8pick" if show_title else "10pick"
                st.session_state["last_poster_meta"] = {
                    "filename": f"steam_{suffix}_{date_str}.png",
                }
                gen_status.update(
                    label="ポスター生成が完了しました", state="complete", expanded=False
                )
                st.toast(
                    "ポスターが完成しました。ダウンロードボタンから保存できます。",
                    icon=":material/check_circle:",
                )
            except Exception as e:
                gen_status.update(label="生成に失敗しました", state="error")
                st.error(f"詳細: {e}")

    # 生成済みポスターを表示（設定変更後も保持）
    if "last_poster_bytes" in st.session_state:
        poster_bytes = st.session_state["last_poster_bytes"]
        meta         = st.session_state["last_poster_meta"]
        st.image(poster_bytes, caption="プレビュー（実際は 1920×1080 で出力）", use_container_width=True)
        st.download_button(
            label="PNG でダウンロード",
            icon=":material/download:",
            data=poster_bytes,
            file_name=meta["filename"],
            mime="image/png",
            type="primary",
            use_container_width=True,
        )

    # ── 編集ダイアログを開く ────────────────────────────────
    # スロットカードの「編集」ボタンが押されたとき editing_slot が設定される
    if "editing_slot" in st.session_state:
        slot_idx = st.session_state["editing_slot"]
        if 0 <= slot_idx < MAX_GAMES:
            edit_dialog(slot_idx)
        else:
            del st.session_state["editing_slot"]


if __name__ == "__main__":
    main()
