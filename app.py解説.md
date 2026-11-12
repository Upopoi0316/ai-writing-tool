# app.py を読み解く: Streamlit で作る AI ライティングツールの仕組み

## はじめに

`app.py` は、このアプリの**画面と操作の流れ**を担当するファイルです。Gemini との通信やツールごとの設定といった細かい処理は別のファイルに分けてあるので、`app.py` は全体をつなぐ「司令塔」として読むと理解しやすくなります。

| ファイル | 役割 |
| --- | --- |
| `app.py` | 画面を組み立て、ボタンが押されたら生成を呼び出す |
| `tools.py` | 8 つのツール(ブログ、メール…)の定義と、プロンプトの組み立て |
| `gemini.py` | Gemini API との通信(文章を少しずつ受け取る) |
| `history.py` | 生成した「版」の記録と、前後の版への移動 |
| `plain_text.py` | Markdown の記号を取り除く |
| `assets/` | 見た目の CSS と、自作のコピーボタン |

この記事では、`app.py` を上から順に読みながら、「なぜこう書いてあるのか」を説明します。行番号は `app.py:123` の形で書きます。

---

## 1. 最初に押さえる考え方: Streamlit は「毎回、最初から全部実行し直す」

ここを押さえておけば、残りはほぼ読めます。

普通の GUI アプリは「ボタンが押されたらこの関数を呼ぶ」という作りです。ところが Streamlit は、**ボタンを押すたび、文字を入力するたびに、`app.py` を上から下まで丸ごと実行し直します**。

```python
submitted = st.button("生成する")   # 押された回の実行だけ True が返る
if submitted:
    ...生成する...
```

`st.button(...)` は「ボタンを画面に描く」命令ですが、同時に「今回の実行がこのボタンを押したことで始まったか」を `True`/`False` で返します。

ただ、毎回やり直すと変数は全部消えてしまいます。そこで、実行をまたいで残したいデータは **`st.session_state`**(ブラウザのタブごとの保存箱)にしまいます。このアプリでは生成結果の履歴をここに入れています(`app.py:238`)。

```python
histories = st.session_state.setdefault("histories", {})
```

`setdefault` は「なければ空の辞書を作って入れ、あればそれを返す」という意味です。初回は空の辞書ができ、2 回目からは前の結果が入った辞書が返ります。

もうひとつ覚えておきたいのは、**Streamlit は書いた順に画面へ並べる**ということです。「あとで決まる内容を、画面の上のほうに出したい」ときは、先に場所だけ確保しておく必要があります。これはあとで何度も出てきます。

---

## 2. ファイルの冒頭: 定数と部品の準備(`app.py:1-40`)

```python
_FIELD_PREFIX = "field."
_RESULT_HEIGHT = 480
_QUICK_EDITS = (
    ("短く", "もっと短く"),
    ("丁寧に", "もっと丁寧に"),
    ("箇条書きに", "箇条書きにして"),
    ("続きを書く", "続きを書いて"),
)
```

名前が `_` で始まるのは「このファイルの中だけで使う」という Python の慣習です。

`_QUICK_EDITS` は結果の下に並ぶワンクリック修正ボタンの一覧で、(ボタンの表示, Gemini に送る指示) の組になっています。ボタンを増やしたければ、ここに 1 行足すだけで済みます。

```python
_copy_button = st.components.v2.component(
    "copy_button",
    html=(_ASSETS / "copy_button.html").read_text(encoding="utf-8"),
    css=...,
    js=...,
)
```

Streamlit には「クリップボードにコピーするボタン」が標準でないので、HTML・CSS・JavaScript で自作したものを部品(コンポーネント)として登録しています。登録は 1 回で済むので、関数の外に書いてあります。

---

## 3. 全体の流れ: `main()` を上から読む

本体は `main()`(`app.py:232`)です。1 回の実行でやっていることを順に並べると、次のようになります。

```
① ページ設定・CSS 読み込み・.env 読み込み・下書きの保護
② サイドバーを描く(ツール選択・モデル選択・API キー)
③ 左列: 入力フォームと「生成する」ボタン
④ 右列: 生成中の表示場所・結果の表示場所・修正指示の欄
⑤ 押されたボタンを見て、Gemini に送る会話(new_turns)を決める
⑥ 送るものがあれば生成 → 履歴に保存 → st.rerun() で最初からやり直し
⑦ 結果(または「ここに生成結果が表示されます」)を描く
```

