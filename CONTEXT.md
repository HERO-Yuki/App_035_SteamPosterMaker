# PROJECT CONTEXT & MEMORY

このドキュメントは、AI エージェントがプロジェクトの文脈を理解し、適切な支援を提供するための情報をまとめたものです。

---

## 1. プロジェクト概要 (Overview)

* **アプリ名**: App_035 SteamPosterMaker
* **目的**: Steam ゲーム布教用まとめ画像（最大10本紹介）を X (Twitter) 向けに 1920×1080 PNG で自動生成する Web アプリ
* **ターゲットユーザー**: Steam ゲームをオススメしたいゲーマー
* **主要機能**:
    * Steam ストア API でゲームを検索・詳細取得（キャッシュ付き）
    * **AppID 直接入力**にも対応（検索フォームで数字のみ入力すると即時取得）
    * 最大10スロット管理（session_state で状態保持）
    * ポップアップダイアログ（`st.dialog`）でゲームを編集
    * ドラッグ＆ドロップによるスロット並べ替え（`streamlit-sortables`）
    * 1920×1080 PNG ポスター生成（Pillow）・DL ファイル名にタイトル文字を含む
    * テーマカラー5種・**カラースウォッチプレビュー**・背景スタイル2種（ぼかしスライダー/単色）
    * 日本語対応ピクセル幅ベースのテキスト折り返し + フォント自動縮小
    * 年齢制限コンテンツを錠前アイコン（Pillow 描画）で可視化
    * フォント取得: GitHub → jsDelivr CDN フォールバック

---

## 2. 技術スタック (Tech Stack)

* **Language**: Python 3.10+
* **Environment**: Streamlit Community Cloud（ローカルでも動作）
* **Key Libraries**:
    - `streamlit >= 1.37.0` — Web UI・状態管理・`st.dialog`・`st.status`
    - `streamlit-sortables` — ドラッグ＆ドロップ並べ替え
    - `Pillow (PIL)` — 画像生成（キャンバス・テキスト・GaussianBlur・alpha_composite）
    - `requests` — Steam API / 画像 URL フェッチ
    - `functools.lru_cache` — フォントオブジェクト・年齢制限画像のインメモリキャッシュ
* **外部リソース**:
    - Steam Web API（認証不要・公開エンドポイント）
    - Noto Sans CJK JP Bold（起動時に GitHub から自動ダウンロード）

---

## 3. ディレクトリ構造とファイルの役割 (File Structure)

```text
App_035_SteamPosterMaker/
├── app.py                   # アプリ全体（単一ファイル構成）
│   ├── 固定定数・レイアウト計算 (compute_layout)
│   ├── テーマカラー定義 (THEMES dict — 5テーマ × 6色)
│   ├── フォント管理 (ensure_font, get_font with lru_cache)
│   ├── Steam API (@st.cache_data: search_steam, get_game_details)
│   ├── 画像ユーティリティ (_fetch_raw_image, load_pil_image, make_age_restricted_image)
│   ├── UI ヘルパー (_show_age_restricted_thumb, _price_badge_html)
│   ├── テキスト描画 (wrap_text_pixels, fit_text_in_box)
│   ├── カード描画 (draw_card)
│   ├── ポスター生成 (generate_poster)
│   └── Streamlit UI (init_session, edit_dialog, render_slot_card, main)
├── requirements.txt
├── .streamlit/config.toml
├── docs/
│   ├── setup-guide.md
│   └── troubleshooting.md
└── NotoSansCJKjp-Bold.otf   # 自動生成（gitignore 済み）
```

---

## 4. 重要な設計判断 (Key Design Decisions)

### 動的レイアウト `compute_layout(show_title: bool)`
- `show_title=True` : ヘッダー 120px + 2列×4行 = **8スロット**（カード 954×235 px）
- `show_title=False`: ヘッダーなし + 2列×5行 = **10スロット**（カード 954×211 px）
- どちらも出力は **1920×1080 px 固定**。カード間マージン: **4 px**（定数 `MARGIN`）
- `title_max_h` を縮小して `review_max_h` を最大化（レビュー文の表示エリアを広く）

### カードレイアウト
- サムネ幅: **380 px**
- サムネ描画モード: **contain（letterbox）** — `load_pil_image_contain()` でアスペクト比を保ったまま全体を表示し、余白は黒ベタで埋める（旧: cover/中央クロップ）
- アクセントカラーの縦区切り線（3px）がサムネとテキストを分離
- 価格: サムネ右下に **半透明バッジ**（`Image.alpha_composite` で合成）として描画
    - フォント 24pt・端から `PRICE_BADGE_EDGE=10px` の余白
    - 定数: `PRICE_BADGE_PAD=8`, `PRICE_BADGE_EDGE=10`（モジュール定数）
