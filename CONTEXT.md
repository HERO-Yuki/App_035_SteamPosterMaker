# PROJECT CONTEXT & MEMORY

このドキュメントは、AIエージェントがプロジェクトの文脈を理解し、適切な支援を提供するための情報をまとめたものです。

---

## 1. プロジェクト概要 (Overview)

* **アプリ名**: App_035 Steam8 Poster
* **目的**: Steamゲーム布教用のまとめ画像（8本紹介）を X (Twitter) 向けに自動生成する Webアプリ
* **ターゲットユーザー**: Steamゲームをオススメしたいゲーマー
* **主要機能**:
    * Steam ストア API でゲームを検索・詳細取得（キャッシュ付き）
    * 最大8本のゲームスロット管理（session_state で状態保持）
    * 1920×1080 PNG ポスター生成（Pillow）
    * テーマカラー5種・背景スタイル2種（ぼかしスライダー/単色）
    * 日本語対応ピクセル幅ベースのテキスト折り返し + フォント自動縮小
    * 年齢制限・API障害時のフォールバック処理

---

## 2. 技術スタック (Tech Stack)

* **Language**: Python 3.10+
* **Environment**: Streamlit Community Cloud（ローカルでも動作）
* **Key Libraries**:
    - `streamlit` — Web UI・状態管理（`st.session_state`）
    - `Pillow (PIL)` — 画像生成（キャンバス・テキスト・GaussianBlur）
    - `requests` — Steam API / 画像URL フェッチ
    - `functools.lru_cache` — フォントオブジェクトのインメモリキャッシュ
* **外部リソース**:
    - Steam Web API（認証不要・公開エンドポイント）
    - Noto Sans CJK JP Bold（起動時に GitHub から自動ダウンロード）

---

## 3. ディレクトリ構造とファイルの役割 (File Structure)

```text
App_035_Steam8Poster/
├── app.py                   # アプリ全体（単一ファイル構成）
│   ├── 定数・レイアウト計算 (CANVAS_W, CARD_W, CARD_H, TITLE_Y, REVIEW_Y...)
│   ├── テーマカラー定義 (THEMES dict — 5テーマ × 6色)
│   ├── フォント管理 (ensure_font, get_font with lru_cache)
│   ├── Steam API (@st.cache_data: search_steam, get_game_details)
│   ├── 画像ユーティリティ (_fetch_raw_image, load_pil_image)
│   ├── テキスト描画 (wrap_text_pixels, fit_text_in_box)
│   ├── カード描画 (draw_card)
│   ├── ポスター生成 (generate_poster)
│   └── Streamlit UI (init_session, render_slot, main)
├── requirements.txt         # streamlit / Pillow / requests
├── .streamlit/config.toml   # Steam カラーテーマ
└── NotoSansCJKjp-Bold.otf   # 自動生成（gitignore済み）
```

---

## 4. 重要な設計判断 (Key Design Decisions)

### カードグリッド
- **2列 × 4行** で 8枚のカードを配置（横長Twitter画像に最適）
- カードサイズ: **930 × 215 px**（マージン 20px を差し引いて均等分割）
- サムネイル: **215×215 px** の正方形クロップ（カード左端）
- アクセントカラーの縦区切り線（3px）がサムネとテキストを分離

### テキスト折り返し（日本語対応）
- `textwrap` は全角文字の幅計算が不正確なため**不使用**
- `ImageDraw.textlength()` で 1文字ずつ計測するカスタム関数 `wrap_text_pixels()` を実装

### フォント自動縮小
- `fit_text_in_box(draw, text, initial_size, max_w, max_h, min_size)` が 1pt ずつ縮小
- タイトル: 初期 36pt → 最小 18pt
- プレイ人数: 初期 19pt → 最小 13pt
- レビュー文: 初期 19pt → 最小 11pt

### フォントキャッシュ
- `get_font(size)` に `@lru_cache(maxsize=32)` を適用
- ポスター生成中の同一サイズへの重複呼び出しでファイル I/O を回避

