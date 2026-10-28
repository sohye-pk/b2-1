"""거래 모델과 공통 값 검증."""

from dataclasses import dataclass, field
from datetime import date
import re
from typing import Any


class AppError(Exception):
    def __init__(self, message: str, hint: str) -> None:
        super().__init__(message)
        self.hint = hint


def valid_date(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise AppError("날짜 형식이 올바르지 않습니다.", "YYYY-MM-DD 형식으로 입력하세요.")
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise AppError("존재하지 않는 날짜입니다.", "달력에 있는 날짜를 입력하세요.") from exc
    return value


def valid_month(value: str) -> str:
    if not re.fullmatch(r"\d{4}-\d{2}", value):
        raise AppError("월 형식이 올바르지 않습니다.", "YYYY-MM 형식으로 입력하세요.")
    valid_date(value + "-01")
    return value


def positive_int(value: str | int) -> int:
    if isinstance(value, bool) or not re.fullmatch(r"[0-9]+", str(value)):
        raise AppError("금액 또는 개수는 양수 정수여야 합니다.", "소수점 없이 1 이상의 정수를 입력하세요.")
    try:
        result = int(value)
    except ValueError as exc:
        raise AppError("금액 또는 개수를 정수로 변환할 수 없습니다.", "너무 긴 숫자 대신 필요한 범위의 정수를 입력하세요.") from exc
    if result <= 0:
        raise AppError("금액 또는 개수는 0보다 커야 합니다.", "1 이상의 정수를 입력하세요.")
    return result


def valid_type(value: str) -> str:
    if value not in ("income", "expense"):
        raise AppError("허용되지 않은 거래 타입입니다.", "income 또는 expense를 입력하세요.")
    return value


def parse_tags(value: str) -> list[str]:
    return list(dict.fromkeys(tag.strip() for tag in value.split(",") if tag.strip()))


@dataclass(frozen=True)
class Transaction:
    id: str
    type: str
    date: str
    amount: int
    category: str
    memo: str = ""
    tags: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        valid_date(self.date)
        valid_type(self.type)
        if type(self.amount) is not int:
            raise AppError("거래 금액의 저장 타입이 올바르지 않습니다.", "양수 정수로 저장하세요.")
        positive_int(self.amount)
        if not isinstance(self.id, str) or not self.id.strip():
            raise AppError("거래 ID가 비어 있습니다.", "유효한 ID가 있는 데이터를 사용하세요.")
        if not isinstance(self.category, str) or not self.category.strip():
            raise AppError("카테고리가 비어 있습니다.", "등록된 카테고리를 입력하세요.")
        if not isinstance(self.memo, str) or not isinstance(self.tags, list) or any(
            not isinstance(tag, str) for tag in self.tags
        ):
            raise AppError("메모 또는 태그 형식이 잘못되었습니다.", "메모는 문자열, 태그는 문자열 목록이어야 합니다.")

    @property
    def sort_key(self) -> tuple[str, str]:
        return self.date, self.id

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> "Transaction":
        return cls(**record)


@dataclass(frozen=True)
class MonthSummary:
    income: int
    expense: int
    count: int
    top_categories: list[tuple[str, int]]
    budget: int | None

    @property
    def balance(self) -> int:
        return self.income - self.expense