- スロット番号バッジ（01, 02...）は廃止

### 年齢制限コンテンツ
- `get_game_details` が `age_restricted: bool` フラグを返す
    - `success: false` → `age_restricted=True`（年齢/リージョン制限）
    - ネットワークエラーなど → `age_restricted=False`
- ポスター: `make_age_restricted_image(w, h)` で錠前アイコン＋"18+"を Pillow 描画
    - `@lru_cache(maxsize=4)` でキャッシュ済み（同一サイズで再利用）
    - ぼかし背景も適用しない（CDN 画像取得をスキップ）
- UI: `_show_age_restricted_thumb()` ヘルパーで🔞プレースホルダー表示

### テキスト折り返し（日本語対応）
- `textwrap` は全角文字の幅計算が不正確なため**不使用**
- `ImageDraw.textlength()` で 1文字ずつ計測するカスタム関数 `wrap_text_pixels()` を実装

### フォント自動縮小 `fit_text_in_box`
- タイトル: 初期 `TITLE_FONT_PT=28` → 最小 `TITLE_MIN_PT=16`
- プレイ人数: 初期 `PLAYER_FONT_PT=19` → 最小 `PLAYER_MIN_PT=13`
- レビュー文: 初期 `REVIEW_FONT_PT=19` → 最小 `REVIEW_MIN_PT=11`

### スロット並べ替えモード
- ヘッダー行の **「🔀 並び替え」ボタン** で `reorder_mode` フラグをトグル
- `True` 時: 2×N グリッドを非表示にし `sort_items` の縦リストを全幅表示
- `False` 時: 通常グリッドを表示
- ボタンタイプ: 通常モード `secondary` / 並び替えモード `primary`（視認性向上）
- 旧実装（`st.expander` 内 `sort_items`）は expander が閉じる rerun で変化なしに見えるバグがあったため廃止

### 全体見出し（`poster_title`）
- `max_chars=25` — 64pt フォント × 1920px ヘッダーに収まる安全上限
    - 計算根拠: `(1920 - 80px余白) / 70px文字幅 ≈ 26.3` → 25文字

### セッション状態
- **ゲームデータ**: `st.session_state.games[i]`（dict or None）
- **検索結果**: `st.session_state.search_results[i]`
- ~~`search_queries`~~: UI リファクタ後に未参照となったため削除済み
- **並べ替えモード**: `st.session_state["reorder_mode"]`（bool）— `init_session()` で初期化
- **ダイアログ**:
    - `st.session_state["editing_slot"] = i` でポップアップを開く
    - ダイアログ内ウィジェット: `dlg_review_{i}`, `dlg_players_{i}`, `dlg_q_{i}` キーで管理
    - フェーズ切替フラグ: `dlg_search_back_{i}` — セットされていると検索フェーズに戻る。ダイアログを閉じる際（保存・クリア・キャンセル）に必ず削除する
- **ポスター永続化**: 生成した PNG バイト列を `last_poster_bytes` / `last_poster_meta` に保存し、設定変更後のリラン後も表示を維持

### API キャッシュ
- `@st.cache_data(ttl=3600)` を `search_steam`, `get_game_details`, `_fetch_raw_image` に適用
- `@st.cache_data` 内で `st.session_state` を書き換えない（キャッシュヒット時にサイドエフェクトが再実行されないため）

### ポスター生成フロー（`st.status` で進捗表示）
1. `🌐 Steam からゲーム画像を引っ張っています...` — 年齢制限ゲームを除く各ゲームの画像を `_fetch_raw_image` でプリフェッチ
2. `🖼️ 1920 × 1080 px の画像を合成中...` — `generate_poster` 呼び出し
3. `💾 PNG に書き出し中...` — `io.BytesIO` に保存して `last_poster_bytes` へ

---

## 5. 現在の開発状況 (Current Status)

