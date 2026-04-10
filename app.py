"""
App_035 SteamPosterMaker
Steamゲーム布教まとめ画像（最大10本紹介）自動生成 Webアプリ
"""

# ── Standard Library ───────────────────────────────────────
import html
import io
import os
import random
import datetime
from collections import deque
from functools import lru_cache

# ── Third Party ────────────────────────────────────────────
import requests
import streamlit as st
import streamlit.components.v1 as components
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
MAX_GAMES  = 10     # スロット最大数（常に10本固定）
HEADER_H   = 88     # 全体見出しエリアの高さ（px）— ensure_font() 後に _actual_header_h へ反映
FOOTER_H   = 36     # フッター帯の高さ（px）— ウォーターマーク領域

# ── カード構造 ───────────────────────────────────────────
THUMB_W           = 380   # サムネ幅（px）
CENTER_DIV_W      = 20    # グリッド中央縦罫線の幅（px）
ROW_DIV_H         = 6     # ゲーム行間の横罫線の高さ（px）
TEXT_PAD          = 12    # テキストエリア内側パディング（px）
ROW_GAP           = 6     # タイトル〜レビュー間の行間（px）
TITLE_MAX_H_RATIO = 0.22  # ゲームタイトル最大高さ ÷ カード高さの比率（8本/10本・見出しあり/なしで可変）
TITLE_BOX_MIN_H   = 36    # ゲームタイトル最大高さの下限（px）— 極端な縮小を防ぐフロア値
ACCENT_LINE_H     = 4     # ヘッダー・フッターのアクセントライン高さ（px）

# ── 価格バッジ ───────────────────────────────────────────
PRICE_BADGE_PAD  = 8          # バッジ内テキスト余白（px）
PRICE_BADGE_EDGE = 10         # バッジとサムネ端の余白（px）
SALE_GREEN       = (164, 208, 7)  # #A4D007 — セール割引率テキスト色（Steam グリーン）

# ── タイポグラフィ（ポスター画像上のフォントサイズ / pt）──
HEADER_FONT_PT   = 52   # 全体見出し
TITLE_V_PAD      = 8    # 全体見出しテキストの上下余白（px）
TITLE_FONT_PT    = 28   # ゲームタイトル（初期）
TITLE_MIN_PT     = 16   # ゲームタイトル（最小）
REVIEW_FONT_PT   = 19   # レビュー文（初期）
REVIEW_MIN_PT    = 11   # レビュー文（最小）
PRICE_FONT_PT    = 24   # 価格バッジ
SLOT_PH_FONT_PT  = 28   # 空スロットプレースホルダ
WM_FONT_PT       = 22   # ウォーターマーク

# ensure_font() 実行後にフォント実測値で更新される（UI・ポスター両方で共用）
_actual_header_h: int = HEADER_H

# ── Steam API キャッシュ設定 ─────────────────────────────
# Streamlit Community Cloud のメモリ制限（約 1 GB）を考慮した上限値
_CACHE_TTL         = 3600   # キャッシュ有効期間（秒）
_CACHE_MAX_SEARCH  = 100    # search_steam: クエリ文字列ごとにキャッシュ
_CACHE_MAX_DETAILS = 200    # get_game_details: AppID ごとにキャッシュ
_CACHE_MAX_IMAGES  = 50     # _fetch_raw_image: 画像バイト列は大きいので最小限

FONT_FILENAME = "NotoSansCJKjp-Bold.otf"
FONT_URLS = [
    # プライマリ: GitHub 公式リポジトリ
    "https://github.com/googlefonts/noto-cjk/raw/main/Sans/OTF/Japanese/NotoSansCJKjp-Bold.otf",
    # フォールバック: jsDelivr CDN（GitHub 障害時）
    "https://cdn.jsdelivr.net/gh/googlefonts/noto-cjk/Sans/OTF/Japanese/NotoSansCJKjp-Bold.otf",
]
APP_NAME      = "SteamPosterMaker"
# config.toml の primaryColor と一致させる（スティッキーバー・UI 強調色）
_PRIMARY_COLOR = "#d99200"

# ── 開発者モード ──────────────────────────────────────────
# False に変更するだけでデバッグ用 UI（テストデータ入力ボタン等）が完全に非表示になる
DEV_MODE: bool = False

