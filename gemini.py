"""Gemini Interactions API を呼び出す薄いラッパー。"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

from google import genai

# 先頭が既定のモデル。一覧の出典: https://ai.google.dev/gemini-api/docs/models
MODELS: dict[str, str] = {
    "gemini-3.5-flash-lite": "3.5 Flash-Lite(低コスト)",
    "gemini-3.8-flash": "3.8 Flash(高品質)",
    "gemini-3.6-flash": "3.6 Flash(安定版)",
}
DEFAULT_MODEL = next(iter(MODELS))

_CONTINUING = "requires_continuation"
_FRIENDLY_STATUS = {
    400: "リクエストが不正です。入力内容か API キーを確認してください。",
    401: "API キーが無効です。設定を確認してください。",
    403: "この API キーでは利用できません。権限を確認してください。",
    404: "選択したモデルが見つかりません。別のモデルを選んでください。",
    429: "利用上限に達しました。少し待ってから再度お試しください。",
}


class GeminiError(Exception):
    """画面にそのまま表示できるメッセージを持つエラー。"""


@dataclass(frozen=True)
class Turn:
    role: str  # "user" または "model"
    text: str


def _to_step(turn: Turn) -> dict:
    step_type = "user_input" if turn.role == "user" else "model_output"
    return {"type": step_type, "content": [{"type": "text", "text": turn.text}]}


def _friendly_error(exc: Exception) -> GeminiError:
    # Interactions API の例外クラスは SDK の公開パスから import できないため、属性で判定する
    status = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    if status in _FRIENDLY_STATUS:
        return GeminiError(_FRIENDLY_STATUS[status])
    if isinstance(status, int) and status >= 500:
        return GeminiError("Gemini 側で一時的なエラーが発生しました。少し待って再度お試しください。")
    name = type(exc).__name__
    if "Timeout" in name or "Connection" in name or "Connect" in name:
        return GeminiError("Gemini に接続できませんでした。ネットワークを確認してください。")
    return GeminiError(f"生成に失敗しました: {exc}")


def _is_sdk_error(exc: Exception) -> bool:
    # コード側のバグを API エラーとして握りつぶさないよう、SDK と通信層の例外だけを変換する
    return type(exc).__module__.split(".")[0] in {"google", "httpx", "httpcore"}


class GenerationStream:
    """テキストを順に返すイテラブル。完了後に truncated と text を参照できる。"""

    def __init__(self, api_key: str, model: str, system_instruction: str, turns: list[Turn]):
        self._api_key = api_key
        self._model = model
        self._system_instruction = system_instruction
        self._turns = turns
        self._status: str | None = None
        self.text = ""

    @property
    def truncated(self) -> bool:
        return self._status == "incomplete"

    def __iter__(self) -> Iterator[str]:
        try:
            yield from self._generate()
        except GeminiError:
            raise
        except Exception as exc:
            if not _is_sdk_error(exc):
                raise
            raise _friendly_error(exc) from exc

    def _generate(self) -> Iterator[str]:
        client = genai.Client(api_key=self._api_key)
        stream = client.interactions.create(
            model=self._model,
            system_instruction=self._system_instruction,
            input=[_to_step(turn) for turn in self._turns],
            stream=True,
            # 貼り付けたメール等をサーバー側に残さない(履歴は毎回送信する)
            store=False,
        )
        for event in stream:
            if event.event_type == "step.delta" and event.delta.type == "text":
                self.text += event.delta.text
                yield event.delta.text
            elif event.event_type == "error":
                message = event.error.message if event.error else "不明なエラー"
                raise GeminiError(f"生成に失敗しました: {message}")
            elif event.event_type == "interaction.completed":
                if event.interaction.status != _CONTINUING:
                    self._status = event.interaction.status

        if self._status not in (None, "completed", "incomplete"):
            raise GeminiError(f"生成が完了しませんでした(状態: {self._status})。")
        if not self.text:
            raise GeminiError(
                "応答が空でした。安全フィルタで止められた可能性があります。内容を変えて再度お試しください。"
            )


def generate(api_key: str, model: str, system_instruction: str, turns: list[Turn]) -> GenerationStream:
    return GenerationStream(api_key, model, system_instruction, turns)