以下、この順に見ていきます。

---

## 4. ① 準備(`app.py:233-236`)

```python
st.set_page_config(page_title="AI Writing Tool", page_icon=":material/edit_note:", layout="wide")
st.html(_STYLE_PATH)   # assets/style.css を読み込む
load_dotenv()          # .env の GEMINI_API_KEY を環境変数にする
_keep_drafts()
```

`layout="wide"` は画面の横幅いっぱいを使う設定です。入力と結果を左右に並べるために指定しています。

`_keep_drafts()`(`app.py:47`)は少しクセのある処理です。

```python
def _keep_drafts() -> None:
    for key in list(st.session_state):
        if key.startswith(_FIELD_PREFIX):
            st.session_state[key] = st.session_state[key]
```

自分自身を代入しているだけに見えますが、ちゃんと意味があります。Streamlit には「**今回の実行で画面に出なかった入力欄の値は捨てる**」という仕様があります。ブログ記事ツールから翻訳ツールに切り替えるとブログの入力欄は表示されなくなり、書きかけのテーマが消えてしまいます。こうして明示的に代入し直すと、Streamlit はその値を「アプリ側が管理する値」として扱い、捨てずに残します。

入力欄のキーは `_field_key`(`app.py:43`)で `field.blog.topic` のように「接頭辞.ツール ID.項目名」の形で作っています。ツールごとに別々の値を持てるのも、`_keep_drafts` が `field.` で始まるキーだけを探せるのも、この命名のおかげです。

---

## 5. ② サイドバー(`_render_sidebar`, `app.py:93`)

```python
with st.sidebar:
    tool_id = st.radio(
        "ツール",
        [tool.id for tool in TOOLS],
        format_func=lambda tool_id: f"{TOOLS_BY_ID[tool_id].icon} {TOOLS_BY_ID[tool_id].name}",
        key="tool_id",
        label_visibility="collapsed",
    )
```

`with st.sidebar:` の中に書いたものはサイドバーに表示されます。

ラジオボタンの選択肢の中身は `"blog"` や `"email"` といった ID です。表示するときだけ `format_func` を通して「ブログ記事」のような文字に変えています。データは扱いやすい ID のまま持ち、見た目は別に作るという、よく使われるやり方です。`TOOLS_BY_ID` は `tools.py` にある「ID → ツール定義」の辞書です。

API キーの部分(`app.py:112-123`)は、環境変数にキーがあればそれを使い、なければパスワード欄を出して入力してもらう、という分岐です。

```python
env_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or ""
if env_key:
    api_key = env_key
else:
    api_key = st.text_input("Gemini API キー", type="password", key="api_key", ...)
```

最後に `(選んだツール, モデル名, API キー)` の 3 つをまとめて返します。

---

## 6. ③ 左列: 入力フォーム(`app.py:246-265`)

```python
with st.container(key="workspace"):
    input_column, result_column = st.columns([5, 6], gap="large")
```

画面を 5:6 の比率で左右に分けています。`key="workspace"` は、`style.css` からこの部分だけを狙ってデザインを当てるための目印です(このファイルの `key=` は、ほとんどがこの目的か、部品を区別する目的です)。

### フォームを作る 3 つの関数

入力欄は、ツールの定義(`tools.py` の `Field`)をもとに自動で作られます。ツールごとに画面を手書きしなくて済むのがこの作りのよいところです。

- **`_render_field`**(`app.py:54`): 1 つの欄を作ります。`kind` が `"select"` ならプルダウン、`"textarea"` なら複数行の欄、それ以外は 1 行の欄です。必須項目にはラベルに「(必須)」を付けます。
- **`_render_group`**(`app.py:64`): 欄を縦に並べます。**プルダウンが 2 つ続いたら横に 2 列で並べる**工夫があり、フォームが縦に長くなりすぎないようにしています。
- **`_render_form`**(`app.py:84`): `advanced=True` の欄(想定読者、キーワードなど)を「詳細オプション」に折りたたみます。

```python
values = _render_group(tool, [f for f in tool.fields if not f.advanced])
advanced = [f for f in tool.fields if f.advanced]
if advanced:
    with st.expander("詳細オプション", icon=":material/tune:"):
        values |= _render_group(tool, advanced)
```

`values |= ...` は「辞書に別の辞書の中身を追加する」書き方です。最終的に `values` は `{"topic": "在宅勤務…", "length": "約1500字", ...}` のような辞書になります。

