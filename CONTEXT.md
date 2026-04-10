# PROJECT CONTEXT & MEMORY

このドキュメントは、AI エージェントがプロジェクトの文脈を理解し、適切な支援を提供するための情報をまとめたものです。

---

## 1. プロジェクト概要 (Overview)

* **アプリ名**: App_035 Steam8 Poster
* **目的**: Steam ゲーム布教用まとめ画像（最大10本紹介）を X (Twitter) 向けに 1920×1080 PNG で自動生成する Web アプリ
* **ターゲットユーザー**: Steam ゲームをオススメしたいゲーマー
* **主要機能**:
    * Steam ストア API でゲームを検索・詳細取得（キャッシュ付き）
    * 最大10スロット管理（session_state で状態保持）
    * ポップアップダイアログ（`st.dialog`）でゲームを編集
    * ドラッグ＆ドロップによるスロット並べ替え（`streamlit-sortables`）
    * 1920×1080 PNG ポスター生成（Pillow）
    * テーマカラー5種・背景スタイル2種（ぼかしスライダー/単色）
    * 日本語対応ピクセル幅ベースのテキスト折り返し + フォント自動縮小
    * 年齢制限コンテンツを錠前アイコン（Pillow 描画）で可視化

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
App_035_Steam8Poster/
├── app.py                   # アプリ全体（単一ファイル構成）
│   ├── 固定定数・レイアウト計算 (compute_layout)
│   ├── テーマカラー定義 (THEMES dict — 5テーマ × 6色)
│   ├── フォント管理 (ensure_font, get_font with lru_cache)
│   ├── Steam API (@st.cache_data: search_steam, get_game_details)
│   ├── 画像ユーティリティ (_fetch_raw_image, load_pil_image, make_age_restricted_image)
│   ├── UI ヘルパー (_show_age_restricted_thumb)
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
- `show_title=True` : ヘッダー 120px + 2列×4行 = **8スロット**（カード 930×215 px）
- `show_title=False`: ヘッダーなし + 2列×5行 = **10スロット**（カード 930×192 px）
- どちらも出力は **1920×1080 px 固定**
- `title_max_h` を縮小して `review_max_h` を最大化（レビュー文の表示エリアを広く）

### カードレイアウト
- サムネ幅: **380 px**（Steam ヘッダー画像 460×215 の約83%を表示）
- アクセントカラーの縦区切り線（3px）がサムネとテキストを分離
- 価格: サムネ右下に **半透明バッジ**（`Image.alpha_composite` で合成）として描画
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
- タイトル: 初期 **28pt** → 最小 **16pt**
- プレイ人数: 初期 19pt → 最小 13pt
- レビュー文: 初期 19pt → 最小 11pt

### セッション状態
- **ゲームデータ**: `st.session_state.games[i]`（dict or None）
- **検索結果**: `st.session_state.search_results[i]`
- ~~`search_queries`~~: UI リファクタ後に未参照となったため削除済み
- **ダイアログ**: `st.session_state["editing_slot"] = i` でポップアップを開く。ダイアログ内ウィジェットは `dlg_review_{i}`, `dlg_players_{i}`, `dlg_q_{i}` キーで管理
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
- [x] Steam ウィッシュリストからの一括インポート（API キー不要）
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
- [x] ポスター MARGIN 20 → 10 px（カードサイズ 950×227 px に拡大）
- [x] フォント自動ダウンロード（Noto Sans CJK JP Bold）
- [x] PNG ダウンロード（1920×1080）
- [x] ウォーターマーク
- [x] コードレビュー・リファクタリング（2026-04-09 v2・v3）

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
- 年齢制限ゲームの UI 表示には `_show_age_restricted_thumb()` を使うこと（HTML を直書きしない）
- `make_age_restricted_image` は `@lru_cache` 済みなので何度呼んでも安全
- `ensure_font()` は `main()` の冒頭で一度だけ呼ぶこと
- ダイアログを開く/閉じる操作は `st.session_state["editing_slot"]` の設定/削除＋`st.rerun()` で行うこと

---

## 7. 更新履歴 (Changelog)

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
