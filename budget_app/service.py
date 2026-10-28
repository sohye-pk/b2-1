"""파일 형식과 CLI에서 독립적인 가계부 처리 규칙."""

from itertools import islice
from typing import Iterator
from uuid import uuid4

from .models import AppError, Transaction, parse_tags, positive_int, valid_date, valid_type
from .repository import TransactionRepository


class BudgetService:
    def __init__(self, repository: TransactionRepository) -> None:
        self.repository = repository

    def category_add(self, name: str) -> None:
        categories = self.repository.categories()
        if not name.strip() or name in categories:
            raise AppError("비어 있거나 이미 등록된 카테고리입니다.", "category list로 확인 후 새 이름을 입력하세요.")
        self.repository.save_categories(categories + [name])

    def category_remove(self, name: str) -> None:
        self.require_category(name)
        if any(tx.category == name for tx in self.repository.iter_transactions()):
            raise AppError("사용 중인 카테고리는 삭제할 수 없습니다.", "해당 거래를 수정하거나 삭제한 뒤 다시 시도하세요.")
        self.repository.save_categories([item for item in self.repository.categories() if item != name])

    def require_category(self, name: str) -> None:
        if name not in self.repository.categories():
            raise AppError(f"등록되지 않은 카테고리: {name}", "category list로 확인하거나 category add로 등록하세요.")

    def make_transaction(
        self, date: str, type: str, category: str, amount: str | int,
        memo: str = "", tags: str = "",
    ) -> Transaction:
        self.require_category(category)
        return Transaction(
            id=str(uuid4()), date=valid_date(date), type=valid_type(type),
            category=category, amount=positive_int(amount), memo=memo, tags=parse_tags(tags),
        )

    def add(
        self, date: str, type: str, category: str, amount: str | int,
        memo: str = "", tags: str = "",
    ) -> Transaction:
        transaction = self.make_transaction(date, type, category, amount, memo, tags)
        self.repository.merge_transactions([transaction])
        return transaction

    def list_transactions(self, limit: int = 10) -> Iterator[Transaction]:
        positive_int(limit)
        yield from islice(self.repository.iter_transactions(), limit)