### 生成ボタン

```python
submitted = st.button(
    "もう一度生成する" if conversation else "生成する",
    type="secondary" if conversation else "primary",
    ...
    shortcut="Mod+Enter",
    width="stretch",
)
form_message = st.container()
```

`conversation` は「このツールで表示中の結果があるか」です。まだ結果がなければ目立つ色の「生成する」、結果があれば控えめな「もう一度生成する」になります。結果があるときの主役は、右側の修正指示のほうだからです。`shortcut="Mod+Enter"` で、Mac なら Cmd + Enter でも押せます。

`form_message = st.container()` が、1 章で触れた**場所の確保**です。「必須項目が空です」などの警告は、ボタンが押されたかどうかを判定したあと(⑤)で決まります。でも表示したい場所はボタンのすぐ下です。そこで、ボタンの下に空の入れ物を先に置いておき、あとから `form_message.warning(...)` で中身を入れています。

---

## 7. ④ 右列: 結果と修正指示の欄(`app.py:267-282`)

```python
with result_column, st.container(border=True, key="result-panel"):
    live_area = st.container()   # 生成中の表示を入れる場所
    result_area = st.empty()     # 結果を入れる場所
    feedback = None
    if conversation:
        with st.container(horizontal=True, gap="small", key="quick-edits"):
            for index, (label, instruction) in enumerate(_QUICK_EDITS):
                if st.button(label, key=f"quick.{tool.id}.{index}", width="content"):
                    feedback = instruction
        typed = st.chat_input("修正の指示を入力(例: 敬語を強めて、結論を先に)", key=f"feedback.{tool.id}")
        feedback = typed or feedback
```

ここでも 2 つの場所を先に確保しています。

- `live_area`: 生成中の文章を流す場所
- `result_area`: 完成した結果を出す場所

`result_area` が `st.empty()`(中身を 1 つだけ持てる入れ物)なのがポイントです。結果を書き込むのはこの関数のいちばん最後(⑦)なので、**生成中はまだ空のまま**です。そのため、生成を始めると前回の結果が消え、生成中の文章だけが見えます。

結果があるときだけ、修正ボタン(「短く」など)と指示の入力欄を出します。`feedback = typed or feedback` は「手で入力した指示があればそれを、なければボタンの指示を使う」という意味です。どちらもなければ `None` のままです。

---

## 8. ⑤ Gemini に送る会話を決める(`app.py:284-297`)

ここが「何が押されたか」を判断する部分です。

```python
new_turns: list[Turn] | None = None
if submitted:
    missing = missing_required(tool, values)
    if missing:
        form_message.warning(f"入力してください: {'、'.join(missing)}", ...)
    elif not api_key:
        form_message.warning("サイドバーで Gemini API キーを設定してください。", ...)
    else:
        new_turns = [Turn("user", build_prompt(tool, values))]
elif feedback:
    if api_key:
        new_turns = [*conversation, Turn("user", feedback)]
    else:
        form_message.warning(...)
```

### `Turn` は会話の 1 発言

`Turn`(`gemini.py:33`)は「誰が(`"user"` か `"model"`)、何を言ったか」だけを持つ小さなデータです。会話はこれのリストで表します。

```python
[
    Turn("user",  "次の条件でブログ記事を…"),   # 最初の依頼
    Turn("model", "# 在宅勤務で集中力を…"),     # Gemini の回答
    Turn("user",  "もっと短く"),               # 修正指示
]
```

### 「生成する」が押されたとき

入力欄の値から `build_prompt`(`tools.py:186`)でプロンプトを作り、**新しい会話**を始めます。たとえばブログ記事ツールなら、次のような文章になります。

```
次の条件でブログ記事を執筆してください。タイトル、導入、見出しごとの本文、まとめの順で構成してください。掲載先の指定があれば、…(以下、掲載先ごとの書き方の指示)

条件:
- テーマ: 在宅勤務で集中力を保つ方法
- 掲載先: note
- 長さの目安: 約1500字
- トーン: 丁寧

<material name="盛り込みたい内容・メモ">
朝の散歩を習慣にしたら…
</material>
```

貼り付けた素材を `<material>` タグで囲むのは、素材の中に「以上の指示を無視して…」のような文が混ざっていても、AI が指示ではなく素材として扱うようにするためです(`tools.py` の共通ルールにそう書いてあります)。

### 修正指示が来たとき