# テスト入力用サンプルゲームデータ（DEV_MODE=True のときのみ使用）
_DEV_SAMPLE_GAMES: list[dict] = [
    {
        "app_id": 1245620, "title": "ELDEN RING",
        "image_url": "https://cdn.akamai.steamstatic.com/steam/apps/1245620/header.jpg",
        "price": "¥8,778", "age_restricted": False,
        "review": "オープンワールドと死にゲーの融合。探索の自由度と達成感が圧倒的。ボス撃破時の感動はひとしお。",
    },
    {
        "app_id": 1091500, "title": "Cyberpunk 2077",
        "image_url": "https://cdn.akamai.steamstatic.com/steam/apps/1091500/header.jpg",
        "price": "¥8,778", "age_restricted": False,
        "review": "圧倒的なビジュアルとストーリー。ナイトシティの世界に完全に没入できる。大型アプデで別ゲーに。",
    },
    {
        "app_id": 1145360, "title": "Hades",
        "image_url": "https://cdn.akamai.steamstatic.com/steam/apps/1145360/header.jpg",
        "price": "¥2,050", "age_restricted": False,
        "review": "死んでも楽しいローグライク。会話で物語が進む構造が斬新。何周でもやりたくなる中毒性。",
    },
    {
        "app_id": 367520, "title": "Hollow Knight",
        "image_url": "https://cdn.akamai.steamstatic.com/steam/apps/367520/header.jpg",
        "price": "¥580", "age_restricted": False,
        "review": "コスパ最強の2Dアクション。広大なマップ、美麗なドット、硬派な難易度のすべてが最高水準。",
    },
    {
        "app_id": 413150, "title": "Stardew Valley",
        "image_url": "https://cdn.akamai.steamstatic.com/steam/apps/413150/header.jpg",
        "price": "¥980", "age_restricted": False,
        "review": "農場経営×RPG。ゆっくり自分のペースで遊べる癒し系。協力プレイで友人と農業ライフも楽しい。",
    },
    {
        "app_id": 620, "title": "Portal 2",
        "image_url": "https://cdn.akamai.steamstatic.com/steam/apps/620/header.jpg",
        "price": "¥1,480", "age_restricted": False,
        "review": "発想力を試されるパズルゲームの金字塔。ストーリーも秀逸。友人との協力プレイが特にオススメ。",
    },
    {
        "app_id": 292030, "title": "The Witcher 3: Wild Hunt",
        "image_url": "https://cdn.akamai.steamstatic.com/steam/apps/292030/header.jpg",
        "price": "¥4,980", "age_restricted": False,
        "review": "オープンワールドRPGの最高傑作のひとつ。クエストの一つひとつが丁寧に作り込まれている。",
    },
    {
        "app_id": 105600, "title": "Terraria",
        "image_url": "https://cdn.akamai.steamstatic.com/steam/apps/105600/header.jpg",
        "price": "¥980", "age_restricted": False,
        "review": "2Dサンドボックスの傑作。掘って作って戦うループが止まらない。マルチプレイで友人と遊ぶと倍楽しい。",
    },
    {
        "app_id": 548430, "title": "Deep Rock Galactic",
        "image_url": "https://cdn.akamai.steamstatic.com/steam/apps/548430/header.jpg",
        "price": "¥2,480", "age_restricted": False,
        "review": "最高のコープシューター。チームワークが問われる設計が秀逸。Rock and Stone！",
    },
    {
        "app_id": 582010, "title": "Monster Hunter: World",
        "image_url": "https://cdn.akamai.steamstatic.com/steam/apps/582010/header.jpg",
        "price": "¥4,180", "age_restricted": False,
        "review": "シリーズ最高傑作の呼び声高い一作。アクションの奥深さはもちろん、世界の造り込みも抜群。",
    },
    {
        "app_id": 504230, "title": "Celeste",
        "image_url": "https://cdn.akamai.steamstatic.com/steam/apps/504230/header.jpg",
        "price": "¥1,980", "age_restricted": False,
        "review": "難しいが理不尽ではないプラットフォーマー。克服するたびに成長を感じられる。BGMも最高。",
    },
    {
        "app_id": 2379780, "title": "Balatro",
        "image_url": "https://cdn.akamai.steamstatic.com/steam/apps/2379780/header.jpg",
        "price": "¥2,600", "age_restricted": False,
        "review": "ポーカー×ローグライクの唯一無二の組み合わせ。シナジーを見つける快感が止まらない中毒作。",
    },
]

# Windows / URL で使えない文字セット
_FILENAME_INVALID = set('\\/: *?"<>|\t\n\r')

# X (Twitter) ブランドカラーのリンクボタン HTML（.x-btn CSS は _GLOBAL_CSS で定義）
_X_BUTTON_HTML = """
<div style="text-align:center;margin:8px 0 20px;">
  <p style="font-size:0.8rem;color:#aaa;margin:0 0 8px;">ご意見・ご要望は開発者のXまで</p>
  <a href="https://x.com/Yuki_HERO44" target="_blank" rel="noopener noreferrer" class="x-btn">
    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="white">
      <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-4.714-6.231-5.401 6.231H2.747l7.73-8.835L1.254 2.25H8.08l4.258 5.629 5.906-5.629Zm-1.161 17.52h1.833L7.084 4.126H5.117z"/>
    </svg>
    @Yuki_HERO44
  </a>
</div>
"""

# グローバル CSS（スロットカード高さ揃え + 列ギャップ調整 + X ボタン共通スタイル）
_GLOBAL_CSS = """
<style>
/* スロットカード列内のギャップを詰める */
div[data-testid='stColumn'] > div[data-testid='stVerticalBlock'] { gap: 2px; }

/* ── サイドバーを完全非表示 ── */
[data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"] {
  display: none !important;
}
section[data-testid="stMain"] { margin-left: 0 !important; }

/* ページ下部にスティッキーバーの高さ分の余白を確保（コンテンツが隠れないように） */
section[data-testid="stMain"] > div > div { padding-bottom: 90px !important; }


/* ── X ブランドリンクボタン ── */
.x-btn {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  background: #000;
  color: #fff !important;
  border: 1px solid #333;
  border-radius: 6px;
  padding: 6px 14px;
  font-size: 0.85rem;
  font-weight: bold;
  text-decoration: none !important;
  line-height: 1.4;
  white-space: nowrap;
  transition: background 0.2s ease, border-color 0.2s ease, opacity 0.2s ease;
}
.x-btn:visited, .x-btn:active, .x-btn:focus {
  color: #fff !important;
  text-decoration: none !important;
}
.x-btn:hover {
  background: #1a1a1a;
  border-color: #666;
  opacity: 0.85;
  color: #fff !important;
}

/* ── スロットカード行: 高さを同一に揃える ── */
/* ボーダーコンテナを含む横並びブロックのみ対象にし、他の行に影響させない */
[data-testid="stHorizontalBlock"]:has([data-testid="stVerticalBlockBorderWrapper"]) {
    align-items: stretch !important;
}
[data-testid="stHorizontalBlock"]:has([data-testid="stVerticalBlockBorderWrapper"])
    > [data-testid="column"] {
    display: flex !important;
    flex-direction: column !important;
}
/* 列内の中間 div を flex コンテナとして高さを伝播 */
[data-testid="stHorizontalBlock"]:has([data-testid="stVerticalBlockBorderWrapper"])
    > [data-testid="column"] > div {
    flex: 1 !important;
    display: flex !important;
    flex-direction: column !important;
    height: 100% !important;
}
/* stVerticalBlockBorderWrapper 自体と内部 stVerticalBlock を 100% に */
[data-testid="stHorizontalBlock"]:has([data-testid="stVerticalBlockBorderWrapper"])
    [data-testid="stVerticalBlockBorderWrapper"] {
    flex: 1 !important;
    height: 100% !important;
}
[data-testid="stHorizontalBlock"]:has([data-testid="stVerticalBlockBorderWrapper"])
    [data-testid="stVerticalBlockBorderWrapper"] > div[data-testid="stVerticalBlock"] {
    height: 100% !important;
    display: flex !important;
    flex-direction: column !important;
}
</style>
"""


