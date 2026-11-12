"""AI ライティングツール(Streamlit + Gemini)。

起動: streamlit run app.py
"""

from __future__ import annotations

import os
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

import gemini
from gemini import GeminiError, Turn
from history import History, describe
from plain_text import to_plain_text
from tools import TOOLS, TOOLS_BY_ID, Field, Tool, build_prompt, missing_required

_FIELD_PREFIX = "field."
_ASSETS = Path(__file__).parent / "assets"
_STYLE_PATH = _ASSETS / "style.css"
_RESULT_HEIGHT = 480  # 実際の高さは style.css の --result-body-height で画面に合わせて上書きする
_API_KEY_URL = "https://aistudio.google.com/apikey"
# よく使う修正指示(ボタンの表示, 送る指示)。1 行に収まるよう表示は短くする
_QUICK_EDITS = (
    ("短く", "もっと短く"),
    ("丁寧に", "もっと丁寧に"),
    ("箇条書きに", "箇条書きにして"),
    ("続きを書く", "続きを書いて"),
)
_LONG_DESCRIPTION = 24  # これより長い版の説明は省略されるので、全文を吹き出しで読めるようにする

# Streamlit にコピーボタンがないため自作する。全文は HTML に埋め込まず data で渡す
_copy_button = st.components.v2.component(
    "copy_button",
    html=(_ASSETS / "copy_button.html").read_text(encoding="utf-8"),
    css=(_ASSETS / "copy_button.css").read_text(encoding="utf-8"),
    js=(_ASSETS / "copy_button.js").read_text(encoding="utf-8"),
)


def _field_key(tool: Tool, field: Field) -> str:
    return f"{_FIELD_PREFIX}{tool.id}.{field.key}"


def _keep_drafts() -> None:
    # 非表示になった入力欄の値は Streamlit に破棄されるため、ツールを切り替えても残るようにする
    for key in list(st.session_state):
        if key.startswith(_FIELD_PREFIX):
            st.session_state[key] = st.session_state[key]


def _render_field(tool: Tool, field: Field) -> str:
    label = f"{field.label}(必須)" if field.required else field.label
    key = _field_key(tool, field)
    if field.kind == "select":
        return st.selectbox(label, field.options, key=key)
    if field.kind == "textarea":
        return st.text_area(label, key=key, placeholder=field.placeholder, height=200)
    return st.text_input(label, key=key, placeholder=field.placeholder)


def _render_group(tool: Tool, fields: list[Field]) -> dict[str, str]:
    """入力欄を縦に並べる。連続する選択欄は2列にまとめ、フォームを短くする。"""
    values: dict[str, str] = {}
    index = 0
    while index < len(fields):
        field = fields[index]
        following = fields[index + 1] if index + 1 < len(fields) else None
        if field.kind == "select" and following is not None and following.kind == "select":
            left, right = st.columns(2)
            with left:
                values[field.key] = _render_field(tool, field)
            with right:
                values[following.key] = _render_field(tool, following)
            index += 2
        else:
            values[field.key] = _render_field(tool, field)
            index += 1
    return values


def _render_form(tool: Tool) -> dict[str, str]:
    values = _render_group(tool, [f for f in tool.fields if not f.advanced])
    advanced = [f for f in tool.fields if f.advanced]
    if advanced:
        with st.expander("詳細オプション", icon=":material/tune:"):
            values |= _render_group(tool, advanced)
    return values