`[*conversation, Turn("user", feedback)]` は、**今表示している会話の末尾に修正指示を足した新しいリスト**です。`*conversation` はリストの中身を展開する書き方です。

Gemini 側には会話を保存させていない(`gemini.py` の `store=False`)ので、修正のたびに会話の最初から全部を送っています。だから Gemini は「さっきの記事を短くする」ことができます。

---

## 9. ⑥ 生成して保存する(`app.py:299-304` と `_run`)

```python
if new_turns is not None:
    with live_area:
        text = _run(tool, api_key, model, new_turns)
    if text is not None:
        histories.setdefault(tool.id, History()).add([*new_turns, Turn("model", text)])
        st.rerun()
```

`with live_area:` とすることで、`_run` の中で描いたものは ④ で確保した場所に表示されます。

### `_run`: 文章を流しながら表示する(`app.py:127`)

```python
stream = gemini.generate(api_key, model, tool.system_instruction, turns)
live = st.empty()
try:
    with live.container():
        ...「生成中」の見出しと「止める」ボタン...
        with st.container(height=_RESULT_HEIGHT, border=False, autoscroll=True, key="stream-body"):
            body = st.empty()
        with st.spinner("文章を書いています..."):
            for _ in stream:
                body.markdown(stream.text)
except GeminiError as exc:
    live.empty()
    st.error(str(exc), icon=":material/error:")
    return None
```

`stream` は、Gemini から文章が少し届くたびに 1 回ループが回るオブジェクトです(`gemini.py` の `GenerationStream`)。届いた分は `stream.text` にたまっていくので、ループのたびに `body.markdown(stream.text)` で**これまでの全文を描き直します**。`st.empty()` は中身を上書きできるので、文章がだんだん伸びていくように見えます。`autoscroll=True` で、枠は自動的に下へスクロールします。

#### 「止める」ボタンの仕組み

```python
# 押すと Streamlit がスクリプトを再実行するので、受信のループはそこで止まる
st.button("止める", ...)
```

このボタンの戻り値はどこでも使っていません。それでも止まるのは、1 章の仕組みのおかげです。ボタンを押すと Streamlit は**今の実行を打ち切って最初からやり直す**ので、受信中の `for` ループもそこで終わります。やり直した回では `new_turns` が `None` なので、生成は始まりません。

#### エラーのとき

API キーが間違っている、利用上限に達した、などのエラーは `gemini.py` が `GeminiError` という日本語メッセージ付きのエラーに変換してくれます。`_run` はそれを受け取り、生成中の表示を消して(`live.empty()`)赤いエラー表示を出し、`None` を返します。`None` なら履歴には何も保存しません。

#### 途中で切れたとき

```python
if stream.truncated:
    st.session_state[f"truncated.{tool.id}"] = True
return stream.text
```

文章が長すぎて Gemini が途中で打ち切った場合は、印を `session_state` に残します。このあとすぐ `st.rerun()` でやり直すため、普通の変数では印が消えてしまうからです。印は ⑦ の結果表示で読み取られます。

### 保存して、最初からやり直す

生成に成功したら、会話の末尾に Gemini の回答を足して、1 つの「版」として履歴に追加します。

```python
histories.setdefault(tool.id, History()).add([*new_turns, Turn("model", text)])
st.rerun()
```

そして `st.rerun()` で、**自分から最初の実行をやり直します**。なぜでしょうか。

この時点の画面は、生成前の状態で組み立てられています。ボタンは「生成する」のままで、修正ボタンも出ていません。最初から実行し直せば、`conversation` に今の結果が入った状態で画面全体が組み立てられ、「もう一度生成する」や修正ボタンが正しく表示されます。

---

## 10. ⑦ 結果を表示する(`app.py:306-310`)

```python
with result_area.container():
    if history:
        _render_result(tool, history)
    else:
        _render_empty()
```

④ で確保した `result_area` に、結果か「ここに生成結果が表示されます」の案内を入れます。

### `_render_result`(`app.py:193`)

```python
result = history.current[-1].text    # 表示中の版の、最後の発言(= Gemini の回答)
plain = to_plain_text(result)        # Markdown の記号を除いた文章
```

見出しの行には次のものが並びます。

- **文字数**: 記号を除いた `plain` で数えています。SNS の文字数制限の目安にするためです。
- **コピーボタン**: 自作の部品です。メール返信と SNS 投稿のように `plain_copy=True` のツールでは記号なしの文章を、それ以外は Markdown のままコピーします。
- **保存ボタン**: `blog-v2.md` のような名前で Markdown ファイルをダウンロードします。