def _render_sticky_bar(filled: int, num_games: int, already_generated: bool) -> None:
    """
    画面下部に固定表示するスティッキーボトムバーを st.markdown で描画する。

    構成: [プログレスバー（固定幅）] [生成 / 再生成ボタン] — 中央寄せ。

    ボタンは純粋な HTML ボタンのため、クリック時は JS で URL クエリパラメータ
    `?_sg=<timestamp>` を書き換えて Streamlit のリランを誘発する方式を採用。
    リラン後、main() の冒頭で `st.session_state["_sticky_generate"]` を検知して
    生成処理を実行する。
    """
    btn_label  = "再生成する" if already_generated else "ポスターを生成する"
    btn_icon   = "refresh"   if already_generated else "palette"
    pct        = int(filled / num_games * 100) if num_games > 0 else 0
    btn_bg     = "#555"            if filled == 0 else _PRIMARY_COLOR
    btn_color  = "#999"            if filled == 0 else "#fff"
    btn_cursor = "not-allowed"     if filled == 0 else "pointer"
    disabled   = 'disabled=""'     if filled == 0 else ""
    onclick    = "" if filled == 0 else (
        "var u=new URL(window.location.href);"
        "u.searchParams.set('_sg',Date.now());"
        "window.location.href=u.toString();"
    )
    st.markdown(
        f"""
<div id="spm-sticky-bar" style="
  position:fixed;bottom:0;left:0;right:0;z-index:9999;
  background:#1b2838;border-top:2px solid #2a475e;
  padding:8px 0 10px;box-shadow:0 -2px 12px rgba(0,0,0,.5);
  display:flex;justify-content:center;
">
  <!-- 中央寄せコンテナ（最大幅・左右余白） -->
  <div style="display:inline-flex;align-items:center;gap:16px;padding:0 40px;">
    <!-- プログレスバー（短め・固定幅） -->
    <div style="width:120px;flex-shrink:0;">
      <div style="font-size:0.7rem;color:#aaa;margin-bottom:3px;white-space:nowrap;">
        {filled} / {num_games} 本
      </div>
      <div style="background:#2a475e;border-radius:4px;height:6px;overflow:hidden;">
        <div style="background:{_PRIMARY_COLOR};width:{pct}%;height:100%;
                    border-radius:4px;transition:width .3s;"></div>
      </div>
    </div>
    <!-- 生成ボタン -->
    <button {disabled} onclick="{onclick}"
      style="display:inline-flex;align-items:center;gap:6px;
             background:{btn_bg};color:{btn_color};border:none;
             border-radius:6px;padding:9px 22px;font-size:0.9rem;
             font-weight:bold;cursor:{btn_cursor};white-space:nowrap;
             transition:opacity .2s;font-family:inherit;"
      onmouseover="if(!this.disabled)this.style.opacity='.8'"
      onmouseout="this.style.opacity='1'"
    >
      <span style="font-family:'Material Symbols Rounded';font-size:1.15rem;
                   font-variation-settings:'FILL' 1,'wght' 400,'GRAD' 0,'opsz' 24;
                   line-height:1;vertical-align:middle;">{btn_icon}</span>
      {btn_label}
    </button>
  </div>
</div>
<link rel="stylesheet"
  href="https://fonts.googleapis.com/css2?family=Material+Symbols+Rounded:opsz,wght,FILL,GRAD@20..48,100..700,0..1,-50..200">
<script>
(function(){{
  /* 生成ボタンエリアが見えているときはスティッキーバーを隠す */
  var BAR = 'spm-sticky-bar';
  var SEN = 'poster-gen-sentinel';
  function setup() {{
    var bar = document.getElementById(BAR);
    var sen = document.getElementById(SEN);
    if (!bar || !sen) return false;
    var io = new IntersectionObserver(function(entries) {{
      bar.style.display = entries[0].isIntersecting ? 'none' : 'flex';
    }}, {{ rootMargin: '0px' }});
    io.observe(sen);
    return true;
  }}
  /* sentinel はページ後半に挿入されるため MutationObserver で待機 */
  if (!setup()) {{
    var mo = new MutationObserver(function() {{
      if (setup()) mo.disconnect();
    }});
    mo.observe(document.body, {{ childList: true, subtree: true }});
  }}
}})();
</script>
""",
        unsafe_allow_html=True,
    )


def _safe_filename(title: str) -> str:
    """
    ポスタータイトルをダウンロードファイル名に使える文字列に変換する。
    使用不可文字を _ に置換し、最大 20 文字に切り詰める。
    """
    safe = "".join("_" if c in _FILENAME_INVALID else c for c in title.strip())
    safe = safe.strip("_")
    return safe[:20] or "poster"


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

def compute_layout(
    show_title: bool,
    num_games:  int = MAX_GAMES,
    header_h:   int | None = None,
) -> dict:
    """
    全体見出しの有無・ゲーム本数に応じてレイアウト定数を動的に計算する。
    header_h が None の場合は _actual_header_h（ensure_font で実測更新済み）を使用。
    出力は常に 1920×1080 px 固定。下端は FOOTER_H(36)px のフッター帯で確保。
    """
    if header_h is None:
        header_h = _actual_header_h if show_title else 0
    else:
        header_h = header_h if show_title else 0
    rows      = num_games // COLS
    grid_h    = CANVAS_H - header_h - FOOTER_H

    card_w = (CANVAS_W - MARGIN * (COLS + 1)) // COLS
    card_h = (grid_h   - MARGIN * (rows + 1)) // rows

    text_x_offset = THUMB_W + TEXT_PAD
    text_area_w   = card_w - text_x_offset - TEXT_PAD

    # タイトル最大高さはカード高さに比例させる（8本/10本・見出しあり/なしで自動調整）
    title_max_h  = max(TITLE_BOX_MIN_H, int(card_h * TITLE_MAX_H_RATIO))
    title_y      = TEXT_PAD

    review_y     = title_y + title_max_h + ROW_GAP
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
        "review_y":      review_y,
        "review_max_h":  review_max_h,
    }


# ═══════════════════════════════════════════════════════════
#  フォント管理
# ═══════════════════════════════════════════════════════════

