# PROJECT CONTEXT & MEMORY

AI エージェントがプロジェクトの文脈を理解し、適切な支援を提供するための **クイックリファレンス** です。  
詳細な履歴・設計判断は `docs/` の各ファイルを参照してください。

| ドキュメント | 内容 |
|---|---|
| `docs/changelog.md` | 全バージョン更新履歴（v1〜最新） |
| `docs/design-decisions.md` | UI/UX 設計判断ログ |
| `docs/setup-guide.md` | セットアップ手順 |
| `docs/troubleshooting.md` | トラブルシューティング |

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
│   ├── 固定定数（DEV_MODE, _DEV_SAMPLE_GAMES, THEMES, レイアウト定数など）
│   ├── レイアウト計算 (compute_layout)
│   ├── フォント管理 (ensure_font, get_font with lru_cache)
│   ├── Steam API (@st.cache_data: search_steam, get_game_details)
│   ├── 画像ユーティリティ (_fetch_raw_image, load_pil_image, load_pil_image_contain,
│   │                       make_age_restricted_image)
│   ├── UI ヘルパー (_show_age_restricted_thumb, _price_badge_html)
│   ├── テキスト描画 (wrap_text_pixels, fit_text_in_box)
│   ├── カード描画 (draw_card)
│   ├── ポスター生成 (generate_poster)
│   └── Streamlit UI (init_session, edit_dialog, render_slot_card, main)
├── requirements.txt
├── .streamlit/config.toml
├── docs/
│   ├── changelog.md         # 全バージョン更新履歴（v1〜）
│   ├── design-decisions.md  # UI/UX 設計判断ログ
│   ├── setup-guide.md       # セットアップ手順
│   └── troubleshooting.md   # トラブルシューティング
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

> 詳細は [`docs/changelog.md`](docs/changelog.md) を参照してください。

| バージョン | 日付 | 主な変更 |
|---|---|---|
| **v9** | 2026-04-10 | サイドバー進捗バー・CTA 常駐ボタン・`DEV_MODE` 開発者モード追加 |
| v8 | 2026-04-10 | ダイアログ 2フェーズ化・編集フェーズ 2カラムレイアウト・`_price_badge_html` 抽出 |
| v7 | 2026-04-10 | サムネ contain 表示・ダイアログ画像プレビュー・カード UI 改善・免責事項拡充 |
| v6 | 2026-04-10 | フォント URL フォールバック・AppID 直接入力・DL ファイル名カスタマイズ |
| v5 | 2026-04-10 | アプリ名変更・MARGIN 縮小・全定数集約 |
| v4 | 2026-04-10 | コードレビュー・リファクタ・バグ修正 |
| v3.5 | 2026-04-10 | 並び替えモード刷新・価格バッジ拡大 |
| v3 | 2026-04-10 | UX ポリッシュ・Enter キー送信・リアルタイムカウンター |
| v2 | 2026-04-09 | コードレビュー・年齢制限バグ修正・デッドコード削除 |
| v1 | 2026-04-09 | 初期実装 |
