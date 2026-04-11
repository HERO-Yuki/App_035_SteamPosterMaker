"""
App_035 SteamPosterMaker
Steamゲーム布教まとめ画像（最大10本紹介）自動生成 Webアプリ
"""

# ── Standard Library ───────────────────────────────────────
import html
import io
import os
import re
import random
import datetime
import urllib.parse
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
TITLE_V_PAD      = 8    # 全体見出しの上下パディング（px）— ヘッダー高さ計算（_actual_header_h）にも使用
TITLE_FONT_PT    = 28   # ゲームタイトル（初期）
TITLE_MIN_PT     = 16   # ゲームタイトル（最小）
REVIEW_FONT_PT   = 26   # レビュー文（初期）— 見出しあり8本モードで約4行が収まるサイズ
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
APP_URL       = "https://steam-poster-maker.streamlit.app"

# ── Streamlit UI テーマ色（.streamlit/config.toml と同期すること） ──────────
# primaryColor — スティッキーバーボタン・生成ボタン等の強調色
_PRIMARY_COLOR = "#d99200"
# backgroundColor / secondaryBackgroundColor — スティッキーバーの背景・ボーダー色
_STEAM_BG      = "#1b2838"
_STEAM_BG2     = "#2a475e"

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

# X (Twitter) ブランドカラーのリンクボタン HTML（テキスト部は main() で t() を使って描画）
_X_BUTTON_ICON_HTML = """
<div style="text-align:center;margin:0 0 20px;">
  <a href="https://x.com/Yuki_HERO44" target="_blank" rel="noopener noreferrer" class="x-btn">
    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="white">
      <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-4.714-6.231-5.401 6.231H2.747l7.73-8.835L1.254 2.25H8.08l4.258 5.629 5.906-5.629Zm-1.161 17.52h1.833L7.084 4.126H5.117z"/>
    </svg>
    @Yuki_HERO44
  </a>
</div>
"""