def ensure_font() -> bool:
    """
    フォントが存在しなければ FONT_URLS を順番に試してダウンロードする（初回起動時のみ）。
    すべて失敗した場合は Pillow デフォルトフォントにフォールバックする。
    成功・失敗いずれの場合も _actual_header_h をフォント実測値で更新する。
    """
    global _actual_header_h
    if os.path.exists(FONT_FILENAME):
        _update_actual_header_h()
        return True
    if st.session_state.get("_font_failed"):
        return False
    with st.spinner("フォントをセットアップしています（初回のみ）..."):
        for url in FONT_URLS:
            try:
                resp = requests.get(url, timeout=120)
                resp.raise_for_status()
                with open(FONT_FILENAME, "wb") as f:
                    f.write(resp.content)
                _update_actual_header_h()
                return True
            except Exception:
                continue
    st.warning(
        "フォントのダウンロードに失敗しました。システムフォントで代替します。\n"
        f"（試行した URL: {len(FONT_URLS)} 件）"
    )
    st.session_state["_font_failed"] = True
    _update_actual_header_h()
    return False


def _update_actual_header_h() -> None:
    """フォント実測値から全体見出しヘッダー高さを計算して _actual_header_h に反映する。"""
    global _actual_header_h
    try:
        f   = get_font(HEADER_FONT_PT)
        bb  = f.getbbox("Agあ|")          # アセンダ〜ディセンダを含む代表バウンディングボックス
        fh  = bb[3] - bb[1]               # フォント実高（px）
        _actual_header_h = TITLE_V_PAD + fh + TITLE_V_PAD + ACCENT_LINE_H
    except Exception:
        _actual_header_h = HEADER_H


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

@st.cache_data(ttl=_CACHE_TTL, max_entries=_CACHE_MAX_SEARCH)
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


@st.cache_data(ttl=_CACHE_TTL, max_entries=_CACHE_MAX_DETAILS)
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

@st.cache_data(ttl=_CACHE_TTL, max_entries=_CACHE_MAX_IMAGES)
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
    target_w × target_h にリサイズする（cover モード）。
    背景ぼかし生成など「領域を全面で埋める」用途で使用。
    失敗時はグレー画像を返す。
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