### 実装済み (Done)
- [x] Steam API 検索・詳細取得（エラーハンドリング・キャッシュ）
- [x] 最大10スロット管理（session_state）
- [x] ポップアップダイアログ（`st.dialog`）でゲーム編集
- [x] 検索フォームを `st.form` 化 → Enter キーで送信可能
- [x] ドラッグ＆ドロップ並べ替え（streamlit-sortables）
- [x] 2×N グリッド UI（ポスターレイアウトに近しい mini カード）
- [x] 検索結果にサムネプレビュー
- [x] 全体見出しトグル（ON: 8スロット / OFF: 10スロット）
- [x] 年齢制限ゲームの錠前アイコン（ポスター＋UI 両対応）
- [x] 価格バッジをサムネ右下に配置（半透明オーバーレイ）
- [x] タイトルフォント小型化（初期28pt）
- [x] レビュー文エリア拡大（価格行削除でスペース確保）
- [x] レビュー文: リアルタイム文字数カウンター（140字超で赤表示・保存無効化）
- [x] st.spinner / st.status によるローディング表示
- [x] ポスターの設定変更後リラン後も表示維持
- [x] 全幅ボタン（生成・ダウンロード）。生成後は「再生成する」に文言変更
- [x] st.toast による生成完了通知（st.balloons 廃止）
- [x] サイドバーに開発者フォローリンク（X @Yuki_HERO44）
- [x] 生成前に空きスロット数を st.info で案内
- [x] スロットカード: フォント・色・行間・絵文字スペースの視認性改善
- [x] スロットカード間 CSS gap 2px（Streamlit デフォルト間隔を縮小）
- [x] レビュー文をカード全幅に表示（右カラム外に移動）
- [x] ポスター MARGIN 20 → 10 → 4 px（カードサイズ 954×235 px / 954×211 px に拡大）
- [x] フォント自動ダウンロード（Noto Sans CJK JP Bold）
- [x] PNG ダウンロード（1920×1080）
- [x] ウォーターマーク
- [x] 並び替えモードのトグルボタン（expander 廃止・rerun バグ解消）
- [x] 価格バッジ: フォント 24pt・端余白 10px（PRICE_BADGE_EDGE 定数）
- [x] 全体見出し文字数上限: 40 → 25文字（64pt フォント幅に基づく計算）
- [x] コードレビュー・リファクタリング（v2〜v7）
- [x] アプリ名を `Steam8 Poster` → `SteamPosterMaker` に変更
- [x] 可変定数を `app.py` 冒頭の定数セクションに集約
- [x] サムネイル描画: cover（クロップ）→ contain（letterbox + 黒ベタ）
- [x] ダイアログ: ゲーム選択後にヘッダー画像プレビュー（width=250）を表示
- [x] スロットカード: 価格を囲み枠バッジ（Steam 青ボーダー）で表示
- [x] スロットカード: プレイ人数を「プレイ人数: ○○」形式で表示
- [x] スロットカード: 横並び高さ揃え CSS（flex stretch + height:100% 伝播）
- [x] 免責事項: 5セクション構成に拡充・X ボタン化（ブランドカラー）
- [x] グローバル CSS を `_GLOBAL_CSS` 定数に集約・X ボタン HTML を `_X_BUTTON_HTML` 定数に抽出
- [x] ダイアログ UI 2フェーズ化（検索フェーズ / 編集フェーズ）完全分離
- [x] 編集フェーズを2カラムレイアウト（左=ゲーム画像 / 右=入力フォーム）に刷新
- [x] 「検索に戻る」「編集に戻る」ボタンでフェーズをシームレスに切り替え
- [x] `_price_badge_html(price_raw)` ヘルパー抽出（バッジ HTML の重複排除・XSS 対策集約）
- [x] `dlg_search_back_{i}` フラグ残留バグを修正（保存・キャンセル時のクリーンアップ）
- [x] サイドバー: 進捗バー（`st.progress`）でゲーム登録数を可視化
- [x] サイドバー: 「ポスターを生成」CTA ボタンを常駐化（スクロールなしで生成可能）
- [x] `DEV_MODE` フラグ + `_DEV_SAMPLE_GAMES` によるテストデータ一括入力機能

### 未実装・将来課題 (Todo)
- [ ] フォント取得の代替 URL（GitHub が落ちている場合のフォールバック）
- [ ] 生成プレビューのサイドバイサイド比較

---

## 6. 開発ルール・制約 (Rules)

### コーディング規約
- `app.py` 1ファイルに全機能を収める（Streamlit Community Cloud 向け）
- 関数名・変数名は処理内容が推測できる具体的な英語名
- 複雑な処理には日本語コメントを入れること
- 新しいライブラリを追加する際はユーザーに確認