def _render_sidebar() -> tuple[Tool, str, str]:
    with st.sidebar:
        st.markdown("## AI Writing Tool")
        st.caption("書く、整える、伝えるをひとつに。")
        with st.container(key="tool-nav"):
            tool_id = st.radio(
                "ツール",
                [tool.id for tool in TOOLS],
                format_func=lambda tool_id: f"{TOOLS_BY_ID[tool_id].icon} {TOOLS_BY_ID[tool_id].name}",
                key="tool_id",
                label_visibility="collapsed",
            )
        st.divider()
        model = st.selectbox(
            "Gemini モデル",
            list(gemini.MODELS),
            format_func=gemini.MODELS.get,
            key="model",
        )
        env_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or ""
        if env_key:
            api_key = env_key
            st.caption(":material/check_circle: API キー設定済み")
        else:
            api_key = st.text_input(
                "Gemini API キー",
                type="password",
                key="api_key",
                help="入力したキーはこのセッション中だけメモリに保持され、ファイルには保存されません。",
            )
            st.caption(f"[API キーを発行する]({_API_KEY_URL})")
    return TOOLS_BY_ID[tool_id], model, api_key


def _run(tool: Tool, api_key: str, model: str, turns: list[Turn]) -> str | None:
    """生成を実行して本文を返す。失敗時はエラーを表示して None を返す。"""
    stream = gemini.generate(api_key, model, tool.system_instruction, turns)
    live = st.empty()
    try:
        with live.container():
            with st.container(
                horizontal=True,
                horizontal_alignment="distribute",
                vertical_alignment="center",
                key="stream-head",
            ):
                st.subheader("生成中", anchor=False, width="content")
                # 押すと Streamlit がスクリプトを再実行するので、受信のループはそこで止まる
                st.button("止める", icon=":material/stop_circle:", key=f"stop.{tool.id}", width="content")
            with st.container(height=_RESULT_HEIGHT, border=False, autoscroll=True, key="stream-body"):
                body = st.empty()
            with st.spinner("文章を書いています..."):
                for _ in stream:
                    body.markdown(stream.text)
    except GeminiError as exc:
        live.empty()
        st.error(str(exc), icon=":material/error:")
        return None
    if stream.truncated:
        st.session_state[f"truncated.{tool.id}"] = True
    return stream.text


def _render_empty() -> None:
    with st.container(key="result-empty", horizontal_alignment="center"):
        st.markdown(":material/edit_note:")
        st.markdown("**ここに生成結果が表示されます**")
        st.caption("入力欄を埋めて「生成する」を押してください。")


def _render_versions(tool: Tool, history: History) -> None:
    """前後の版へ移動する操作を表示する。版が 1 つのときは何も出さない。"""
    if len(history.versions) < 2:
        return
    with st.container(horizontal=True, wrap=False, vertical_alignment="center", key="version-nav"):
        st.button(
            "前の版",
            type="tertiary",
            icon=":material/chevron_left:",
            key=f"version.prev.{tool.id}",
            disabled=history.index == 0,
            on_click=history.move,
            args=(-1,),
        )
        st.caption(f"版 {history.index + 1} / {len(history.versions)}", width="content")
        # 説明には自分の入力が入るので、Markdown として解釈されない st.text を使う
        description = describe(history.current)
        st.text(description, help=description if len(description) > _LONG_DESCRIPTION else None)
        st.button(
            "次の版",
            type="tertiary",
            icon=":material/chevron_right:",
            icon_position="right",
            key=f"version.next.{tool.id}",
            disabled=history.index == len(history.versions) - 1,
            on_click=history.move,
            args=(1,),
        )