def load_pil_image_contain(
    url: str,
    target_w: int,
    target_h: int,
    bg_color: tuple = (0, 0, 0),
) -> Image.Image:
    """
    URL から画像を読み込み、アスペクト比を保ったまま target_w × target_h に
    収まるよう縮小し、余白を bg_color で塗りつぶす（contain / letterbox モード）。
    サムネイルを切り欠きなく全体表示したい場合に使用。
    失敗時はグレー画像を返す。
    """
    canvas = Image.new("RGB", (target_w, target_h), bg_color)
    raw = _fetch_raw_image(url)
    if not raw:
        return canvas
    try:
        img = Image.open(io.BytesIO(raw)).convert("RGB")
        src_w, src_h = img.size
        # min スケールで全体が収まる最大サイズを計算
        scale = min(target_w / src_w, target_h / src_h)
        new_w = max(1, int(src_w * scale))
        new_h = max(1, int(src_h * scale))
        img = img.resize((new_w, new_h), Image.LANCZOS)
        # 中央揃えで貼り付け
        left = (target_w - new_w) // 2
        top  = (target_h - new_h) // 2
        canvas.paste(img, (left, top))
        return canvas
    except Exception:
        return canvas


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
    # contain モード: 全体が見えるよう縮小し、余白は黒ベタで埋める
    if game.get("age_restricted"):
        thumb = make_age_restricted_image(THUMB_W, L["card_h"])
    else:
        thumb = load_pil_image_contain(game["image_url"], THUMB_W, L["card_h"], bg_color=(0, 0, 0))
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
    # 割引価格（例: "-50%  ¥1,200"）は割引率を SALE_GREEN、定価を accent で分割描画
    if price_text.startswith("-") and "  " in price_text:
        disc_part, rest_part = price_text.split("  ", 1)
        prefix_w = int(draw.textlength(disc_part + "  ", font=price_font))
        draw.text(
            (bx1 + PRICE_BADGE_PAD, by1 + PRICE_BADGE_PAD),
            disc_part, font=price_font, fill=SALE_GREEN,
        )
        draw.text(
            (bx1 + PRICE_BADGE_PAD + prefix_w, by1 + PRICE_BADGE_PAD),
            rest_part, font=price_font, fill=theme["accent"],
        )
    else:
        draw.text(
            (bx1 + PRICE_BADGE_PAD, by1 + PRICE_BADGE_PAD),
            price_text, font=price_font, fill=theme["accent"],
        )


    tx = x0 + L["text_x_offset"]
    ty = y0

    # ── ゲームタイトル（小さめ・auto-scale） ─────────────────
    t_font, t_wrapped = fit_text_in_box(
        draw, game["title"], TITLE_FONT_PT, L["text_area_w"], L["title_max_h"],
        min_size=TITLE_MIN_PT,
    )
    draw.text((tx, ty + L["title_y"]), t_wrapped, font=t_font, fill=theme["text1"])

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
    num_games: int = MAX_GAMES,
) -> Image.Image:
    """
    1920 × 1080 の Steam 布教まとめポスターを生成して PIL Image として返す。

    レイアウト:
      ヘッダー（show_title=True 時のみ）: _actual_header_h px（TITLE_V_PAD×2 + フォント実高 + ACCENT_LINE_H）
      グリッド: COLS=2 列 × rows 行（num_games から自動算出）
      フッター: FOOTER_H px（アクセントライン + ウォーターマーク）
    """
    h_font  = get_font(HEADER_FONT_PT)
    _ref_bb = h_font.getbbox("Agあ|")   # text_y のアセンダ補正用
    layout  = compute_layout(show_title, num_games)   # _actual_header_h を自動参照

    theme  = THEMES[theme_name]
    canvas = Image.new("RGB", (CANVAS_W, CANVAS_H), theme["bg"])
    draw   = ImageDraw.Draw(canvas)

    if show_title:
        draw.rectangle([0, 0, CANVAS_W, layout["header_h"]], fill=theme["header"])
        draw.rectangle(
            [0, layout["header_h"] - ACCENT_LINE_H, CANVAS_W, layout["header_h"]],
            fill=theme["accent"],
        )
        if poster_title.strip():
            tb = draw.textbbox((0, 0), poster_title, font=h_font)
            tw = tb[2] - tb[0]
            text_y = TITLE_V_PAD - (_ref_bb[1])   # 上余白 TITLE_V_PAD（ascender offset 補正）
            draw.text(
                ((CANVAS_W - tw) // 2, text_y),
                poster_title, font=h_font, fill=theme["text1"],
            )

    # ── グリッド中央縦罫線（2列の境界）────────────────────────────
    cx       = CANVAS_W // 2
    div_x0   = cx - CENTER_DIV_W // 2
    div_x1   = cx + CENTER_DIV_W // 2
    div_y0   = layout["header_h"] + MARGIN
    div_y1   = CANVAS_H - FOOTER_H - MARGIN
    draw.rectangle([div_x0, div_y0, div_x1, div_y1], fill=theme["accent"])

    for i, game in enumerate(games[: layout["num_games"]]):
        draw_card(canvas, draw, i, game, theme, bg_style, blur_r, layout)

    # ── 行間横罫線（各行の下端に描画。最終行・フッター直前は除く）────────
    for row in range(layout["rows"] - 1):
        ry = layout["header_h"] + MARGIN + (row + 1) * (layout["card_h"] + MARGIN) - ROW_DIV_H // 2
        draw.rectangle([MARGIN, ry, CANVAS_W - MARGIN, ry + ROW_DIV_H], fill=theme["accent"])

    # フッター帯（ヘッダーと対称的なデザイン）
    footer_y = CANVAS_H - FOOTER_H
    draw.rectangle([0, footer_y, CANVAS_W, CANVAS_H], fill=theme["header"])
    draw.rectangle([0, footer_y, CANVAS_W, footer_y + ACCENT_LINE_H], fill=theme["accent"])

    # ウォーターマーク（フッター帯内に縦中央揃えで配置）
    wm_font = get_font(WM_FONT_PT)
    wm_text = f"Generated by {APP_NAME}"
    wm_w    = int(draw.textlength(wm_text, font=wm_font))
    wm_bb   = draw.textbbox((0, 0), wm_text, font=wm_font)
    wm_h    = wm_bb[3] - wm_bb[1]
    wm_y    = footer_y + ACCENT_LINE_H + (FOOTER_H - ACCENT_LINE_H - wm_h) // 2
    draw.text(
        (CANVAS_W - wm_w - 20, wm_y),
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


def _price_badge_html(price_raw: str) -> str:
    """
    価格文字列を Steam 青ボーダーの囲み枠バッジ HTML に変換する（UI 用）。
    XSS 対策として html.escape() でエスケープ済み。
    """
    return (
        "<span style='display:inline-block;padding:2px 8px;"
        "border:1px solid #66c0f4;border-radius:4px;"
        "font-size:0.8rem;color:#66c0f4;line-height:1.6;"
        f"white-space:nowrap'>{html.escape(price_raw)}</span>"
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

    フェーズ管理:
    - 検索フェーズ: ゲーム未選択 OR ユーザーが「検索に戻る」を押した
        → 検索フォーム + 検索結果のみ表示
    - 編集フェーズ: ゲーム選択済み
        → 2カラム（左:画像 / 右:入力フォーム）のみ表示
    フェーズ切替フラグ: session_state[f"dlg_search_back_{i}"]
    """
    game            = st.session_state.games[i]
    in_search_phase = game is None or f"dlg_search_back_{i}" in st.session_state

    st.caption(f"スロット {i + 1:02d}")

    # ════════════════════════════════════════════════════════
    # 検索フェーズ
    # ════════════════════════════════════════════════════════
    if in_search_phase:
        if game is not None:
            # 選び直し中: 現在の選択をサブテキストで案内
            st.caption(f"現在の選択: {game['title']}　／　新しいゲームを検索して選択してください")
        st.divider()

        # ── 検索フォーム（Enter キー or ボタンで送信）────────
        with st.form(key=f"dlg_form_{i}", border=False):
            col_q, col_btn = st.columns([5, 1])
            with col_q:
                st.text_input(
                    "ゲームを検索",
                    key=f"dlg_q_{i}",
                    placeholder="タイトル（日英）または AppID（例: 570）を入力して Enter",
                    label_visibility="collapsed",
                    help="Steam上のタイトル（日本語・英語）で検索できます。略称ではヒットしない場合があります。",
                )
            with col_btn:
                search_clicked = st.form_submit_button(
                    "検索", icon=":material/search:", use_container_width=True,
                )

        if search_clicked:
            q = st.session_state.get(f"dlg_q_{i}", "").strip()
            if not q:
                st.warning("キーワードを入力してください。")
            elif q.isdigit():
                # AppID 直接入力
                app_id = int(q)
                with st.spinner(f"AppID {app_id} のデータを取得しています..."):
                    details = get_game_details(app_id)
                if details.get("age_restricted"):
                    st.warning(
                        "このタイトルは年齢制限コンテンツのため Steam API から詳細を取得できませんでした。"
                        "ポスターには制限マークが表示されます。",
                        icon=":material/block:",
                    )
                elif not details.get("title"):
                    st.warning(
                        f"AppID {app_id} のゲーム情報が取得できませんでした。"
                        "ID が正しいか確認してください。",
                        icon=":material/error:",
                    )
                st.session_state.games[i] = {
                    "app_id":         app_id,
                    "title":          details.get("title") or f"AppID {app_id}",
                    "image_url":      details.get("image_url"),
                    "price":          details.get("price", "不明"),
                    "review":         "",
                    "age_restricted": details.get("age_restricted", False),
                }
                st.session_state[f"dlg_review_{i}"]  = ""
                st.session_state.search_results[i]   = []
                st.session_state.pop(f"dlg_search_back_{i}", None)
            else:
                # 通常のテキスト検索
                with st.spinner(f"「{q}」を検索しています..."):
                    results = search_steam(q)
                st.session_state.search_results[i] = results
                st.session_state.pop(f"dlg_sel_{i}", None)
                if not results:
                    st.warning(
                        "該当するゲームが見つかりませんでした。"
                        "別のキーワードを試すか、しばらく待ってから再検索してください。"
                    )

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
                    "age_restricted": details.get("age_restricted", False),
                }
                st.session_state[f"dlg_review_{i}"]  = ""
                st.session_state.search_results[i]   = []
                st.session_state.pop(f"dlg_search_back_{i}", None)

        # ── フッターボタン ────────────────────────────────────
        st.divider()
        # 既存ゲームがある場合は編集フェーズへ戻れるボタンを用意
        if game is not None:
            col_back, col_close = st.columns([1, 1])
            with col_back:
                if st.button("編集に戻る", key=f"dlg_editback_{i}",
                             icon=":material/arrow_back:", use_container_width=True):
                    st.session_state.pop(f"dlg_search_back_{i}", None)
                    st.rerun()
            with col_close:
                if st.button("キャンセル", key=f"dlg_close_{i}",
                             icon=":material/close:", use_container_width=True):
                    del st.session_state["editing_slot"]
                    st.rerun()
        else:
            if st.button("閉じる", key=f"dlg_close_{i}",
                         icon=":material/close:"):
                del st.session_state["editing_slot"]
                st.rerun()

    # ════════════════════════════════════════════════════════
    # 編集フェーズ
    # ════════════════════════════════════════════════════════
    else:
        # ── 選び直しボタン ───────────────────────────────────
        if st.button("検索に戻る", key=f"dlg_back_{i}",
                     icon=":material/search:"):
            st.session_state[f"dlg_search_back_{i}"] = True
            st.session_state.search_results[i] = []
            st.rerun()

        st.divider()

        # ── 2カラム: 左=画像(1) / 右=タイトル・価格・入力フォーム(2) ──
        col_img, col_form = st.columns([1, 2])

        with col_img:
            if game.get("age_restricted"):
                _show_age_restricted_thumb(padding="20px 0")
            elif game.get("image_url"):
                st.image(game["image_url"], use_container_width=True)
            else:
                _show_age_restricted_thumb(padding="20px 0")

        with col_form:
            st.markdown(f"### {game['title']}")
            price_raw = "18+ / 詳細取得不可" if game.get("age_restricted") else game["price"]
            st.markdown(_price_badge_html(price_raw), unsafe_allow_html=True)

            review_now = st.text_area(
                "レビュー文",
                height=160,
                key=f"dlg_review_{i}",
                help="文字数や改行が多い場合は、枠に収まるよう自動で文字サイズが縮小されます。",
            )
            review_len = len(review_now or "")

            # ── 文字数上限（レイアウトの review_max_h に比例） ──
            _show_title  = st.session_state.get("show_title", True)
            _num_g       = st.session_state.get("num_games_sel", 10)
            _L           = compute_layout(_show_title, _num_g)
            # 140文字 ≒ review_max_h=84px 相当を基準にスケール
            max_chars    = max(140, int(_L["review_max_h"] * 140 / 84))

            over_limit = review_len > max_chars
            counter_id = f"dlg-rc-{i}"
            color_init = "#e74c3c" if over_limit else "#aaa"
            st.markdown(
                f"<p id='{counter_id}' style='text-align:right;font-size:0.8rem;"
                f"color:{color_init};margin-top:-12px'>{review_len} / {max_chars} 文字</p>",
                unsafe_allow_html=True,
            )
            if over_limit:
                st.error(f"{max_chars} 文字を超えています。文字数を減らしてから保存してください。")

            # ── リアルタイムカウンター（JS） ─────────────────
            components.html(
                f"""<script>
(function(){{
  var CID = '{counter_id}';
  var MAX = {max_chars};
  function attach() {{
    var doc = window.parent.document;
    var ta = null;
    doc.querySelectorAll('[data-testid="stTextArea"] textarea').forEach(function(el) {{
      var wrap = el.closest('[data-testid="stTextArea"]');
      if (!wrap) return;
      var lbl = wrap.querySelector('label');
      if (lbl && lbl.textContent.trim().startsWith('\u30ec\u30d3\u30e5\u30fc\u6587')) ta = el;
    }});
    if (!ta) return false;
    if (ta._rt) ta.removeEventListener('input', ta._rt);
    ta._rt = function() {{
      var n = this.value.length;
      var c = window.parent.document.getElementById(CID);
      if (!c) return;
      c.textContent = n + ' / {max_chars} \u6587\u5b57';
      c.style.color = n > MAX ? '#e74c3c' : '#aaa';
    }};
    ta.addEventListener('input', ta._rt);
    return true;
  }}
  if (!attach()) {{
    var tries = 0;
    var iv = setInterval(function() {{
      if (attach() || ++tries > 20) clearInterval(iv);
    }}, 150);
  }}
}})();
</script>""",
                height=0,
                scrolling=False,
            )

        # ── アクションボタン ─────────────────────────────────
        st.divider()
        col_save, col_clear, col_cancel = st.columns([3, 2, 2])
        with col_save:
            if st.button("保存して閉じる", key=f"dlg_save_{i}",
                         icon=":material/save:",
                         type="primary", use_container_width=True,
                         disabled=over_limit):
                st.session_state.games[i]["review"] = st.session_state.get(f"dlg_review_{i}", "")
                st.session_state.pop(f"dlg_search_back_{i}", None)
                del st.session_state["editing_slot"]
                st.rerun()
        with col_clear:
            if st.button("クリア", key=f"dlg_clear_{i}",
                         icon=":material/delete:",
                         use_container_width=True):
                st.session_state.games[i] = None
                st.session_state.search_results[i] = []
                for k in [f"dlg_review_{i}", f"dlg_q_{i}", f"dlg_search_back_{i}"]:
                    st.session_state.pop(k, None)
                del st.session_state["editing_slot"]
                st.rerun()
        with col_cancel:
            if st.button("キャンセル", key=f"dlg_cancel_{i}",
                         icon=":material/close:",
                         use_container_width=True):
                st.session_state.pop(f"dlg_search_back_{i}", None)
                del st.session_state["editing_slot"]
                st.rerun()


# ═══════════════════════════════════════════════════════════
#  スロットカード（グリッド表示用）
# ═══════════════════════════════════════════════════════════

def render_slot_card(i: int, disabled: bool = False) -> None:
    """
    ポスターのカードレイアウト（サムネ左・テキスト右）に近しい
    ミニカードを Streamlit で描画する。
    disabled=True のとき編集ボタンを非活性にする（並び替えモード用）。
    編集ボタンクリック → edit_dialog を開く。
    """
    game = st.session_state.games[i]

    with st.container(border=True):
        if game:
            # ── 上段: サムネ + タイトル・価格 ─────────────────
            col_thumb, col_info = st.columns([2, 3])
            with col_thumb:
                if game.get("age_restricted"):
                    _show_age_restricted_thumb()
                else:
                    st.image(game["image_url"], use_container_width=True)
            with col_info:
                price_raw = (
                    "18+ / 詳細取得不可"
                    if game.get("age_restricted")
                    else game["price"]
                )
                price_badge = _price_badge_html(price_raw)
                st.markdown(
                    f"<p style='margin:0 0 4px;font-weight:bold;font-size:0.95rem;line-height:1.3'>{game['title']}</p>"
                    f"<p style='margin:0'>{price_badge}</p>",
                    unsafe_allow_html=True,
                )
            # ── 下段: レビュー文（カード全幅・改行対応） ────────
            review = game.get("review", "")
            if review:
                # html.escape() で XSS 対策済みの後、改行を <br> に変換して表示
                review_escaped = html.escape(review).replace("\n", "<br>")
                st.markdown(
                    f"<p style='margin:4px 0 0;font-size:0.8rem;"
                    f"color:#aaa;line-height:1.5'>{review_escaped}</p>",
                    unsafe_allow_html=True,
                )
        else:
            # 空スロットのプレースホルダ
            st.markdown(
                f"<div style='text-align:center;padding:20px 0;"
                f"color:#555;font-size:0.85rem;'>スロット {i + 1:02d}</div>",
                unsafe_allow_html=True,
            )

        if st.button(
            "編集", key=f"btn_edit_{i}",
            icon=":material/edit:",
            use_container_width=True,
            disabled=disabled,
        ):
            st.session_state["editing_slot"] = i
            # ダイアログを開く際にウィジェットをゲームの保存値でリセット
            if game:
                st.session_state[f"dlg_review_{i}"] = game.get("review", "")


# ═══════════════════════════════════════════════════════════
#  メイン
# ═══════════════════════════════════════════════════════════

def main() -> None:
    st.set_page_config(
        page_title="SteamPosterMaker",
        layout="wide",
    )

    init_session()
    ensure_font()
    st.markdown(_GLOBAL_CSS, unsafe_allow_html=True)

    st.markdown(
        "<h1 style='text-align:center;'>SteamPosterMaker</h1>",
        unsafe_allow_html=True,
    )

    # ── レイアウト・進捗を先に計算 ──────────────────────────────
    show_title        = st.session_state.get("show_title", True)
    num_games_sel     = st.session_state.get("num_games_sel", 10)
    layout            = compute_layout(show_title, num_games_sel)
    num_games         = layout["num_games"]
    filled            = sum(1 for g in st.session_state.games[:num_games] if g is not None)
    already_generated = "last_poster_bytes" in st.session_state

    # ── スティッキーボトムバー ─────────────────────────────────
    # JS クリック → URL クエリ ?_sg= 変更 → リラン → _sticky_triggered で生成実行
    _sticky_triggered = st.session_state.pop("_sticky_generate", False)
    if st.query_params.get("_sg"):
        st.query_params.clear()
        st.session_state["_sticky_generate"] = True
        st.rerun()

    _render_sticky_bar(filled, num_games, already_generated)


    # ── 開発者ツール（DEV_MODE=True のときのみ表示）────────────────
    if DEV_MODE:
        with st.expander("開発者ツール", icon=":material/science:"):
            if st.button(
                "テストデータを入力",
                key="dev_fill_btn",
                icon=":material/science:",
                use_container_width=True,
            ):
                picks = random.sample(
                    _DEV_SAMPLE_GAMES,
                    min(num_games, len(_DEV_SAMPLE_GAMES)),
                )
                for idx, game_data in enumerate(picks):
                    st.session_state.games[idx] = {
                        k: (list(v) if isinstance(v, list) else v)
                        for k, v in game_data.items()
                    }
                    st.session_state[f"dlg_review_{idx}"] = game_data["review"]
                    st.session_state.pop(f"dlg_search_back_{idx}", None)
                for idx in range(len(picks), MAX_GAMES):
                    st.session_state.games[idx] = None
                st.rerun()

    st.divider()

    # ── 見出し設定（常時表示）+ 表示設定ポップオーバー ────────
    # show_title は上で session_state から先読み済み。
    # 3 カラムの with ブロックは連続して展開する（間に非 UI コードを挟むと
    # Streamlit の列レンダリングが分断され再描画タイミングが乱れるため）。
    col_tog, col_ttl, col_pop = st.columns([1, 3, 1])
    with col_tog:
        show_title = st.toggle(
            "全体見出し",
            value=True,
            key="show_title",
            help="OFF にすると上部の見出し帯が非表示になり、ゲームカードが少し大きくなります（常に10本・1920×1080 出力）",
        )
    with col_ttl:
        if show_title:
            poster_title = st.text_input(
                "見出しテキスト",
                value="2026年 神ゲー10選",
                max_chars=25,
                placeholder="25文字以内",
                key="poster_title",
                label_visibility="collapsed",
                help="ポスター上部に大きな文字で表示されるタイトルです。空欄にすると見出しテキストなし（帯とアクセントラインは残ります）で生成されます。",
            )
        else:
            # トグルOFF時は入力欄を非表示にして説明テキストだけ表示
            # session_state の値は保持されるため、ON に戻すと入力内容が復元される
            poster_title = st.session_state.get("poster_title", "")
            st.caption("見出しなし")
    with col_pop:
        with st.popover("表示設定", icon=":material/settings:", use_container_width=True):
            st.radio(
                "ゲーム数",
                [8, 10],
                horizontal=True,
                key="num_games_sel",
                help="8本: カードが大きめ / 10本: カードが小さめ",
            )
            st.divider()
            theme_name = st.selectbox(
                "テーマ",
                list(THEMES.keys()),
                key="theme_sel",
            )
            # カラースウォッチ（bg / accent / card_bg の3色を表示）
            _t = THEMES[theme_name]
            _swatch_html = "".join(
                f"<span title='{label}' style='display:inline-block;width:22px;height:22px;"
                f"border-radius:5px;background:rgb{color};margin-right:5px;"
                f"border:1px solid #555;vertical-align:middle'></span>"
                for label, color in [
                    ("背景", _t["bg"]),
                    ("アクセント", _t["accent"]),
                    ("カード", _t["card_bg"]),
                ]
            )
            st.markdown(_swatch_html, unsafe_allow_html=True)
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
    # filled / already_generated はページ冒頭で先行計算済み
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

    # ── カードグリッド ───────────────────────────────────────
    # 並び替えモード時は編集ボタンを disabled にして誤操作を防ぐ
    is_reorder = st.session_state["reorder_mode"]
    num_rows = (num_games + 1) // 2
    for row in range(num_rows):
        grid_cols = st.columns(2, gap="small")
        for col_idx, gcol in enumerate(grid_cols):
            slot_idx = row * 2 + col_idx
            if slot_idx < num_games:
                with gcol:
                    render_slot_card(slot_idx, disabled=is_reorder)

    st.divider()

    # ── ポスター生成 ────────────────────────────────────────
    # sentinel が画面内に入ったら、スティッキーバーの IntersectionObserver が自動で非表示にする
    st.markdown('<div id="poster-gen-sentinel"></div>', unsafe_allow_html=True)
    if filled > 0 and filled < num_games:
        st.info(
            f"現在 **{filled}** 本のゲームが登録されています。"
            f"未入力の枠 {num_games - filled} 個は「空欄カード」として出力されます。",
            icon=":material/info:",
        )
    generate_btn = st.button(
        "再生成する" if already_generated else "ポスターを生成する",
        icon=":material/refresh:" if already_generated else ":material/palette:",
        type="primary",
        use_container_width=True,
        disabled=(filled == 0),
    )

    if generate_btn or _sticky_triggered:
        games_slice = st.session_state.games[:num_games]

        # 前回の巨大画像バイト列を事前に解放し、新旧データのメモリ二重保持を防ぐ
        for _key in ("last_poster_bytes", "last_poster_meta"):
            st.session_state.pop(_key, None)

        # gen_status.update(state="complete") はストリーミングデルタとして即送信されるため、
        # 画像レンダリング（最終フルステート）より先にブラウザへ届き、タイムラグが生じる。
        # そのため成功時は update を呼ばず with 終了時の自動完了に委ねる。
        # toast は session_state フラグ経由で st.image の直後に移動し同タイミングに揃える。
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
                        f"Steam からゲーム画像を取得しています"
                        f"（{len(fetchable)} 本 / {num_games} スロット）..."
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
                    num_games,
                )

                # Step 3: PNG エンコード
                st.write("PNG ファイルに書き出しています...")
                buf = io.BytesIO()
                poster.save(buf, format="PNG", compress_level=1)
                poster.close()   # Pillow Image オブジェクトを即時解放（PNG 書き出し完了後は不要）
                st.session_state["last_poster_bytes"] = buf.getvalue()
                date_str   = datetime.date.today().strftime("%Y%m%d")
                pick_label = f"{num_games}pick"
                title_part = _safe_filename(poster_title) if show_title and poster_title.strip() else ""
                parts      = ["steam", pick_label] + ([title_part] if title_part else []) + [date_str]
                st.session_state["last_poster_meta"] = {
                    "filename": "_".join(parts) + ".png",
                }
                # フラグを立てて、画像表示後に toast を出す（with ブロック内では呼ばない）
                st.session_state["_poster_complete"] = True
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
            use_container_width=True,
        )
        # 画像が描画されてから toast を出す
        if st.session_state.pop("_poster_complete", False):
            st.toast(
                "ポスターが完成しました。ダウンロードボタンから保存できます。",
                icon=":material/check_circle:",
            )

    # ── 免責事項 ────────────────────────────────────────────
    st.divider()
    st.markdown(
        "<p style='text-align:center;font-size:0.8rem;color:#aaa;line-height:1.8;margin:0'>"
        "<strong>本アプリは非公式のファンメイドツールです。</strong><br>"
        "Steam および Valve Corporation とは直接的な関わりはありません。<br>"
        "Steam の商標・ロゴは Valve Corporation の財産です。"
        "</p>",
        unsafe_allow_html=True,
    )
    st.markdown(_X_BUTTON_HTML, unsafe_allow_html=True)
    with st.expander("利用規約・免責事項"):
        st.markdown(
            """
**著作権について**
* 本アプリが生成するポスターに含まれるゲームタイトル・サムネイル画像の著作権は、各ゲームパブリッシャーおよび Valve Corporation に帰属します。
* 生成した画像は、個人利用・SNS投稿（X/Twitterなど）による「ゲームの紹介・布教」を目的とした範囲でのみご利用ください。
* 商用利用（販売・広告での利用・有償頒布など）は固くお控えください。

**ユーザーの入力内容に関する責任**
* ユーザーが入力した「レビュー文」等のテキスト内容、およびそれを含む生成画像を利用したことによって生じたトラブル（第三者との紛争や権利侵害など）について、開発者は一切の責任を負いません。公序良俗に反する入力はお控えください。

**Steam API の仕様と年齢制限タイトルについて**
* 本アプリはゲーム情報の取得に Steam の公開 Web API（認証不要）を使用しています。ユーザーのアカウント情報や個人情報を取得・送信することはありません。
* **【重要】** APIの仕様上、**「年齢制限（18禁）」が設定されているゲームは、画像や価格情報などを自動取得できません。** 該当タイトルを選択した場合は、自動的に専用のダミー画像（18+アイコン）に置き換わりますのでご了承ください。

**データの保持について**
* 本アプリ上で入力されたテキストや生成されたポスター画像は、ユーザーのブラウザ上（一時メモリ）でのみ処理されており、開発者のサーバーやデータベースに永続的に保存・収集されることはありません。

**動作保証について**
* Steam Web API の仕様変更やサーバー状況により、一時的にゲーム情報の取得に失敗する場合があります。
* 本アプリの動作や出力結果について、開発者は一切の責任を負いません。また、予告なく機能の変更や公開停止を行う場合があります。
* 本アプリは <a href="https://streamlit.io" target="_blank" style="color:#a8c8e8;text-decoration:underline">Streamlit</a> を使用して構築されています。Streamlit Cloud の<a href="https://streamlit.io/terms-of-use" target="_blank" style="color:#a8c8e8;text-decoration:underline">利用規約</a>も併せて適用されます。
            """,
            unsafe_allow_html=True,
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
