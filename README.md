# AI Writing Tool

Streamlit と Gemini API で作った、個人用のライティングツールです。データベースと認証はありません。

## 機能

| ツール | 内容 |
| --- | --- |
| 📝 ブログ記事 | テーマから記事を執筆(note・はてなブログ・Qiita/Zenn など掲載先に合わせた書き方も可能) |
| ✉️ メール返信 | 受信メールと要点から返信文を作成 |
| 📄 要約 | 長文を指定の形式で要約 |
| ✏️ 校正・リライト | 誤字修正、読みやすさの改善と修正点の提示 |
| 🌐 翻訳 | 自然な文章に翻訳(訳語の指定も可能) |
| 💡 タイトル案 | タイトルや件名の候補を提案 |
| 📣 SNS投稿 | 媒体に合わせた投稿文を作成 |
| 🗒️ メモから文章化 | 走り書きを報告書や議事録に整形 |

全ツール共通で、入力と結果を並べて確認しながら、文章の逐次表示、「もっと短く」などの追加指示(よく使うものはワンクリック)、前の版に戻す操作、生成の中断、コピー(Markdown または記号なし)、Markdown 保存ができます。入力中に Cmd/Ctrl + Enter でも生成できます。版はブラウザのセッション中だけ保持され、再読み込みすると消えます。

## セットアップ

Python 3.11 以上が必要です(動作確認は Python 3.15 で行っています)。

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # .env に GEMINI_API_KEY を設定
```

API キーは [Google AI Studio](https://aistudio.google.com/apikey) で発行できます。`.env` を作らず、画面のサイドバーに入力しても使えます。

## 起動

```bash
streamlit run app.py
```

## カスタマイズ

- ツールの追加: `tools.py` の `TOOLS` に追記します。
- デザインの変更: 配色とフォントは `.streamlit/config.toml`、それ以外は `assets/style.css` で調整します。
- モデルの変更: `gemini.py` の `MODELS` を編集します。先頭が既定のモデルです。

## データの扱い

- 入力と結果はブラウザのセッション中だけメモリに保持され、再読み込みすると消えます。
- 入力した文章は Gemini API に送信されます。`store=False` を指定し、Interactions API のサーバー側保存を無効にしています。
- 無料枠では、送信内容が Google のサービス改善に使われる場合があります。機密情報を扱う前に Gemini API の利用規約を確認してください。
- 認証がないため、`.streamlit/config.toml` で `localhost` からのアクセスのみに制限しています。
