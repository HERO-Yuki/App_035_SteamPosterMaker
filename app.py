"""
App_035 Steam8 Poster
Steamゲーム布教まとめ画像（8本紹介）自動生成 Webアプリ
"""

# ── Standard Library ───────────────────────────────────────
import io
import os
import datetime
from functools import lru_cache
from typing import Optional

# ── Third Party ────────────────────────────────────────────
import requests
import streamlit as st
from PIL import Image, ImageDraw, ImageFont, ImageFilter

# ═══════════════════════════════════════════════════════════
#  定数・レイアウト計算
# ═══════════════════════════════════════════════════════════
CANVAS_W, CANVAS_H = 1920, 1080
HEADER_H = 120
GRID_H = CANVAS_H - HEADER_H          # 960

MARGIN = 20
COLS, ROWS = 2, 4

# カードサイズ（マージンを差し引いて均等分割）
#   横: 1920 - 20*3 = 1860  → 1860 / 2 = 930
#   縦:  960 - 20*5 =  860  →  860 / 4 = 215
CARD_W = (CANVAS_W - MARGIN * (COLS + 1)) // COLS   # 930
CARD_H = (GRID_H   - MARGIN * (ROWS + 1)) // ROWS   # 215

# カード内レイアウト
THUMB_W = CARD_H                    # 215px（正方形クロップ）
SEPARATOR_W = 3                     # アクセントライン幅
TEXT_PAD = 12                       # テキストエリア左右上下パディング
TEXT_X_OFFSET = THUMB_W + SEPARATOR_W + TEXT_PAD   # 230
TEXT_AREA_W = CARD_W - TEXT_X_OFFSET - TEXT_PAD    # 688

BADGE_SIZE = 34                     # 番号バッジ（px）

# テキストエリア内 Y レイアウト（カード上端からの相対座標）
TITLE_Y = TEXT_PAD                  # 12
TITLE_MAX_H = 62                    # タイトル最大高さ
PRICE_Y = TITLE_Y + TITLE_MAX_H + 6    # 80
PRICE_H = 26
PLAYER_Y = PRICE_Y + PRICE_H + 4       # 110
PLAYER_H = 26
REVIEW_Y = PLAYER_Y + PLAYER_H + 6     # 142
REVIEW_MAX_H = CARD_H - REVIEW_Y - TEXT_PAD   # 215 - 142 - 12 = 61

# フォント
FONT_FILENAME = "NotoSansCJKjp-Bold.otf"
FONT_URL = (
    "https://github.com/googlefonts/noto-cjk/raw/main"
    "/Sans/OTF/Japanese/NotoSansCJKjp-Bold.otf"
)

APP_NAME = "Steam8 Poster"

PLAYER_PRESETS = [
    "ソロ", "ローカル協力", "ローカル対戦",
    "オンライン協力", "オンライン対戦", "MMO", "その他",
]

# ── テーマカラー定義 ────────────────────────────────────────
# 各キーは PIL RGB タプル
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
#  フォント管理
# ═══════════════════════════════════════════════════════════

def ensure_font() -> bool:
    """フォントが存在しなければ GitHub からダウンロードする（初回起動時のみ）"""
    if os.path.exists(FONT_FILENAME):
        return True
    try:
        with st.spinner("🔤 フォントをダウンロード中（初回のみ約30秒）..."):
            resp = requests.get(FONT_URL, timeout=120)
            resp.raise_for_status()
            with open(FONT_FILENAME, "wb") as f:
                f.write(resp.content)
        return True
    except Exception as e:
        st.warning(
            f"フォントのダウンロードに失敗しました。システムフォントで代替します。\n"
            f"（日本語テキストが正しく表示されない場合があります）\n詳細: {e}"
        )
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
    # フォールバック: Pillow 10.0+ は load_default(size=N) が使える
    try:
        return ImageFont.load_default(size=size)   # type: ignore[call-arg]
    except TypeError:
        return ImageFont.load_default()


# ═══════════════════════════════════════════════════════════
#  Steam API
# ═══════════════════════════════════════════════════════════