その下に、前後の版へ移る操作(`_render_versions`)、途中で切れたときの警告、そして 3 つのタブ(プレビュー / Markdown / 記号なし)が続きます。

```python
if st.session_state.pop(f"truncated.{tool.id}", False):
    st.warning("文章が長すぎて途中で切れた可能性があります。…")
```

`pop` は「値を取り出して、同時に消す」操作です。⑥ で残した印をここで読み、消します。こうすると警告は 1 回だけ表示され、次の操作では出なくなります。

---

## 11. 版(バージョン)の仕組み(`history.py` と `_render_versions`)

`History`(`history.py:11`)は、とてもシンプルなクラスです。

```python
@dataclass
class History:
    versions: list[list[Turn]]   # 版の一覧。1 つの版 = 1 つの会話全体
    index: int = 0               # 今表示している版の番号
```

- `add`: 新しい版を末尾に追加し、それを表示します。
- `move`: 表示する版を前後に動かします。端からはみ出さないよう `max`/`min` で範囲内に収めています。
- `current`: 表示中の版の会話を返します。

面白いのは、**古い版を表示している状態で修正指示を出すと、その古い版の続きとして新しい版ができる**ことです。⑤ の `[*conversation, ...]` の `conversation` が、表示中の版(`history.current`)だからです。「版 2 のほうがよかったから、そこから別の方向に直したい」といった使い方ができます。新しい版は末尾に追加されるだけなので、それまでの版は消えません。

`_render_versions`(`app.py:163`)のボタンは `on_click=history.move, args=(-1,)` という書き方をしています。これは「ボタンが押されたら、再実行の**前に** `history.move(-1)` を呼ぶ」という指定です。版の番号を先に動かしてから再実行するので、再実行した回では最初から新しい版が表示されます。

版の説明には「修正: もっと短く」のように自分の入力が表示されます。ここで `st.markdown` ではなく `st.text` を使っているのは、入力に `*` や `#` が含まれていても、太字や見出しとして解釈されないようにするためです。

---

## 12. 操作をひとつ追ってみる

最後に、実際の操作で `app.py` がどう動くかを追ってみます。

**1 回目: アプリを開く**
`histories` は空。`history` は `None` なので、左にフォーム、右に「ここに生成結果が表示されます」が出ます。

**2 回目: テーマを入れて「生成する」を押す**
最初から実行され、`submitted` が `True` になります。必須項目と API キーを確認して `new_turns = [依頼文]` を作り、`_run` で文章を流しながら表示します。成功したら版 1 として保存し、`st.rerun()`。

**3 回目: `st.rerun()` によるやり直し**
`conversation` に版 1 の会話が入っているので、ボタンは「もう一度生成する」になり、修正ボタンと入力欄が現れ、右に結果が出ます。

**4 回目: 「短く」を押す**
`feedback = "もっと短く"` になり、`new_turns = [依頼文, 回答, "もっと短く"]` を Gemini に送ります。成功したら版 2 として保存し、また `st.rerun()`。

**5 回目: やり直し**
版 2 が表示され、「版 2 / 2 修正: もっと短く」と「前の版」ボタンが出ます。

---

## まとめ

`app.py` を読むときのコツは、次の 3 つです。

1. **操作のたびに上から全部やり直す。** ボタンの戻り値は「今回それが押されたか」。
2. **残したいものは `st.session_state` に入れる。** 履歴、途中で切れた印、入力欄の下書きなど。
3. **画面は書いた順に並ぶので、あとで決まる内容の場所は先に確保する。** `form_message`、`live_area`、`result_area` がそれ。

この 3 つを頭に置いて `main()` を上から読めば、ほかの関数は「画面の一部分を描く部品」として読めるはずです。

### 試してみるなら

- `_QUICK_EDITS` に `("結論を先に", "結論を先に書いて")` を足すと、修正ボタンが 1 つ増えます。
- `_RESULT_HEIGHT` の数字を変えると、結果の枠の高さが変わります(実際の高さは `assets/style.css` 側で上書きされる点に注意)。
- 新しいツールを足したいときは、`app.py` には手を入れず、`tools.py` の `TOOLS` に 1 つ追記するだけで済みます。フォームが自動で作られる仕組みを実感できます。