### Steam API・価格パース
- `price_overview.final_formatted` を優先使用（Steam が整形済み文字列を返す）
- セール時: `-50%  ¥500` 形式
- 無料ゲーム: `is_free: true` を確認 → 「無料」表示
- 年齢制限/取得失敗: CDN ヘッダー画像URL + 価格「不明」でフォールバック

### session_state とウィジェット状態
- **ゲームデータ**: `st.session_state.games[i]` (dict or None) で管理
- **ウィジェット値との競合防止**: ゲーム確定時に `st.session_state[f"review_{i}"]` と `st.session_state[f"players_{i}"]` を明示的にリセットしてから `st.rerun()`
- キーを使うウィジェット（`text_area`, `multiselect`）の `value=` / `default=` は session_state キーが存在するときは無視されるが、Python コードが明示的にキーを書き換えた場合は値が一致していなければ例外になる

### 画像キャッシュ
- `@st.cache_data(ttl=3600)` を API 関数と `_fetch_raw_image` に適用
- 同一セッション内での重複ネットワークリクエストを防止

---

## 5. 現在の開発状況 (Current Status)

### 現在のフェーズ
初期実装完了・リファクタリング済み

### 実装済み (Done)
- [x] Steam API 検索・詳細取得（エラーハンドリング・キャッシュ）
- [x] 8スロット UI（検索→選択→確定→レビュー入力→プレイ人数選択）
- [x] セッション状態管理（session_state でページ再実行後もデータ保持）
- [x] Pillow カード描画（サムネ・番号バッジ・タイトル・価格・プレイ人数・レビュー）
- [x] 日本語テキスト折り返し（ピクセル幅計測）
- [x] フォントサイズ自動縮小（fit_text_in_box）
- [x] フォントオブジェクトの lru_cache キャッシュ
- [x] ゲーム切り替え時の session_state ウィジェット値リセット（バグ修正済み）
- [x] 検索再実行時の selectbox キークリア
- [x] 5テーマカラー
- [x] 背景スタイル（ぼかしスライダー / 単色）
- [x] フォント自動ダウンロード（Noto Sans CJK JP Bold）
- [x] PNG ダウンロード（1920×1080）
- [x] ウォーターマーク

### 未実装・課題 (Todo)
- [ ] フォント取得の代替 URL（GitHub が落ちている場合）
- [ ] 生成プレビューのサイドバイサイド比較

---

## 6. 開発ルール・制約 (Rules)

### コーディング規約
- `app.py` 1ファイルに全機能を収める（Streamlit Community Cloud 向け）
- 関数名や変数は処理内容が推測できる具体的な英語名
- 複雑な処理には日本語コメントを入れること
- 新しいライブラリを追加する際はユーザーに確認

### AIへの指示
- `draw_card` と `generate_poster` の座標計算は定数（MARGIN, CARD_W, CARD_H, TITLE_Y, REVIEW_Y 等）で行うこと
- ゲーム確定時は必ず `st.session_state[f"review_{i}"] = ""` と `st.session_state[f"players_{i}"] = []` でウィジェット値をリセットしてから `st.rerun()` を呼ぶこと
- `st.rerun()` は `st.session_state` の更新直後にのみ呼ぶこと
- `ensure_font()` は `main()` の冒頭で一度だけ呼ぶこと
- `get_font()` は `@lru_cache` でキャッシュ済みなので同一サイズを何度呼んでも安全

---

## 7. 更新履歴 (Changelog)

### 2026-04-09
- プロジェクト作成・初期実装完了
- コードレビュー・リファクタリング実施
  - `get_font()` に `@lru_cache(maxsize=32)` を追加（フォントI/O削減）
  - ゲーム切り替え時のウィジェット値競合バグを修正（session_state 明示リセット）
  - 検索再実行時の selectbox キー（`sel_{i}`）をクリアするよう修正
  - 未使用の `clamp_brightness()` 関数を削除
  - 全体見出し入力に `key="poster_title"` を追加（リロード後も保持）