@st.cache_data(ttl=3600)
def search_steam(query: str) -> list[dict]:
    """Steam ストア検索 API を呼び出してゲーム候補リストを返す"""
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
    fallback = {
        "title":     "",
        "image_url": f"https://cdn.akamai.steamstatic.com/steam/apps/{app_id}/header.jpg",
        "price":     "不明",
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
            return fallback

        info = app_data.get("data", {})

        # 価格パース（無料 / セール / 通常）
        if info.get("is_free"):
            price = "無料"
        else:
            po = info.get("price_overview")
            if po:
                discount = po.get("discount_percent", 0)
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
            "title":     info.get("name", ""),
            "image_url": info.get("header_image", fallback["image_url"]),
            "price":     price,
        }
    except Exception:
        return fallback


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


# ── テキスト描画ユーティリティ ─────────────────────────────

def wrap_text_pixels(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont,
    max_w: int,
) -> str:
    """
    日本語対応・ピクセル幅ベースのテキスト折り返し関数。
    Python 標準の textwrap は全角文字の幅を正しく扱えないため、
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
    1pt ずつ縮小するループ。収まりきらない場合は min_size で描画する。
    """
    size = initial_size
    while size >= min_size:
        font = get_font(size)
        wrapped = wrap_text_pixels(draw, text, font, max_w)
        bbox = draw.textbbox((0, 0), wrapped, font=font)
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
    game: Optional[dict],
    theme: dict,
    bg_style: str,
    blur_r: int,
) -> None:
    """
    1 枚のゲームカードを canvas の所定グリッド位置に描画する。
    idx=0〜7: 左列上→下、右列上→下の順（col = idx%2, row = idx//2）
    """
    col = idx % COLS
    row = idx // COLS
    x0 = MARGIN + col * (CARD_W + MARGIN)
    y0 = HEADER_H + MARGIN + row * (CARD_H + MARGIN)

    # ─── カード背景 ───────────────────────────────────────
    if game and bg_style == "blur":
        # サムネをカードサイズに引き伸ばし、ぼかし + 暗いオーバーレイを重ねる
        bg_img = load_pil_image(game["image_url"], CARD_W, CARD_H)
        blurred = bg_img.filter(ImageFilter.GaussianBlur(radius=max(1, blur_r)))
        overlay = Image.new("RGBA", (CARD_W, CARD_H), (0, 0, 0, 165))
        card_bg = Image.alpha_composite(blurred.convert("RGBA"), overlay).convert("RGB")
    else:
        # 単色背景: game あり → テーマのカード色、なし（空スロット）→ 暗いグレー
        bg_color = theme["card_bg"] if game else (45, 45, 45)
        card_bg = Image.new("RGB", (CARD_W, CARD_H), bg_color)

    canvas.paste(card_bg, (x0, y0))

    # ─── 空スロット ─────────────────────────────────────────
    if game is None:
        ph_font = get_font(28)
        ph_text = f"SLOT  {idx + 1:02d}"
        pw = int(draw.textlength(ph_text, font=ph_font))
        draw.text(
            (x0 + (CARD_W - pw) // 2, y0 + (CARD_H - 32) // 2),
            ph_text, font=ph_font, fill=(85, 85, 85),
        )
        # 破線風の枠（実線で代用）
        draw.rectangle(
            [x0 + 2, y0 + 2, x0 + CARD_W - 3, y0 + CARD_H - 3],
            outline=(65, 65, 65), width=2,
        )
        return

    # ─── サムネイル（正方形クロップ、カード左端） ────────────
    thumb = load_pil_image(game["image_url"], THUMB_W, CARD_H)
    canvas.paste(thumb, (x0, y0))

    # ─── アクセントカラーの縦区切り線 ───────────────────────
    draw.rectangle(
        [x0 + THUMB_W, y0, x0 + THUMB_W + SEPARATOR_W - 1, y0 + CARD_H - 1],
        fill=theme["accent"],
    )

    # ─── テキストエリア原点 ──────────────────────────────────
    tx = x0 + TEXT_X_OFFSET   # テキスト左端 x
    ty = y0                    # カード上端 y

    # ── 番号バッジ（塗りつぶし矩形 + 数字）──────────────────
    bx, by = tx, ty + TITLE_Y
    badge_font = get_font(BADGE_SIZE - 12)  # 22pt
    badge_text = f"{idx + 1:02d}"
    draw.rectangle([bx, by, bx + BADGE_SIZE, by + BADGE_SIZE], fill=theme["accent"])
    bw = int(draw.textlength(badge_text, font=badge_font))
    bb = draw.textbbox((0, 0), badge_text, font=badge_font)
    bh = bb[3] - bb[1]
    draw.text(
        (bx + (BADGE_SIZE - bw) // 2, by + (BADGE_SIZE - bh) // 2 - 1),
        badge_text, font=badge_font, fill=(0, 0, 0),
    )

    # ── ゲームタイトル ────────────────────────────────────────
    title_x = tx + BADGE_SIZE + 10
    title_max_w = TEXT_AREA_W - BADGE_SIZE - 10
    t_font, t_wrapped = fit_text_in_box(
        draw, game["title"], 36, title_max_w, TITLE_MAX_H, min_size=18
    )
    draw.text((title_x, ty + TITLE_Y), t_wrapped, font=t_font, fill=theme["text1"])

    # ── 価格 ─────────────────────────────────────────────────
    price_font = get_font(22)
    price_str = game["price"]
    draw.text((tx, ty + PRICE_Y), price_str, font=price_font, fill=theme["accent"])

    # ── プレイ人数 ───────────────────────────────────────────
    players = game.get("players", [])
    if players:
        p_font = get_font(19)
        p_str = "  /  ".join(players)
        # 幅が溢れる場合は自動縮小
        p_font, p_wrapped = fit_text_in_box(
            draw, p_str, 19, TEXT_AREA_W, PLAYER_H, min_size=13
        )
        draw.text((tx, ty + PLAYER_Y), p_wrapped, font=p_font, fill=theme["text2"])

    # ── レビュー文（自動折り返し + フォントサイズ自動縮小） ──
    review = game.get("review", "").strip()
    if review:
        r_font, r_wrapped = fit_text_in_box(
            draw, review, 19, TEXT_AREA_W, REVIEW_MAX_H, min_size=11
        )
        draw.text((tx, ty + REVIEW_Y), r_wrapped, font=r_font, fill=theme["text2"])


# ═══════════════════════════════════════════════════════════
#  ポスター生成
# ═══════════════════════════════════════════════════════════

def generate_poster(
    games: list[Optional[dict]],
    poster_title: str,
    theme_name: str,
    bg_style: str,
    blur_r: int,
) -> Image.Image:
    """
    1920 × 1080 の Steam 布教まとめポスターを生成して PIL Image として返す。
    ・上部 120px: 全体見出しヘッダー
    ・下部 960px: 2列 × 4行 のゲームカードグリッド
    """
    theme = THEMES[theme_name]
    canvas = Image.new("RGB", (CANVAS_W, CANVAS_H), theme["bg"])
    draw = ImageDraw.Draw(canvas)

    # ─── ヘッダーエリア ──────────────────────────────────────
    draw.rectangle([0, 0, CANVAS_W, HEADER_H], fill=theme["header"])
    # アクセントカラーの下端ライン
    draw.rectangle([0, HEADER_H - 4, CANVAS_W, HEADER_H], fill=theme["accent"])

    if poster_title.strip():
        h_font = get_font(64)
        tw = int(draw.textlength(poster_title, font=h_font))
        tb = draw.textbbox((0, 0), poster_title, font=h_font)
        th = tb[3] - tb[1]
        # ヘッダー内で垂直中央
        draw.text(
            ((CANVAS_W - tw) // 2, (HEADER_H - 4 - th) // 2),
            poster_title, font=h_font, fill=theme["text1"],
        )

    # ─── ゲームカード（8枚） ─────────────────────────────────
    for i, game in enumerate(games):
        draw_card(canvas, draw, i, game, theme, bg_style, blur_r)

    # ─── ウォーターマーク ─────────────────────────────────────
    wm_font = get_font(22)
    wm_text = f"Generated by {APP_NAME}"
    wm_w = int(draw.textlength(wm_text, font=wm_font))
    draw.text(
        (CANVAS_W - wm_w - 20, CANVAS_H - 36),
        wm_text, font=wm_font, fill=(90, 90, 90),
    )

    return canvas


# ═══════════════════════════════════════════════════════════
#  セッション状態初期化
# ═══════════════════════════════════════════════════════════

def init_session() -> None:
    """Streamlit セッション変数の初期値を設定する"""
    if "games" not in st.session_state:
        # 各スロットのゲームデータ（None = 未設定）
        st.session_state.games = [None] * 8
    if "search_results" not in st.session_state:
        st.session_state.search_results = [[] for _ in range(8)]
    if "search_queries" not in st.session_state:
        st.session_state.search_queries = [""] * 8


# ═══════════════════════════════════════════════════════════
#  Streamlit UI
# ═══════════════════════════════════════════════════════════

def render_slot(i: int) -> None:
    """スロット i（0〜7）の検索・選択・入力フォームを描画する"""
    game = st.session_state.games[i]
    slot_label = f"スロット {i + 1:02d}"
    if game:
        slot_label += f"  —  {game['title']}"

    with st.expander(slot_label, expanded=(game is None and i == 0)):

        # ── 検索フォーム ───────────────────────────────────
        col_q, col_btn = st.columns([4, 1])
        with col_q:
            query = st.text_input(
                "ゲームを検索",
                key=f"q_{i}",
                value=st.session_state.search_queries[i],
                placeholder="タイトルを入力...",
                label_visibility="collapsed",
            )
        with col_btn:
            if st.button("🔍 検索", key=f"btn_search_{i}", use_container_width=True):
                if query.strip():
                    st.session_state.search_queries[i] = query
                    with st.spinner("検索中..."):
                        results = search_steam(query.strip())
                    st.session_state.search_results[i] = results
                    # 再検索時: 前回の選択が残らないよう selectbox キーをクリア
                    st.session_state.pop(f"sel_{i}", None)
                    if not results:
                        st.warning("該当するゲームが見つかりませんでした。別のキーワードで試してください。")
                else:
                    st.warning("キーワードを入力してください。")

        # ── 検索結果リスト ─────────────────────────────────
        results = st.session_state.search_results[i]
        if results:
            options_map = {
                f"{r['name']}  (AppID: {r['app_id']})": r
                for r in results[:10]
            }
            selected_key = st.selectbox(
                "候補を選択",
                list(options_map.keys()),
                key=f"sel_{i}",
                label_visibility="collapsed",
            )
            if st.button("✅ このゲームを選択", key=f"btn_confirm_{i}"):
                chosen = options_map[selected_key]
                with st.spinner(f"「{chosen['name']}」の詳細を取得中..."):
                    details = get_game_details(chosen["app_id"])
                st.session_state.games[i] = {
                    "app_id":    chosen["app_id"],
                    "title":     details["title"] or chosen["name"],
                    "image_url": details["image_url"],
                    "price":     details["price"],
                    "review":    "",
                    "players":   [],
                }
                # ウィジェット値を明示的にリセット:
                # text_area / multiselect は session_state キーが残っていると
                # 前のゲームの値を表示してしまうため、確定時に空値で上書きする
                st.session_state[f"review_{i}"] = ""
                st.session_state[f"players_{i}"] = []
                # 検索結果をクリアして画面をすっきりさせる
                st.session_state.search_results[i] = []
                st.rerun()

        # ── 選択済みゲームの入力フォーム ──────────────────
        if game:
            col_img, col_form = st.columns([1, 3])
            with col_img:
                st.image(game["image_url"], use_container_width=True)
                st.caption(f"💴 {game['price']}")

            with col_form:
                # レビュー文（140文字・Python len() でカウント）
                review_val = st.text_area(
                    "レビュー文（最大 140 文字）",
                    value=game.get("review", ""),
                    max_chars=140,
                    height=110,
                    key=f"review_{i}",
                    help="X (Twitter) 投稿を意識して 140 文字以内で。絵文字もOK。",
                )
                # プレイ人数（プリセット複数選択）
                players_val = st.multiselect(
                    "プレイ人数",
                    PLAYER_PRESETS,
                    default=game.get("players", []),
                    key=f"players_{i}",
                )

                # 入力値を session_state に書き戻す
                st.session_state.games[i]["review"] = review_val
                st.session_state.games[i]["players"] = players_val

            # クリアボタン
            if st.button("🗑️ スロットをクリア", key=f"btn_clear_{i}"):
                st.session_state.games[i] = None
                st.session_state.search_results[i] = []
                # ウィジェット値もリセット
                for k in [f"review_{i}", f"players_{i}", f"q_{i}"]:
                    st.session_state.pop(k, None)
                st.rerun()

        elif not results:
            st.info("ゲームを検索してスロットに追加してください。")


def main() -> None:
    st.set_page_config(
        page_title="Steam8 Poster",
        page_icon="🎮",
        layout="wide",
        initial_sidebar_state="collapsed",
    )

    init_session()
    ensure_font()

    # ── タイトル ────────────────────────────────────────────
    st.title("🎮 Steam8 Poster")
    st.caption("Steamゲーム布教まとめ画像（8本紹介）を 1920×1080 で自動生成します。")

    st.divider()

    # ── グローバル設定 ──────────────────────────────────────
    with st.expander("⚙️ 全体設定", expanded=True):
        c1, c2, c3 = st.columns([3, 2, 2])
        with c1:
            poster_title = st.text_input(
                "全体見出し",
                value="2024年 神ゲー8選",
                max_chars=40,
                placeholder="例: 2024年 神ゲー8選",
                key="poster_title",
            )
        with c2:
            theme_name = st.selectbox("テーマカラー", list(THEMES.keys()))
        with c3:
            bg_style = st.radio(
                "背景スタイル",
                ["blur", "solid"],
                format_func=lambda x: "🌫️ ぼかし背景" if x == "blur" else "🎨 単色背景",
                horizontal=True,
            )

        blur_r = 0
        if bg_style == "blur":
            blur_r = st.slider(
                "ぼかし強度",
                min_value=1, max_value=40, value=15,
                help="値が大きいほど強くぼかされます。",
            )

    st.divider()

    # ── 8スロット ───────────────────────────────────────────
    st.subheader("🎯 ゲームスロット（最大 8 本）")

    filled = sum(1 for g in st.session_state.games if g is not None)
    st.caption(f"登録済み: {filled} / 8 本")

    for i in range(8):
        render_slot(i)

    st.divider()

    # ── 生成ボタン ──────────────────────────────────────────
    col_gen, _ = st.columns([1, 3])
    with col_gen:
        generate_btn = st.button(
            "🎨 ポスターを生成する",
            type="primary",
            use_container_width=True,
            disabled=(filled == 0),
        )

    if generate_btn:
        if filled == 0:
            st.error("少なくとも 1 本のゲームを登録してください。")
            return

        with st.spinner("画像を生成中...（大きな画像のため少々お待ちください）"):
            try:
                poster = generate_poster(
                    st.session_state.games,
                    poster_title,
                    theme_name,
                    bg_style,
                    blur_r,
                )
            except Exception as e:
                st.error(f"画像の生成に失敗しました。\n詳細: {e}")
                return

        st.success("✅ ポスターの生成が完了しました！")

        # プレビュー（画面幅に合わせて縮小表示）
        st.image(poster, caption="プレビュー（実際は 1920×1080 で出力）", use_container_width=True)

        # PNG バイト列に変換してダウンロードボタン
        buf = io.BytesIO()
        poster.save(buf, format="PNG", optimize=False)
        buf.seek(0)

        date_str = datetime.date.today().strftime("%Y%m%d")
        st.download_button(
            label="⬇️ PNG でダウンロード",
            data=buf,
            file_name=f"steam_8pick_{date_str}.png",
            mime="image/png",
            type="primary",
        )


if __name__ == "__main__":
    main()