_OFUSE_BUTTON_HTML = """
<div style="text-align:center;margin:0 0 20px;">
  <a href="https://ofuse.me/d57de631" target="_blank" rel="noopener noreferrer" class="ofuse-btn">
    OFUSE
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
section[data-testid="stMain"] > div > div { padding-bottom: 64px !important; }
/* Streamlit の stMainBlockContainer 自身の padding-bottom も除去してフッターを最下部に */
[data-testid="stMainBlockContainer"] { padding-bottom: 0 !important; }

/* ── X ブランドリンクボタン ── */
.x-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  min-width: 160px;
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

/* ── OFUSE 応援ボタン ── */
.ofuse-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  min-width: 160px;
  background: #2882A7;
  color: #fff !important;
  border: 1px solid #2882A7;
  border-radius: 6px;
  padding: 6px 14px;
  font-size: 0.85rem;
  font-weight: bold;
  text-decoration: none !important;
  line-height: 1.4;
  white-space: nowrap;
  transition: opacity 0.2s ease;
}
.ofuse-btn:visited, .ofuse-btn:active, .ofuse-btn:focus {
  color: #fff !important;
  text-decoration: none !important;
}
.ofuse-btn:hover {
  opacity: 0.8;
  color: #fff !important;
}

/* ── 言語トグルボタン: テキスト折り返しを防ぐ ── */
div[data-testid="stButton"] > button { white-space: nowrap !important; }

/* ── コピーライトフッター（全幅・最下部） ── */
.spm-copyright {
  background: #000;
  color: #fff;
  text-align: center;
  font-size: 0.75rem;
  padding: 14px 20px;
  /* Streamlit の content padding を打ち消して全幅に */
  margin: 8px calc(-50vw + 50%) 0;
  width: 100vw;
}

/* ═══════════════════════════════════════════════════
   モバイル対応 (≤ 768px)
   ═══════════════════════════════════════════════════ */
@media (max-width: 768px) {

  /* ── ゲームスロット: 2列 → 1列縦積み ── */
  [data-testid="stHorizontalBlock"]:has(
    [data-testid="stVerticalBlockBorderWrapper"]
  ) {
    flex-direction: column !important;
  }

  /* ── フッター列: 縦積み & セパレーターを横線に変換 ── */
  [data-testid="stHorizontalBlock"]:has(.footer-sep) {
    flex-direction: column !important;
    align-items: stretch !important;
  }
  .footer-sep {
    border-left: none !important;
    border-top: 1px solid #444 !important;
    width: 100% !important;
    height: 1px !important;
    min-height: 1px !important;
    margin: 0.5rem 0 !important;
  }
  /* フッターの X / OFUSE ボタンを縦積み時に横長に */
  [data-testid="stHorizontalBlock"]:has(.footer-sep) .x-btn,
  [data-testid="stHorizontalBlock"]:has(.footer-sep) .ofuse-btn {
    width: 72% !important;
    max-width: 280px !important;
    justify-content: center !important;
  }

  /* ── ダイアログ内 2カラム → 縦積み ── */
  [data-testid="stDialog"] [data-testid="stHorizontalBlock"] {
    flex-direction: column !important;
  }

  /* ── X / OFUSE ボタン: タッチターゲット拡大 ── */
  .x-btn, .ofuse-btn {
    padding: 10px 18px !important;
    font-size: 0.95rem !important;
    min-width: 140px !important;
  }

  /* ── スティッキーバー: 余白・フォント縮小 ── */
  #spm-sticky-bar > div {
    padding: 0 12px !important;
    gap: 8px !important;
  }
  #spm-sticky-bar-progress {
    width: 90px !important;
  }
  #spm-sticky-bar-label {
    font-size: 0.65rem !important;
  }
  #spm-sticky-bar-btn {
    padding: 8px 12px !important;
    font-size: 0.8rem !important;
  }

  /* ── コピーライトフッター: SP では全幅維持 ── */
  .spm-copyright {
    margin: 8px -1rem 0 !important;
    width: calc(100% + 2rem) !important;
    font-size: 0.7rem !important;
    padding: 12px 12px !important;
  }
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


# ═══════════════════════════════════════════════════════════
#  i18n（多言語対応）
# ═══════════════════════════════════════════════════════════

TRANSLATIONS: dict[str, dict[str, str]] = {
    "ja": {
        # ヘッダー設定行
        "heading_toggle":       "全体見出し",
        "heading_toggle_help":  "OFF にすると上部の見出し帯が非表示になり、ゲームカードが少し大きくなります（常に10本・1920×1080 出力）",
        "heading_placeholder":  "25文字以内",
        "heading_default":      "2026年 神ゲー10選",
        "heading_help":         "ポスター上部に大きな文字で表示されるタイトルです。空欄にすると見出しテキストなし（帯とアクセントラインは残ります）で生成されます。",
        "heading_none_cap":     "見出しなし",
        # 設定ポップオーバー
        "num_games_popover":    "ゲーム数",
        "num_games_label":      "ゲーム数",
        "num_games_help":       "8本: カードが大きめ / 10本: カードが小さめ",
        "design_popover":       "デザイン設定",
        "theme_label":          "テーマ",
        "bg_style_label":       "背景スタイル",
        "bg_style_blur":        "ぼかし",
        "bg_style_solid":       "単色",
        "blur_label":           "ぼかし強度",
        "blur_help":            "数値が大きいほどぼかしが強くなります",
        "show_price_label":     "価格バッジを表示する",
        # スロットエリア
        "slots_header":         "ゲームスロット",
        "slots_count_prefix":   "登録数",
        "sort_btn":             "並び替え",
        "sort_done_btn":        "並び替え完了",
        "clear_all_btn":        "全クリア",
        "sort_drag_info":       "ドラッグして順序を変更し、完了したら「並び替え完了」を押してください。",
        "empty_slot_card":      "スロット {n:02d}",
        # 生成ボタン周辺
        "empty_slots_info":     "現在 **{filled}** 本のゲームが登録されています。未入力の枠 {n} 個は「空欄カード」として出力されます。",
        "generate_btn":         "ポスターを生成する",
        "regenerate_btn":       "再生成する",
        "download_btn":         "PNG でダウンロード",
        "preview_caption":      "プレビュー（実際は 1920×1080 で出力）",
        "toast_done":           "ポスターが完成しました。ダウンロードボタンから保存できます。",
        # 生成ステータス
        "status_title":         "ポスターを生成しています...",
        "status_fetch":         "Steam からゲーム画像を取得しています（{n} 本 / {total} スロット）...",
        "status_compose":       "1920 × 1080 px の画像を合成しています...",
        "status_encode":        "PNG ファイルに書き出しています...",
        "status_error":         "生成に失敗しました",
        # 編集ダイアログ
        "slot_caption":         "スロット {n:02d}",
        "reselect_caption":     "現在の選択: {title}　／　新しいゲームを検索して選択してください",
        "search_ph":            "タイトル（日英）・AppID・Steam ストア URL を入力して Enter",
        "search_help":          "Steam URL を貼り付けると自動でゲームを取得します。略称ではヒットしない場合があります。",
        "search_btn":           "検索",
        "warn_empty_query":     "キーワードを入力してください。",
        "warn_age":             "このタイトルは年齢制限コンテンツのため Steam API から詳細を取得できませんでした。ポスターには制限マークが表示されます。",
        "warn_id_notfound":     "AppID {id} のゲーム情報が取得できませんでした。ID が正しいか確認してください。",
        "warn_notfound":        "該当するゲームが見つかりませんでした。別のキーワードを試すか、しばらく待ってから再検索してください。",
        "spin_appid":           "AppID {id} のデータを取得しています...",
        "spin_search":          "「{q}」を検索しています...",
        "spin_details":         "「{name}」のデータを取得しています...",
        "spin_url":             "Steam URL からゲーム情報を取得しています...",
        "confirm_game_btn":     "このゲームに決定",
        "back_to_search_btn":   "検索に戻る",
        "back_to_edit_btn":     "編集に戻る",
        "close_btn":            "閉じる",
        "cancel_btn":           "キャンセル",
        "review_label":         "レビュー文",
        "review_help":          "ポスターに約4行分の文章が収まります（見出しあり8本モード基準）。超える場合はフォントサイズが自動縮小されます。",
        "save_btn":             "保存して閉じる",
        "dlg_clear_btn":        "クリア",
        "char_counter_tmpl":    "{n} / {max} 文字",
        "char_counter_suffix":  "文字",
        "over_limit_err":       "{max} 文字を超えています。文字数を減らしてから保存してください。",
        "age_price_label":      "18+ / 詳細取得不可",
        # スロットカード
        "edit_btn":             "編集",
        "empty_slot_sort":      "空きスロット {n:02d}",
        # 全クリアダイアログ
        "clear_all_warning":    "登録されているすべてのゲームを削除します。この操作は取り消せません。",
        "clear_all_confirm":    "すべて削除する",
        # X ボタン・OFUSE ボタン
        "ofuse_header":         "開発者を応援する",
        "author_section":       "開発者をフォローする",
        "disclaimer_unofficial":"本アプリは非公式のファンメイドツールです。",
        "disclaimer_no_relation":"Steam および Valve Corporation とは直接的な関わりはありません。",
        "disclaimer_trademark": "Steam の商標・ロゴは Valve Corporation の財産です。",
        "feedback_header":      "フィードバック",
        "feedback_body":        "バグ報告や機能のご要望はこちら",
        "feedback_btn":         "要望・バグ報告フォーム",
        # 利用規約エクスパンダー
        "tos_expander":         "利用規約・免責事項",
        # スティッキーバー
        "sticky_count":         "{filled} / {num} 本",
        # DEV モード
        "dev_expander":         "開発者ツール",
        "dev_fill_btn":         "テストデータを入力",
        # 言語トグル
        "lang_toggle":          "EN",
        # X シェアボタン
        "share_header":         "作ったポスターをシェアしよう",
        "share_info":           "Xの投稿画面が開いたら、保存したポスター画像を添付して投稿してください。",
        "share_btn":            "X でシェアする",
        "share_tweet_text":     "SteamPosterMakerで推しゲーのポスターを作りました！Steamのおすすめゲームをまとめた画像を自動生成できるツールです。ぜひ試してみて",
        "share_hashtags":       "Steam,おすすめゲーム,SteamPosterMaker",
    },
    "en": {
        # Header row
        "heading_toggle":       "Poster Title",
        "heading_toggle_help":  "Turn OFF to hide the title bar and slightly enlarge game cards (always 10 games / 1920×1080).",
        "heading_placeholder":  "Up to 25 characters",
        "heading_default":      "Top 10 Games of 2026",
        "heading_help":         "Large text shown at the top of the poster. Leave blank to generate without title text (bar and accent line remain).",
        "heading_none_cap":     "No title",
        # Settings popovers
        "num_games_popover":    "# Games",
        "num_games_label":      "# of Games",
        "num_games_help":       "8 games: larger cards / 10 games: smaller cards",
        "design_popover":       "Design",
        "theme_label":          "Theme",
        "bg_style_label":       "Background",
        "bg_style_blur":        "Blur",
        "bg_style_solid":       "Solid",
        "blur_label":           "Blur Intensity",
        "blur_help":            "Higher value = stronger blur",
        "show_price_label":     "Show price badge",
        # Slot area
        "slots_header":         "Game Slots",
        "slots_count_prefix":   "Registered",
        "sort_btn":             "Reorder",
        "sort_done_btn":        "Done Reordering",
        "clear_all_btn":        "Clear All",
        "sort_drag_info":       'Drag to reorder, then press "Done Reordering".',
        "empty_slot_card":      "SLOT {n:02d}",
        # Generate area
        "empty_slots_info":     "**{filled}** game(s) registered. {n} empty slot(s) will appear as blank cards.",
        "generate_btn":         "Generate Poster",
        "regenerate_btn":       "Regenerate",
        "download_btn":         "Download PNG",
        "preview_caption":      "Preview (actual output: 1920×1080)",
        "toast_done":           "Poster ready! Use the download button to save.",
        # Generation status
        "status_title":         "Generating poster...",
        "status_fetch":         "Fetching game images from Steam ({n} / {total} slots)...",
        "status_compose":       "Compositing 1920 × 1080 px canvas...",
        "status_encode":        "Encoding PNG...",
        "status_error":         "Generation failed",
        # Edit dialog
        "slot_caption":         "Slot {n:02d}",
        "reselect_caption":     "Current: {title} — Search to select a different game",
        "search_ph":            "Title, AppID, or Steam store URL — press Enter",
        "search_help":          "Paste a Steam URL to auto-fetch the game. Abbreviations may not return results.",
        "search_btn":           "Search",
        "warn_empty_query":     "Please enter a keyword.",
        "warn_age":             "This title is age-restricted; Steam API returned no details. A restriction icon will appear on the poster.",
        "warn_id_notfound":     "Could not find game info for AppID {id}. Please verify the ID.",
        "warn_notfound":        "No games found. Try a different keyword or wait before retrying.",
        "spin_appid":           "Fetching data for AppID {id}...",
        "spin_search":          'Searching for "{q}"...',
        "spin_details":         'Fetching data for "{name}"...',
        "spin_url":             "Fetching game info from Steam URL...",
        "confirm_game_btn":     "Select This Game",
        "back_to_search_btn":   "Back to Search",
        "back_to_edit_btn":     "Back to Edit",
        "close_btn":            "Close",
        "cancel_btn":           "Cancel",
        "review_label":         "Review",
        "review_help":          "About 4 lines fit on the poster (8-game + title mode). Font auto-shrinks if text is too long.",
        "save_btn":             "Save & Close",
        "dlg_clear_btn":        "Clear",
        "char_counter_tmpl":    "{n} / {max} chars",
        "char_counter_suffix":  "chars",
        "over_limit_err":       "Over {max} characters. Please shorten the text before saving.",
        "age_price_label":      "18+ / Details unavailable",
        # Slot card
        "edit_btn":             "Edit",
        "empty_slot_sort":      "Empty Slot {n:02d}",
        # Clear all dialog
        "clear_all_warning":    "This will remove all registered games. This cannot be undone.",
        "clear_all_confirm":    "Delete All",
        # X button / OFUSE button
        "ofuse_header":         "Support the developer",
        "author_section":       "Follow the developer",
        "disclaimer_unofficial":"This is an unofficial fan-made tool.",
        "disclaimer_no_relation":"It has no affiliation with Steam or Valve Corporation.",
        "disclaimer_trademark": "Steam trademarks and logos are the property of Valve Corporation.",
        "feedback_header":      "Feedback",
        "feedback_body":        "Bug reports and feature requests welcome",
        "feedback_btn":         "Send Feedback",
        # Terms of Service expander
        "tos_expander":         "Terms of Use & Disclaimer",
        # Sticky bar
        "sticky_count":         "{filled} / {num}",
        # DEV mode
        "dev_expander":         "Dev Tools",
        "dev_fill_btn":         "Fill with Test Data",
        # Language toggle
        "lang_toggle":          "日本語",
        # X share button
        "share_header":         "Share Your Poster!",
        "share_info":           "When X opens, attach the downloaded poster image to complete your post!",
        "share_btn":            "Share on X",
        "share_tweet_text":     "I made a game recommendation poster with SteamPosterMaker! A tool that auto-generates summary images of your favorite Steam games. Check it out",
        "share_hashtags":       "Steam,SteamGames,SteamPosterMaker",
    },
}


def t(key: str, **kwargs) -> str:
    """現在の言語設定でキーに対応する文字列を返す。フォーマット引数がある場合は format() を適用する。"""
    lang = st.session_state.get("lang", "ja")
    text = TRANSLATIONS.get(lang, TRANSLATIONS["ja"]).get(key) \
           or TRANSLATIONS["ja"].get(key, key)
    return text.format(**kwargs) if kwargs else text


def _render_sticky_bar(filled: int, num_games: int, already_generated: bool) -> None:
    """
    画面下部に固定表示するスティッキーボトムバーを st.markdown で描画する。

    構成: [プログレスバー（固定幅）] [生成 / 再生成ボタン] — 中央寄せ。

    ボタンは純粋な HTML ボタンのため、クリック時は JS で URL クエリパラメータ
    `?_sg=<timestamp>` を書き換えて Streamlit のリランを誘発する方式を採用。
    リラン後、main() の冒頭で `st.session_state["_sticky_generate"]` を検知して
    生成処理を実行する。

    バーの表示制御:
      メイン生成エリア手前のセンチネル div（id="poster-gen-sentinel"）が
      ビューポートに入ると、components.html() 経由で注入した IntersectionObserver が
      バーの opacity を 0 → 1 に切り替える（opacity + transition で滑らかにフェード）。
      display ではなく opacity を使用するのは CSS transition が display に非対応なため。
    """
    btn_label  = t("regenerate_btn") if already_generated else t("generate_btn")
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
  background:{_STEAM_BG};border-top:2px solid {_STEAM_BG2};
  padding:8px 0 10px;box-shadow:0 -2px 12px rgba(0,0,0,.5);
  display:flex;justify-content:center;
  opacity:1;transition:opacity 0.4s ease;
">
  <!-- 中央寄せコンテナ（最大幅・左右余白） -->
  <div style="display:inline-flex;align-items:center;gap:16px;padding:0 40px;">
    <!-- プログレスバー（短め・固定幅） -->
    <div id="spm-sticky-bar-progress" style="width:120px;flex-shrink:0;">
      <div id="spm-sticky-bar-label" style="font-size:0.7rem;color:#aaa;margin-bottom:3px;white-space:nowrap;">
        {t("sticky_count", filled=filled, num=num_games)}
      </div>
      <div style="background:{_STEAM_BG2};border-radius:4px;height:6px;overflow:hidden;">
        <div style="background:{_PRIMARY_COLOR};width:{pct}%;height:100%;
                    border-radius:4px;transition:width .3s;"></div>
      </div>
    </div>
    <!-- 生成ボタン -->
    <button id="spm-sticky-bar-btn" {disabled} onclick="{onclick}"
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
    # show_title=False 時は高さ 0（ヘッダー帯なし）。header_h 未指定時はフォント実測値を使用
    header_h = (header_h if header_h is not None else _actual_header_h) if show_title else 0
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
    show_price: bool = True,
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
    if show_price:
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
        badge_bg = Image.new("RGBA", (badge_w, badge_h), (0, 0, 0, 185))
        section  = canvas.crop((bx1, by1, bx2, by2)).convert("RGBA")
        canvas.paste(Image.alpha_composite(section, badge_bg).convert("RGB"), (bx1, by1))
        if price_text.startswith("-") and "  " in price_text:
            disc_part, rest_part = price_text.split("  ", 1)
            prefix_w = int(draw.textlength(disc_part + "  ", font=price_font))
            draw.text(
                (bx1 + PRICE_BADGE_PAD - price_bb[0], by1 + PRICE_BADGE_PAD - price_bb[1]),
                disc_part, font=price_font, fill=SALE_GREEN,
            )
            draw.text(
                (bx1 + PRICE_BADGE_PAD - price_bb[0] + prefix_w, by1 + PRICE_BADGE_PAD - price_bb[1]),
                rest_part, font=price_font, fill=theme["accent"],
            )
        else:
            draw.text(
                (bx1 + PRICE_BADGE_PAD - price_bb[0], by1 + PRICE_BADGE_PAD - price_bb[1]),
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
    show_price: bool = True,
) -> Image.Image:
    """
    1920 × 1080 の Steam 布教まとめポスターを生成して PIL Image として返す。

    レイアウト:
      ヘッダー（show_title=True 時のみ）: _actual_header_h px（TITLE_V_PAD×2 + フォント実高 + ACCENT_LINE_H）
      グリッド: COLS=2 列 × rows 行（num_games から自動算出）
      フッター: FOOTER_H px（アクセントライン + ウォーターマーク）
    """
    h_font  = get_font(HEADER_FONT_PT)
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
            # アクセントライン上端までの領域に上下中央揃え
            content_h = layout["header_h"] - ACCENT_LINE_H
            text_y    = (content_h - (tb[3] - tb[1])) // 2 - tb[1]
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
        draw_card(canvas, draw, i, game, theme, bg_style, blur_r, layout, show_price)

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
    wm_text = f"Generated by {APP_NAME}  |  {APP_URL}"
    wm_bb   = draw.textbbox((0, 0), wm_text, font=wm_font)
    wm_tw   = wm_bb[2] - wm_bb[0]   # 視覚的なテキスト幅
    wm_th   = wm_bb[3] - wm_bb[1]   # 視覚的なテキスト高さ
    # フッターコンテンツ領域（アクセントライン下）内で上下均等に配置
    content_y = footer_y + ACCENT_LINE_H
    content_h = FOOTER_H - ACCENT_LINE_H
    wm_y = content_y + (content_h - wm_th) // 2
    draw.text(
        (CANVAS_W - wm_tw - 20 - wm_bb[0], wm_y - wm_bb[1]),
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
    if "num_games_sel" not in st.session_state:
        st.session_state["num_games_sel"] = 8
    if "lang" not in st.session_state:
        st.session_state["lang"] = "ja"
    if "show_price" not in st.session_state:
        st.session_state["show_price"] = True


# ═══════════════════════════════════════════════════════════
#  全スロットクリア確認ダイアログ
# ═══════════════════════════════════════════════════════════

def _clear_all_body() -> None:
    """全スロットクリア確認ダイアログの本体（言語に依存しない共通ロジック）"""
    st.warning(t("clear_all_warning"), icon=":material/warning:")
    col_yes, col_no = st.columns(2)
    with col_yes:
        if st.button(t("clear_all_confirm"), key="dlg_clear_all_yes",
                     icon=":material/delete_forever:", type="primary",
                     use_container_width=True):
            st.session_state.games = [None] * MAX_GAMES
            st.session_state.search_results = [[] for _ in range(MAX_GAMES)]
            for idx in range(MAX_GAMES):
                for k in [f"dlg_review_{idx}", f"dlg_q_{idx}", f"dlg_search_back_{idx}"]:
                    st.session_state.pop(k, None)
            st.session_state.pop("_confirm_clear_all", None)
            st.rerun()
    with col_no:
        if st.button(t("cancel_btn"), key="dlg_clear_all_no",
                     icon=":material/close:", use_container_width=True):
            st.session_state.pop("_confirm_clear_all", None)
            st.rerun()


@st.dialog("全スロットをクリア")
def _clear_all_dialog_ja() -> None:
    _clear_all_body()


@st.dialog("Clear All Slots")
def _clear_all_dialog_en() -> None:
    _clear_all_body()


def clear_all_dialog() -> None:
    """言語に応じたダイアログを呼び出す"""
    if st.session_state.get("lang", "ja") == "en":
        _clear_all_dialog_en()
    else:
        _clear_all_dialog_ja()


# ═══════════════════════════════════════════════════════════
#  編集ダイアログ（ポップアップ）
# ═══════════════════════════════════════════════════════════

@st.dialog("ゲームを編集", width="large")
def _edit_dialog_ja(i: int) -> None:
    _edit_dialog_body(i)


@st.dialog("Edit Game", width="large")
def _edit_dialog_en(i: int) -> None:
    _edit_dialog_body(i)


def edit_dialog(i: int) -> None:
    """言語設定に応じた編集ダイアログを呼び出す"""
    if st.session_state.get("lang", "ja") == "en":
        _edit_dialog_en(i)
    else:
        _edit_dialog_ja(i)


def _edit_dialog_body(i: int) -> None:
    """
    スロット i のゲーム検索・選択・テキスト入力をポップアップで行う。

    フェーズ管理:
    - 検索フェーズ: ゲーム未選択 OR ユーザーが「検索に戻る」を押した
    - 編集フェーズ: ゲーム選択済み
    フェーズ切替フラグ: session_state[f"dlg_search_back_{i}"]

    入力に対応: テキスト検索 / AppID 直接入力 / Steam ストア URL
    """
    game            = st.session_state.games[i]
    in_search_phase = game is None or f"dlg_search_back_{i}" in st.session_state

    st.caption(t("slot_caption", n=i + 1))

    # ════════════════════════════════════════════════════════
    # 検索フェーズ
    # ════════════════════════════════════════════════════════
    if in_search_phase:
        if game is not None:
            st.caption(t("reselect_caption", title=game["title"]))
        st.divider()

        with st.form(key=f"dlg_form_{i}", border=False):
            col_q, col_btn = st.columns([5, 1])
            with col_q:
                st.text_input(
                    t("search_btn"),
                    key=f"dlg_q_{i}",
                    placeholder=t("search_ph"),
                    label_visibility="collapsed",
                    help=t("search_help"),
                )
            with col_btn:
                search_clicked = st.form_submit_button(
                    t("search_btn"), icon=":material/search:", use_container_width=True,
                )

        if search_clicked:
            q = st.session_state.get(f"dlg_q_{i}", "").strip()
            if not q:
                st.warning(t("warn_empty_query"))
            else:
                # Steam ストア URL から AppID を自動抽出
                url_match = re.search(r"steampowered\.com/app/(\d+)", q)
                if url_match:
                    app_id = int(url_match.group(1))
                    with st.spinner(t("spin_url")):
                        details = get_game_details(app_id)
                    if details.get("age_restricted"):
                        st.warning(t("warn_age"), icon=":material/block:")
                    elif not details.get("title"):
                        st.warning(t("warn_id_notfound", id=app_id), icon=":material/error:")
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
                elif q.isdigit():
                    # AppID 直接入力
                    app_id = int(q)
                    with st.spinner(t("spin_appid", id=app_id)):
                        details = get_game_details(app_id)
                    if details.get("age_restricted"):
                        st.warning(t("warn_age"), icon=":material/block:")
                    elif not details.get("title"):
                        st.warning(t("warn_id_notfound", id=app_id), icon=":material/error:")
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
                    # テキスト検索
                    with st.spinner(t("spin_search", q=q)):
                        results = search_steam(q)
                    st.session_state.search_results[i] = results
                    st.session_state.pop(f"dlg_sel_{i}", None)
                    if not results:
                        st.warning(t("warn_notfound"))

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
                    "candidates",
                    list(options_map.keys()),
                    key=f"dlg_sel_{i}",
                    label_visibility="collapsed",
                )
                confirm_clicked = st.button(
                    t("confirm_game_btn"), key=f"dlg_confirm_{i}",
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
                with st.spinner(t("spin_details", name=chosen["name"])):
                    details = get_game_details(chosen["app_id"])
                if details.get("age_restricted"):
                    st.warning(t("warn_age"), icon=":material/block:")
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
        if game is not None:
            col_back, col_close = st.columns([1, 1])
            with col_back:
                if st.button(t("back_to_edit_btn"), key=f"dlg_editback_{i}",
                             icon=":material/arrow_back:", use_container_width=True):
                    st.session_state.pop(f"dlg_search_back_{i}", None)
                    st.rerun()
            with col_close:
                if st.button(t("cancel_btn"), key=f"dlg_close_{i}",
                             icon=":material/close:", use_container_width=True):
                    del st.session_state["editing_slot"]
                    st.rerun()
        else:
            if st.button(t("close_btn"), key=f"dlg_close_{i}", icon=":material/close:"):
                del st.session_state["editing_slot"]
                st.rerun()

    # ════════════════════════════════════════════════════════
    # 編集フェーズ
    # ════════════════════════════════════════════════════════
    else:
        if st.button(t("back_to_search_btn"), key=f"dlg_back_{i}", icon=":material/search:"):
            st.session_state[f"dlg_search_back_{i}"] = True
            st.session_state.search_results[i] = []
            st.rerun()

        st.divider()

        col_img, col_form = st.columns([1, 2])

        with col_img:
            if not game.get("age_restricted") and game.get("image_url"):
                st.image(game["image_url"], use_container_width=True)
            else:
                _show_age_restricted_thumb(padding="20px 0")

        with col_form:
            st.markdown(f"### {game['title']}")
            price_raw = t("age_price_label") if game.get("age_restricted") else game["price"]
            st.markdown(_price_badge_html(price_raw), unsafe_allow_html=True)

            review_now = st.text_area(
                t("review_label"),
                height=160,
                key=f"dlg_review_{i}",
                help=t("review_help"),
            )
            review_len = len(review_now or "")

            # ── 文字数上限（利用可能エリアに対して REVIEW_FONT_PT を基準に算出） ──
            _show_title  = st.session_state.get("show_title", True)
            _num_g       = st.session_state.get("num_games_sel", 8)
            _L           = compute_layout(_show_title, _num_g)
            max_chars    = max(60, int(_L["review_max_h"] * _L["text_area_w"] // (REVIEW_FONT_PT ** 2)))

            over_limit = review_len > max_chars
            counter_id = f"dlg-rc-{i}"
            color_init = "#e74c3c" if over_limit else "#aaa"
            counter_text = t("char_counter_tmpl", n=review_len, max=max_chars)
            st.markdown(
                f"<p id='{counter_id}' style='text-align:right;font-size:0.8rem;"
                f"color:{color_init};margin-top:-12px'>{counter_text}</p>",
                unsafe_allow_html=True,
            )
            if over_limit:
                st.error(t("over_limit_err", max=max_chars))

            # ── リアルタイムカウンター（JS）─ダイアログ内の唯一の textarea を対象 ──
            lang_suffix = t("char_counter_suffix")
            components.html(
                f"""<script>