### AI への指示
- `draw_card` と `generate_poster` の座標計算は `compute_layout()` が返す `dict` のキー経由で行うこと（ハードコード禁止）
- ダイアログ内ウィジェットには `dlg_` プレフィックスを付けること
- `@st.cache_data` 内で `st.session_state` を書き換えないこと
- 年齢制限ゲームの UI 表示: スロットカード・ダイアログともに `_show_age_restricted_thumb()` を使うこと
- `make_age_restricted_image` は `@lru_cache` 済みなので何度呼んでも安全
- `ensure_font()` は `main()` の冒頭で一度だけ呼ぶこと
- ダイアログを開く/閉じる操作は `st.session_state["editing_slot"]` の設定/削除＋`st.rerun()` で行うこと
- グローバル CSS は `_GLOBAL_CSS` 定数、X ボタン HTML は `_X_BUTTON_HTML` 定数を使うこと（インライン HTML 直書き禁止）
- HTML エスケープは `html.escape()` を使うこと（手動 `.replace()` 禁止）
- 価格バッジ HTML は `_price_badge_html(price_raw)` を使うこと（インライン HTML 直書き禁止）
- ダイアログのフェーズ切替フラグ `dlg_search_back_{i}` は、ダイアログを完全に閉じる際（保存・クリア・キャンセル）に必ず `pop` してクリアすること
- テストデータを入力する処理でも `dlg_search_back_{i}` を `pop` してクリアすること
- `DEV_MODE = False` にすれば開発者ツール UI は完全に非表示になる。本番リリース前にここを変更すること
- `_DEV_SAMPLE_GAMES` は API を呼ばずに直接 session_state へ書き込む。本番のゲームデータと同じ dict 構造（app_id, title, image_url, price, age_restricted, players, review）を維持すること

---

## 7. 更新履歴 (Changelog)

### 2026-04-10 v9（サイドバー強化・開発者モード）

**サイドバー: 進捗の可視化**
- `st.progress(filled / num_games, text=f"進捗: {filled} / {num_games} 本")` をサイドバー最上部に追加
- ゲーム登録数をスクロールなしで常に確認できる

**サイドバー: CTA ボタン常駐化**
- 「ポスターを生成」ボタンをサイドバーにも配置（`key="sidebar_generate_btn"`）
- メイン側ボタンと `generate_btn or sidebar_generate_btn` で同じ生成ロジックを共有
- `filled == 0` のとき `disabled=True`、生成済みは「再生成」に文言変更

**先行計算のリファクタリング**
- `show_title / layout / num_games / filled / already_generated` をサイドバーブロックより前で一括計算
- `main()` 内の重複変数（`filled`, `already_generated`）を削除し、先行計算した値を参照

**開発者モード（`DEV_MODE` フラグ）**
- `DEV_MODE: bool = True` を定数セクションに追加（`False` に変えるだけで dev UI が非表示）
- `_DEV_SAMPLE_GAMES`（12タイトル）をモジュール定数として定義
- サイドバー末尾に「テストデータを入力」ボタンを配置（`DEV_MODE=True` 時のみ表示）
    - `random.sample` で `num_games` 本分をランダムに選択し全スロットへ一括入力
    - `dlg_review_{idx}` / `dlg_players_{idx}` / `dlg_search_back_{idx}` も同時にリセット

**バグ修正**
- テストデータ入力時に `dlg_search_back_{idx}` フラグが残留し、次回ダイアログ開封時に検索フェーズになるバグを修正

### 2026-04-10 v8（ダイアログ UI 大幅刷新）

**ダイアログ 2フェーズ化**
- `edit_dialog` を「検索フェーズ」と「編集フェーズ」に完全分離
    - 検索フェーズ: 検索フォーム + 検索結果リストのみ表示
    - 編集フェーズ: 検索フォーム/リストは非表示。選択ゲームの画像＋入力フォームのみ
- フェーズ切替フラグ: `session_state[f"dlg_search_back_{i}"]` で管理
- 編集フェーズ上部に「検索に戻る」ボタン（`:material/search:`）を配置
- 検索フェーズでゲーム選択済みの場合は「編集に戻る」ボタンも表示

**編集フェーズの 2カラムレイアウト**
- `st.columns([1, 2])` で左=ゲーム画像（比率1）/ 右=タイトル・価格バッジ・プレイ人数・レビュー文（比率2）のダッシュボード風レイアウトを実現
- 検索候補画像と選択ゲーム画像が縦に2枚重なっていた問題を解消

**バグ修正**
- ダイアログを「保存」「キャンセル」で閉じた際に `dlg_search_back_{i}` フラグが残留し、次回開封時に誤って検索フェーズになるバグを修正
- 「クリア」ボタンでも同フラグを明示的に削除するよう統一