def _render_result(tool: Tool, history: History) -> None:
    result = history.current[-1].text
    plain = to_plain_text(result)
    with st.container(horizontal=True, vertical_alignment="center", key="result-head"):
        st.subheader("生成結果", anchor=False, width="content")
        # SNS の文字数制限などの目安になるよう、Markdown の記号を除いて数える
        st.caption(f"{len(plain):,} 文字")
        _copy_button(
            data={
                "text": plain if tool.plain_copy else result,
                "hint": "記号なしの文章をコピーします" if tool.plain_copy else "Markdown のままコピーします",
            },
            key=f"copy.{tool.id}",
            width="content",
        )
        st.download_button(
            "保存",
            result,
            file_name=f"{tool.id}-v{history.index + 1}.md",
            mime="text/markdown",
            key=f"download.{tool.id}",
            icon=":material/download:",
            help="Markdown ファイル(.md)として保存します。",
            width="content",
        )
    _render_versions(tool, history)
    if st.session_state.pop(f"truncated.{tool.id}", False):
        st.warning("文章が長すぎて途中で切れた可能性があります。「続きを書いて」と指示できます。")
    preview, markdown, plain_tab = st.tabs(["プレビュー", "Markdown", "記号なし"])
    with preview, st.container(height=_RESULT_HEIGHT, border=False, key="result-body"):
        st.markdown(result)
    with markdown, st.container(height=_RESULT_HEIGHT, border=False, key="result-copy"):
        st.caption("右上のアイコンで全文をコピーできます。")
        st.code(result, language=None, wrap_lines=True)
    with plain_tab, st.container(height=_RESULT_HEIGHT, border=False, key="result-plain"):
        st.caption("見出しや太字の記号を除いた文章です。右上のアイコンでコピーできます。")
        st.code(plain, language=None, wrap_lines=True)


def main() -> None:
    st.set_page_config(page_title="AI Writing Tool", page_icon=":material/edit_note:", layout="wide")
    st.html(_STYLE_PATH)
    load_dotenv()
    _keep_drafts()

    histories: dict[str, History] = st.session_state.setdefault("histories", {})
    tool, model, api_key = _render_sidebar()
    history = histories.get(tool.id)
    conversation = history.current if history else None

    st.header(f"{tool.icon} {tool.name}", anchor=False)
    st.caption(tool.description)

    with st.container(key="workspace"):
        input_column, result_column = st.columns([5, 6], gap="large")

    with input_column:
        if not api_key:
            st.info(
                f"生成には Gemini API キーが必要です。サイドバーに入力してください。[発行はこちら]({_API_KEY_URL})",
                icon=":material/key:",
            )
        values = _render_form(tool)
        # 結果があるときの主役は修正指示の欄なので、再生成は控えめな見た目にする
        submitted = st.button(
            "もう一度生成する" if conversation else "生成する",
            type="secondary" if conversation else "primary",
            icon=":material/refresh:" if conversation else ":material/edit_note:",
            key=f"submit.{tool.id}",
            shortcut="Mod+Enter",
            width="stretch",
        )
        form_message = st.container()

    with result_column, st.container(border=True, key="result-panel"):
        # 生成中の表示と結果を別の枠にする。結果の枠は st.empty なので、
        # 中身を書かない間(生成中)は前回の結果が画面から消える
        live_area = st.container()
        result_area = st.empty()
        feedback = None
        if conversation:
            with st.container(horizontal=True, gap="small", key="quick-edits"):
                for index, (label, instruction) in enumerate(_QUICK_EDITS):
                    if st.button(label, key=f"quick.{tool.id}.{index}", width="content"):
                        feedback = instruction
            typed = st.chat_input(
                "修正の指示を入力(例: 敬語を強めて、結論を先に)",
                key=f"feedback.{tool.id}",
            )
            feedback = typed or feedback

    new_turns: list[Turn] | None = None
    if submitted:
        missing = missing_required(tool, values)
        if missing:
            form_message.warning(f"入力してください: {'、'.join(missing)}", icon=":material/edit:")
        elif not api_key:
            form_message.warning("サイドバーで Gemini API キーを設定してください。", icon=":material/key:")
        else:
            new_turns = [Turn("user", build_prompt(tool, values))]
    elif feedback:
        if api_key:
            new_turns = [*conversation, Turn("user", feedback)]
        else:
            form_message.warning("サイドバーで Gemini API キーを設定してください。", icon=":material/key:")

    if new_turns is not None:
        with live_area:
            text = _run(tool, api_key, model, new_turns)
        if text is not None:
            histories.setdefault(tool.id, History()).add([*new_turns, Turn("model", text)])
            st.rerun()

    with result_area.container():
        if history:
            _render_result(tool, history)
        else:
            _render_empty()


if __name__ == "__main__":
    main()
