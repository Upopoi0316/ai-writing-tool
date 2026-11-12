"""生成結果の履歴。生成が成功するたびに、その時点の会話全体を 1 つの版として残す。"""

from __future__ import annotations

from dataclasses import dataclass, field

from gemini import Turn


@dataclass
class History:
    versions: list[list[Turn]] = field(default_factory=list)
    index: int = 0  # 表示中の版。修正指示はこの版の会話に続けて送る

    @property
    def current(self) -> list[Turn]:
        return self.versions[self.index]

    def add(self, turns: list[Turn]) -> None:
        """新しい版を末尾に追加して表示する。古い版を表示中でも、それ以降の版は消さない。"""
        self.versions.append(turns)
        self.index = len(self.versions) - 1

    def move(self, step: int) -> None:
        self.index = max(0, min(self.index + step, len(self.versions) - 1))


def describe(turns: list[Turn]) -> str:
    """版の作られ方を、画面に表示する 1 行の説明にする。"""
    if len(turns) <= 2:
        return "入力欄から生成"
    return "修正: " + " ".join(turns[-2].text.split())