**コードリファクタリング（v8）**
- `_price_badge_html(price_raw: str) -> str` ヘルパーを抽出
    - `render_slot_card` と `edit_dialog` の両方で使用していた同一の囲み枠バッジ HTML を統一
    - `html.escape()` による XSS 対策を一元化
- 編集フェーズ冒頭で `over_limit = False` を防御的に初期化（依存関係を明示）

### 2026-04-10 v7（ビジュアル・UX 改善バッチ）

**サムネイル contain 表示**
- ポスター画像のサムネを cover（中央クロップ）→ contain（letterbox）に変更
- `load_pil_image_contain(url, w, h, bg_color=(0,0,0))` を追加
- Steam ヘッダー画像（460×215）がサムネ枠（380px 幅）に全体表示される

**ダイアログ: ゲーム選択後のヘッダー画像プレビュー**
- Progressive Disclosure 展開後（ゲーム選択済・検索中でない状態）にヘッダー画像を `st.image(width=250)` で表示
- 年齢制限ゲームは `st.warning("🔞 画像を取得できません")` でフォールバック
- レビュー・プレイ人数入力欄をフルwidth に変更（旧: 右カラムに収容）

**スロットカード UI**
- 価格を `border:1px solid #66c0f4` の囲み枠バッジ（Steam 青色）で表示
- プレイ人数を「プレイ人数: ソロ / オンライン協力」形式で表示
- スロット横並び高さ揃え CSS を強化（`height:100%` を伝播させる新ルール追加）

**免責事項の拡充**
- 短文キャプション: 「本アプリは非公式のファンメイドツールです」太字化
- 折りたたみ内を 5 セクションに整理（著作権・ユーザー責任・Steam API・データ保持・動作保証）
- 連絡先リンクを X ブランドカラーのボタン形式（黒背景 + SVG ロゴ）に変更

**コードリファクタリング（v7）**
- `import html` 追加、手動エスケープ `.replace()` を `html.escape()` に統一
- 2か所に分散していたグローバル CSS を `_GLOBAL_CSS` モジュール定数に統合
- X ボタン HTML を `_X_BUTTON_HTML` モジュール定数に抽出
- `main()` のインライン HTML を定数参照に置き換え

### 2026-04-10 v6（UX 改善バッチ）

**フォント取得の堅牢化**
- `FONT_URL` (単一) → `FONT_URLS` (リスト) に変更
- `ensure_font()` を複数 URL 順試み方式に改修（GitHub → jsDelivr CDN フォールバック）

**ダウンロードファイル名カスタマイズ**
- `_safe_filename(title)` ヘルパー追加（使用不可文字を `_` 置換、最大20文字）
- DL ファイル名: `steam_8pick_<タイトル>_YYYYMMDD.png` 形式に変更

**トグル OFF 時の UI 改善**
- 全体見出しトグル OFF 時: `st.text_input(disabled=True)` → 入力欄非表示 + `st.caption` 表示に変更
- session_state の値はウィジェット非表示時も保持（ON に戻すと入力内容が復元）

**UIカードのレビュー改行対応**
- `st.caption(review)` → XSSエスケープ + `\n` → `<br>` 変換の `st.markdown(unsafe_allow_html=True)` に変更

**テーマカラースウォッチ**
- テーマセレクトボックスの直下に3色スウォッチ（`bg` / `accent` / `card_bg`）を HTML で表示

**AppID 直接入力**
- 検索フォームで数字のみ入力した場合、Steam AppID として `get_game_details()` を直接呼び出す
- 検索→候補選択→確定の3ステップをスキップ
- プレースホルダ文字を "AppID（例: 570）" に言及するよう更新

### 2026-04-10 v5（定数集約・アプリ名変更・マージン縮小）

**アプリ名変更**
- `Steam8 Poster` → `SteamPosterMaker`（`APP_NAME`, `st.title`, `page_title`, ファイル冒頭コメント）
- ウォーターマーク表示も自動で更新（`APP_NAME` 定数を参照）

**カード間マージン縮小**
- `MARGIN`: 10 → 4 px
- カードサイズ: 950×227 → **954×235 px**（見出しON）/ 950×204 → **954×211 px**（見出しOFF）