(function(){{
  var CID = '{counter_id}';
  var MAX = {max_chars};
  var SUFFIX = ' / {max_chars} {lang_suffix}';
  function attach() {{
    var doc = window.parent.document;
    var ta = doc.querySelector('[data-testid="stTextArea"] textarea');
    if (!ta) return false;
    if (ta._rt) ta.removeEventListener('input', ta._rt);
    ta._rt = function() {{
      var n = this.value.length;
      var c = doc.getElementById(CID);
      if (!c) return;
      c.textContent = n + SUFFIX;
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
            if st.button(t("save_btn"), key=f"dlg_save_{i}",
                         icon=":material/save:",
                         type="primary", use_container_width=True,
                         disabled=over_limit):
                st.session_state.games[i]["review"] = st.session_state.get(f"dlg_review_{i}", "")
                st.session_state.pop(f"dlg_search_back_{i}", None)
                del st.session_state["editing_slot"]
                st.rerun()
        with col_clear:
            if st.button(t("dlg_clear_btn"), key=f"dlg_clear_{i}",
                         icon=":material/delete:",
                         use_container_width=True):
                st.session_state.games[i] = None
                st.session_state.search_results[i] = []
                for k in [f"dlg_review_{i}", f"dlg_q_{i}", f"dlg_search_back_{i}"]:
                    st.session_state.pop(k, None)
                del st.session_state["editing_slot"]
                st.rerun()
        with col_cancel:
            if st.button(t("cancel_btn"), key=f"dlg_cancel_{i}",
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
                    t("age_price_label")
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
                f"color:#555;font-size:0.85rem;'>{t('empty_slot_card', n=i+1)}</div>",
                unsafe_allow_html=True,
            )

        if st.button(
            t("edit_btn"), key=f"btn_edit_{i}",
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
        page_icon="🎮",
        layout="wide",
    )

    init_session()
    ensure_font()
    st.markdown(_GLOBAL_CSS, unsafe_allow_html=True)

    st.markdown(
        "<h1 style='text-align:center;'>SteamPosterMaker</h1>",
        unsafe_allow_html=True,
    )
    # ── 言語トグル（右上） ───────────────────────────────────
    col_spacer, col_lang = st.columns([8, 2])
    with col_lang:
        if st.button(
            t("lang_toggle"), key="lang_toggle_btn",
            icon=":material/language:", use_container_width=True,
        ):
            st.session_state["lang"] = "en" if st.session_state.get("lang", "ja") == "ja" else "ja"
            st.rerun()

    # ── レイアウト・進捗を先に計算 ──────────────────────────────
    show_title        = st.session_state.get("show_title", True)
    num_games_sel     = st.session_state.get("num_games_sel", 8)
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
        with st.expander(t("dev_expander"), icon=":material/science:"):
            if st.button(
                t("dev_fill_btn"),
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
            t("heading_toggle"),
            value=True,
            key="show_title",
            help=t("heading_toggle_help"),
        )
    with col_ttl:
        if show_title:
            poster_title = st.text_input(
                t("heading_toggle"),
                value=t("heading_default"),
                max_chars=25,
                placeholder=t("heading_placeholder"),
                key="poster_title",
                label_visibility="collapsed",
                help=t("heading_help"),
            )
        else:
            poster_title = st.session_state.get("poster_title", "")
            st.caption(t("heading_none_cap"))
    with col_pop:
        with st.popover(t("num_games_popover"), icon=":material/grid_view:", use_container_width=True):
            st.radio(
                t("num_games_label"),
                [8, 10],
                horizontal=True,
                key="num_games_sel",
                help=t("num_games_help"),
            )
            st.caption(f"Card {layout['card_w']} × {layout['card_h']} px")

    st.divider()

    # ── ゲームスロット（2列グリッド） ───────────────────────
    # filled / already_generated はページ冒頭で先行計算済み
    col_hdr, col_cnt, col_clear, col_sort = st.columns([3, 1, 1, 1], vertical_alignment="center")
    with col_hdr:
        st.subheader(t("slots_header"))
    with col_cnt:
        st.markdown(
            f"<p style='margin:0;text-align:right;white-space:nowrap;'>"
            f"<span style='font-size:0.8rem;color:#aaa;margin-right:6px;'>{t('slots_count_prefix')}</span>"
            f"<span style='font-size:1.15rem;font-weight:bold;'>{filled} / {num_games}</span>"
            f"</p>",
            unsafe_allow_html=True,
        )
    with col_clear:
        if st.button(
            t("clear_all_btn"), key="btn_clear_all",
            icon=":material/delete_sweep:", use_container_width=True,
            disabled=filled == 0,
        ):
            st.session_state["_confirm_clear_all"] = True
            st.rerun()
    with col_sort:
        sort_label = t("sort_done_btn") if st.session_state["reorder_mode"] else t("sort_btn")
        sort_icon  = ":material/done_all:" if st.session_state["reorder_mode"] else ":material/swap_vert:"
        sort_type  = "primary"   if st.session_state["reorder_mode"] else "secondary"
        if st.button(sort_label, icon=sort_icon, use_container_width=True, type=sort_type):
            st.session_state["reorder_mode"] = not st.session_state["reorder_mode"]
            st.rerun()

    if st.session_state["reorder_mode"]:
        # ── 並び替えモード ────────────────────────────────────
        st.info(
            t("sort_drag_info"),
            icon=":material/swap_vert:",
        )

        sort_labels = []
        for idx in range(num_games):
            g = st.session_state.games[idx]
            sort_labels.append(g["title"] if g else t("empty_slot_sort", n=idx + 1))

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
    # sentinel が画面内に入ったら、スティッキーバーを非表示にする
    # components.html() はリラン毎にiframeが再実行されるため、st.markdown<script>より確実
    st.markdown('<div id="poster-gen-sentinel"></div>', unsafe_allow_html=True)
    components.html(
        """<script>
(function() {
  var BAR_ID = 'spm-sticky-bar';
  var SEN_ID = 'poster-gen-sentinel';
  var doc = window.parent.document;
  var win = window.parent;

  function updateBar() {
    var bar = doc.getElementById(BAR_ID);
    var sen = doc.getElementById(SEN_ID);
    if (!bar || !sen) return;
    /* sentinel の top が viewport の高さ以下なら「到達済み or 通過済み」→ バーを隠す */
    var reached = sen.getBoundingClientRect().top <= win.innerHeight;
    bar.style.opacity       = reached ? '0' : '1';
    bar.style.pointerEvents = reached ? 'none' : 'auto';
  }

  /* スクロール毎に判定（passive で軽量） */
  win.addEventListener('scroll', updateBar, { passive: true });

  /* 初回チェック: sentinel が DOM に現れるまでポーリング */
  var tid = setInterval(function() {
    if (doc.getElementById(SEN_ID)) {
      clearInterval(tid);
      updateBar();
    }
  }, 80);
})();
</script>""",
        height=0,
        scrolling=False,
    )
    if filled > 0 and filled < num_games:
        st.info(
            t("empty_slots_info", filled=filled, n=num_games - filled),
            icon=":material/info:",
        )
    col_design, col_gen = st.columns([1, 2])
    with col_design:
        with st.popover(t("design_popover"), icon=":material/settings:", use_container_width=True):
            theme_name = st.selectbox(
                t("theme_label"),
                list(THEMES.keys()),
                key="theme_sel",
            )
            theme_colors = THEMES[theme_name]
            _swatch_html = "".join(
                f"<span title='{label}' style='display:inline-block;width:22px;height:22px;"
                f"border-radius:5px;background:rgb{color};margin-right:5px;"
                f"border:1px solid #555;vertical-align:middle'></span>"
                for label, color in [
                    ("bg", theme_colors["bg"]),
                    ("accent", theme_colors["accent"]),
                    ("card", theme_colors["card_bg"]),
                ]
            )
            st.markdown(_swatch_html, unsafe_allow_html=True)
            bg_style = st.radio(
                t("bg_style_label"),
                ["blur", "solid"],
                format_func=lambda x: t("bg_style_blur") if x == "blur" else t("bg_style_solid"),
                horizontal=True,
                key="bg_style_sel",
            )
            blur_r = 0
            if bg_style == "blur":
                blur_r = st.slider(
                    t("blur_label"), min_value=1, max_value=40, value=15,
                    key="blur_r_val",
                    help=t("blur_help"),
                )
            st.toggle(t("show_price_label"), value=True, key="show_price")
    with col_gen:
        generate_btn = st.button(
            t("regenerate_btn") if already_generated else t("generate_btn"),
            icon=":material/refresh:" if already_generated else ":material/palette:",
            type="primary",
            use_container_width=True,
            disabled=(filled == 0),
        )

    if generate_btn or _sticky_triggered:
        games_slice = st.session_state.games[:num_games]
        show_price  = st.session_state.get("show_price", True)

        for _key in ("last_poster_bytes", "last_poster_meta"):
            st.session_state.pop(_key, None)

        with st.status(t("status_title"), expanded=True) as gen_status:
            try:
                fetchable = [
                    g for g in games_slice
                    if g is not None and not g.get("age_restricted")
                ]
                if fetchable:
                    st.write(t("status_fetch", n=len(fetchable), total=num_games))
                    for g in fetchable:
                        _fetch_raw_image(g["image_url"])

                st.write(t("status_compose"))
                poster = generate_poster(
                    games_slice,
                    poster_title,
                    theme_name,
                    bg_style,
                    blur_r,
                    show_title,
                    num_games,
                    show_price,
                )

                st.write(t("status_encode"))
                buf = io.BytesIO()
                poster.save(buf, format="PNG", compress_level=1)
                poster.close()
                st.session_state["last_poster_bytes"] = buf.getvalue()
                date_str   = datetime.date.today().strftime("%Y%m%d")
                pick_label = f"{num_games}pick"
                title_part = _safe_filename(poster_title) if show_title and poster_title.strip() else ""
                parts      = ["steam", pick_label] + ([title_part] if title_part else []) + [date_str]
                st.session_state["last_poster_meta"] = {
                    "filename": "_".join(parts) + ".png",
                }
                st.session_state["_poster_complete"] = True
            except Exception as e:
                gen_status.update(label=t("status_error"), state="error")
                st.error(f"{e}")

    if "last_poster_bytes" in st.session_state:
        poster_bytes = st.session_state["last_poster_bytes"]
        meta         = st.session_state["last_poster_meta"]
        st.image(poster_bytes, caption=t("preview_caption"), use_container_width=True)
        st.download_button(
            label=t("download_btn"),
            icon=":material/download:",
            data=poster_bytes,
            file_name=meta["filename"],
            mime="image/png",
            use_container_width=True,
        )
        # ── X シェアボタン ──────────────────────────────────
        _tweet_params = urllib.parse.urlencode(
            {"text": t("share_tweet_text"), "url": APP_URL},
            quote_via=urllib.parse.quote,
        )
        _tweet_url = (
            "https://x.com/intent/tweet?"
            + _tweet_params
            + "&hashtags=" + urllib.parse.quote(t("share_hashtags"), safe=",")
        )
        st.divider()
        st.markdown(
            f"<p style='text-align:center;font-weight:bold;font-size:0.95rem;"
            f"margin:0 0 6px;'>{t('share_header')}</p>",
            unsafe_allow_html=True,
        )
        st.info(t("share_info"), icon=":material/attach_file:")
        st.link_button(
            t("share_btn"),
            _tweet_url,
            icon=":material/share:",
            use_container_width=True,
        )
        if st.session_state.pop("_poster_complete", False):
            st.toast(t("toast_done"), icon=":material/check_circle:")

    # ── フッター ────────────────────────────────────────────
    # 順序: ① 非公式注意 → ② フィードバック → ③ 作者への導線 → ④ 利用規約
    st.divider()

    # ① 非公式ファンメイドツール注意（アンバー背景）
    st.markdown(
        "<div style='text-align:center;font-size:0.8rem;color:#c8c0a0;line-height:1.8;"
        "background:rgba(200,160,64,0.12);border:1px solid rgba(200,160,64,0.35);"
        "border-radius:8px;padding:12px 20px;margin:0;'>"
        f"<strong>{t('disclaimer_unofficial')}</strong><br>"
        f"{t('disclaimer_no_relation')}<br>"
        f"{t('disclaimer_trademark')}"
        "</div>",
        unsafe_allow_html=True,
    )

    # ② フィードバックフォーム ＋ ③ 作者への導線（横並び）
    st.divider()
    col_fb, col_sep, col_author = st.columns([10, 1, 10], vertical_alignment="center")

    with col_sep:
        st.markdown(
            "<div class='footer-sep' style='border-left:1px solid #444;height:220px;"
            "margin:0 auto;width:1px;'></div>",
            unsafe_allow_html=True,
        )

    with col_fb:
        st.markdown(
            f"<p style='text-align:center;font-size:0.85rem;font-weight:bold;margin:0 0 4px;'>"
            f"{t('feedback_header')}</p>"
            f"<p style='text-align:center;font-size:0.8rem;color:#aaa;margin:0 0 1.6em;'>"
            f"{t('feedback_body')}</p>",
            unsafe_allow_html=True,
        )
        _, btn_col, _ = st.columns([1, 4, 1])
        with btn_col:
            st.link_button(
                t("feedback_btn"),
                "https://forms.gle/GpBA3PHgZHsze82r8",
                icon=":material/rate_review:",
                use_container_width=True,
            )

    with col_author:
        # ① OFUSE 応援ボタン
        st.markdown(
            f"<p style='text-align:center;font-size:0.85rem;font-weight:bold;margin:0 0 1.6em;'>"
            f"{t('ofuse_header')}</p>",
            unsafe_allow_html=True,
        )
        st.markdown(_OFUSE_BUTTON_HTML, unsafe_allow_html=True)
        # ② X フォローボタン（間隔を広めに取る）
        st.markdown(
            f"<p style='text-align:center;font-size:0.85rem;font-weight:bold;"
            f"margin:1.8em 0 1.6em;'>"
            f"{t('author_section')}</p>",
            unsafe_allow_html=True,
        )
        st.markdown(_X_BUTTON_ICON_HTML, unsafe_allow_html=True)

    # ④ 利用規約・免責事項
    st.divider()
    with st.expander(t("tos_expander")):
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

**利用している外部サービスについて**
* 本アプリは <a href="https://streamlit.io" target="_blank" style="color:#a8c8e8;text-decoration:underline">Streamlit</a> を使用して構築されており、<a href="https://streamlit.io/cloud" target="_blank" style="color:#a8c8e8;text-decoration:underline">Streamlit Community Cloud</a> 上でホスティングされています。Streamlit の<a href="https://streamlit.io/terms-of-use" target="_blank" style="color:#a8c8e8;text-decoration:underline">利用規約</a>も併せて適用されます。
* フッターの「OFUSE」ボタンは、開発者個人の支援ページ（<a href="https://ofuse.me" target="_blank" style="color:#a8c8e8;text-decoration:underline">ofuse.me</a> / 株式会社 Sozi）へのリンクです。OFUSE はこのアプリとは無関係であり、OFUSE の<a href="https://ofuse.me/terms" target="_blank" style="color:#a8c8e8;text-decoration:underline">利用規約</a>はOFUSE サービス内でのみ適用されます。支援はあくまで任意です。
            """,
            unsafe_allow_html=True,
        )

    # ── コピーライトフッター ────────────────────────────────
    st.markdown(
        "<div class='spm-copyright'>"
        "© 2026 Yuuki Hiiro &nbsp;—&nbsp; "
        "This app is an unofficial fan-made tool, not affiliated with Valve."
        "</div>",
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

    # 全クリア確認ダイアログ
    if st.session_state.get("_confirm_clear_all"):
        clear_all_dialog()


if __name__ == "__main__":
    main()
