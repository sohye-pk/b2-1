"""파일 형식과 CLI에서 독립적인 가계부 처리 규칙."""

from dataclasses import replace
import csv
from itertools import islice
from pathlib import Path
from typing import Iterator
from uuid import uuid4

from .models import AppError, MonthSummary, Transaction, parse_tags, positive_int, valid_date, valid_month, valid_type
from .repository import TransactionRepository, atomic_output

CSV_COLUMNS = ("date", "type", "category", "amount", "memo", "tags")


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

    def find(self, transaction_id: str) -> Transaction:
        for transaction in self.repository.iter_transactions():
            if transaction.id == transaction_id:
                return transaction
        raise AppError(f"없는 데이터: {transaction_id}", "list 또는 search로 거래 ID를 확인하세요.")

    def update(
        self, transaction_id: str, date: str | None = None, type: str | None = None,
        category: str | None = None, amount: str | None = None,
        memo: str | None = None, tags: str | None = None,
    ) -> None:
        if all(value is None for value in (date, type, category, amount, memo, tags)):
            raise AppError("수정할 필드가 없습니다.", "--amount, --date 등 수정할 옵션을 지정하세요.")
        current = self.find(transaction_id)
        if category is not None:
            self.require_category(category)
        updated = replace(
            current, date=valid_date(date) if date is not None else current.date,
            type=valid_type(type) if type is not None else current.type,
            category=category if category is not None else current.category,
            amount=positive_int(amount) if amount is not None else current.amount,
            memo=memo if memo is not None else current.memo,
            tags=parse_tags(tags) if tags is not None else current.tags,
        )
        self.repository.merge_transactions([updated], remove_id=transaction_id)

    def delete(self, transaction_id: str) -> None:
        self.find(transaction_id)
        self.repository.merge_transactions([], remove_id=transaction_id)

    def search(
        self, start: str | None = None, end: str | None = None,
        category: str | None = None, type: str | None = None,
        q: str | None = None, tag: str | None = None,
    ) -> Iterator[Transaction]:
        if start is not None:
            valid_date(start)
        if end is not None:
            valid_date(end)
        if start is not None and end is not None and start > end:
            raise AppError("시작일이 종료일보다 늦습니다.", "--from을 --to 이전 날짜로 지정하세요.")
        if category is not None:
            self.require_category(category)
        if type is not None:
            valid_type(type)
        for tx in self.repository.iter_transactions():
            if start is not None and tx.date < start:
                continue
            if end is not None and tx.date > end:
                continue
            if category is not None and tx.category != category:
                continue
            if type is not None and tx.type != type:
                continue
            if q is not None and q not in tx.memo:
                continue
            if tag is not None and tag not in tx.tags:
                continue
            yield tx

    def set_budget(self, month: str, amount: str | int) -> None:
        valid_month(month)
        value = positive_int(amount)
        budgets = self.repository.budgets()
        budgets[month] = value
        self.repository.save_budgets(budgets)

    def summary(self, month: str, top: int = 3) -> MonthSummary:
        valid_month(month)
        positive_int(top)
        income = expense = count = 0
        categories: dict[str, int] = {}
        for tx in self.repository.iter_transactions():
            if not tx.date.startswith(month + "-"):
                continue
            count += 1
            if tx.type == "income":
                income += tx.amount
            else:
                expense += tx.amount
                categories[tx.category] = categories.get(tx.category, 0) + tx.amount
        ranking = sorted(categories.items(), key=lambda item: (-item[1], item[0]))[:top]
        return MonthSummary(income, expense, count, ranking, self.repository.budgets().get(month))

    def import_csv(self, path: Path) -> int:
        transactions: list[Transaction] = []
        with path.open(encoding="utf-8-sig", newline="") as source:
            reader = csv.DictReader(source, strict=True)
            try:
                header = reader.fieldnames
                if (header is None or len(header) != len(set(header))
                        or not set(CSV_COLUMNS[:4]).issubset(header)
                        or not set(header).issubset(CSV_COLUMNS)):
                    raise AppError("CSV 헤더가 올바르지 않습니다.", "필수 컬럼 date,type,category,amount와 선택 컬럼 memo,tags를 확인하세요.")
                for row in reader:
                    try:
                        if None in row or any(value is None for value in row.values()):
                            raise AppError("CSV 컬럼 개수가 헤더와 다릅니다.", "쉼표가 포함된 필드는 큰따옴표로 감싸세요.")
                        transactions.append(self.make_transaction(
                            row["date"], row["type"], row["category"], row["amount"],
                            row.get("memo", ""), row.get("tags", ""),
                        ))
                    except AppError as exc:
                        raise AppError(
                            f"CSV {reader.line_num}행: {exc} (전체 가져오기 취소)", exc.hint,
                        ) from exc
            except csv.Error as exc:
                raise AppError(
                    f"CSV {reader.line_num}행 구문 오류: {exc} (전체 가져오기 취소)",
                    "따옴표와 쉼표 구분 형식을 확인하세요.",
                ) from exc
        transactions.sort(key=lambda tx: tx.sort_key, reverse=True)
        if transactions:
            self.repository.merge_transactions(transactions)
        return len(transactions)

    def export_csv(
        self, path: Path, month: str | None = None,
        start: str | None = None, end: str | None = None,
    ) -> int:
        if month is not None:
            valid_month(month)
            if start is not None or end is not None:
                raise AppError("내보내기 기간 조건이 중복되었습니다.", "--month 또는 --from/--to 쌍 중 하나만 사용하세요.")
        elif start is None or end is None:
            raise AppError("내보내기 기간이 필요합니다.", "--month 또는 --from과 --to를 함께 지정하세요.")
        if path.resolve() in {item.resolve() for item in self.repository.storage_paths}:
            raise AppError("저장소 파일로 내보낼 수 없습니다.", "별도의 CSV 출력 경로를 지정하세요.")
        if path.exists() and any(path.samefile(item) for item in self.repository.storage_paths):
            raise AppError("출력 파일이 저장소 파일과 같습니다.", "별도의 CSV 출력 경로를 지정하세요.")
        count = 0
        with atomic_output(path) as output:
            writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS)
            writer.writeheader()
            for tx in self.search(start, end):
                if month is not None and not tx.date.startswith(month + "-"):
                    continue
                writer.writerow({
                    "date": tx.date, "type": tx.type, "category": tx.category,
                    "amount": tx.amount, "memo": tx.memo, "tags": ",".join(tx.tags),
                })
                count += 1
        return count