**定数集約**
- `app.py` 冒頭の固定定数セクションに以下を追加・移動：
    - グリッド: `HEADER_H=120`, `PLAYER_H=26`, `ROW_GAP=6`, `TITLE_MAX_H_ON=52`, `TITLE_MAX_H_OFF=42`
    - タイポグラフィ: `HEADER_FONT_PT=64`, `TITLE_FONT_PT=28`, `TITLE_MIN_PT=16`, `PLAYER_FONT_PT=19`, `PLAYER_MIN_PT=13`, `REVIEW_FONT_PT=19`, `REVIEW_MIN_PT=11`, `PRICE_FONT_PT=24`, `SLOT_PH_FONT_PT=28`, `WM_FONT_PT=22`
- `compute_layout`, `draw_card`, `generate_poster` 内のハードコードをすべて定数参照に置き換え

### 2026-04-10 v4（コードレビュー・リファクタ）

**バグ修正**
- `sort_type` 変数が両分岐とも `"secondary"` のデッドコード → `reorder_mode` 中は `"primary"` に修正

**定数・構造整理**
- `PRICE_BADGE_PAD=8` / `PRICE_BADGE_EDGE=10` をモジュール定数として `draw_card` 内ローカル変数から昇格
- `generate_poster` のヘッダー文字幅取得: `textlength + textbbox` 二重呼び出しを `textbbox` 一本化
- `reorder_mode` の初期化を `main()` 内インラインから `init_session()` に集約
- `compute_layout` docstring のカードサイズ記載を実際の値（950×227 / 950×204）に修正
- 関数間の3連空白行を PEP 8 準拠の2行に統一

### 2026-04-10 v3.5（UI 細部改善）

- 並び替え: `st.expander` 内 D&D から「🔀 並び替え」トグルボタン + モード切替式に変更
- 価格バッジ: フォント 16pt → 24pt（1.5倍）、端からの余白 0 → 10px
- 全体見出し: `max_chars` 40 → 25（ヘッダー幅に基づく上限）
- `docs/design-decisions.md` 新規作成（UI/UX 判断ログ）

### 2026-04-09 v2（コードレビュー・リファクタ）

**バグ修正**
- `@st.cache_data` 内での `st.session_state` 書き換えを削除（`search_steam`）
- 年齢制限ゲームに blur 背景処理が走っていた問題を修正（`draw_card`）
- ダイアログ内で年齢制限ゲームに `st.image` を呼んでいた問題を修正
- ポスター生成前の画像プリフェッチで年齢制限ゲームを除外

**改善**
- `make_age_restricted_image` に `@lru_cache(maxsize=4)` を追加
- 🔞 UI サムネ HTML を `_show_age_restricted_thumb()` ヘルパーに抽出（重複排除）
- `st.status` + `st.success` の 2 重表示を解消（`st.success` 削除）

**死コード削除**
- `st.session_state.search_queries` — UI リファクタ後に未参照のため削除
- `_last_search_error` session_state キー — `@st.cache_data` との不整合のため削除

### 2026-04-10 v3（UX ポリッシュ・レイアウト調整）

- 検索フォームを `st.form` 化（Enter キー送信対応）
- レビュー文: `max_chars` 撤廃 → リアルタイム N/140 カウンター＋140字超で保存無効化
- `st.balloons` → `st.toast` に変更（完了通知を控えめに）
- サイドバーに開発者フォローリンク（X @Yuki_HERO44）
- 生成ボタン文言を初回「生成する」→ 2回目以降「再生成する」に切り替え
- 生成前に空きスロット数を `st.info` で案内
- スロットカード: フォントサイズ 0.78→0.88rem、カラー #aaa→#ccc、絵文字後 `&nbsp;`
- スロットカード間 CSS gap 2px
- レビュー文をカード全幅（下段）に移動
- ポスター MARGIN 20→10px（カード 950×227px / 950×204px に拡大）
- Steam ウィッシュリスト一括インポート機能追加
- API キー不要機能のみに絞り込み（最近プレイ・プレイ時間 TOP を削除）

### 2026-04-09 v1（初期実装・機能追加）

- プロジェクト作成・初期実装完了
- 全体見出しトグル（ON/OFF で 8/10 スロット切替）
- ポップアップダイアログ + ドラッグ＆ドロップ並べ替え UI に全面リファクタ
- 検索結果サムネプレビュー追加
- サムネ幅を 380px に拡大
- 価格バッジをサムネ右下に移動
- 年齢制限コンテンツの錠前アイコン実装
- st.spinner / st.status でローディング表示
- ポスター永続化（last_poster_bytes）
- 全幅ボタン（生成・ダウンロード）
