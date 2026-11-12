// 結果の全文をクリップボードへコピーするボタン。
// 全文は AI の出力なので、HTML としては描画せず、クリップボードへ渡すだけにする。
const LABEL = "コピー";
const RESET_MS = 2000;

export default function ({ parentElement, data }) {
  const button = parentElement.querySelector("button");
  const label = parentElement.querySelector(".label");
  let timer;

  const show = (text, state, title = data.hint) => {
    label.textContent = text;
    button.title = title;
    button.classList.remove("done", "failed");
    if (state) button.classList.add(state);
  };

  button.title = data.hint;

  // 全文が変わるとこの関数が再度呼ばれる。代入で上書きし、常に最新の全文をコピーする
  button.onclick = async () => {
    clearTimeout(timer);
    try {
      await navigator.clipboard.writeText(data.text);
      show("コピー済み", "done");
    } catch {
      show("コピー失敗", "failed", "「Markdown」か「記号なし」のタブから手動でコピーしてください。");
    }
    timer = setTimeout(() => show(LABEL), RESET_MS);
  };

  return () => clearTimeout(timer);
}
