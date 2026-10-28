"""JSONL 저장과 원자적 파일 교체. 거래는 (날짜, ID) 내림차순."""

from contextlib import contextmanager
from dataclasses import asdict
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Iterable, Iterator, TextIO

from .models import AppError, Transaction, positive_int, valid_month


@contextmanager
def atomic_output(path: Path) -> Iterator[TextIO]:
    """같은 폴더에 쓰고 닫은 후 교체한다. 실패하면 임시 파일만 제거한다."""
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="", dir=path.parent,
            prefix=".ledger-", suffix=".tmp", delete=False,
        ) as output:
            temp_path = Path(output.name)
            yield output
            output.flush()
            os.fsync(output.fileno())
        os.replace(temp_path, path)
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


class TransactionRepository:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.transactions_path = data_dir / "transactions.jsonl"
        self.categories_path = data_dir / "categories.jsonl"
        self.budgets_path = data_dir / "budgets.jsonl"
        data_dir.mkdir(parents=True, exist_ok=True)
        for path in self.storage_paths:
            path.touch(exist_ok=True)
        if not self.categories():
            self.save_categories(["food", "transport", "rent", "salary", "etc"])

    @property
    def storage_paths(self) -> tuple[Path, Path, Path]:
        return self.transactions_path, self.categories_path, self.budgets_path

    def records(self, path: Path) -> Iterator[tuple[int, dict[str, Any]]]:
        with path.open(encoding="utf-8") as source:
            for line_number, line in enumerate(source, 1):
                try:
                    record = json.loads(line)
                    if not isinstance(record, dict):
                        raise ValueError("JSON 객체가 아닙니다")
                except (ValueError, TypeError) as exc:
                    raise self.corrupt(path, line_number) from exc
                yield line_number, record

    @staticmethod
    def corrupt(path: Path, line_number: int) -> AppError:
        return AppError(f"저장 파일 오류: {path} ({line_number}행)", "해당 행의 JSON 형식과 필드를 확인하세요. 원본을 자동 삭제하지 않습니다.")

    def write_records(self, path: Path, records: Iterable[dict[str, Any]]) -> None:
        with atomic_output(path) as output:
            for record in records:
                output.write(json.dumps(record, ensure_ascii=False) + "\n")

    def iter_transactions(self) -> Iterator[Transaction]:
        previous: tuple[str, str] | None = None
        for number, record in self.records(self.transactions_path):
            try:
                transaction = Transaction.from_record(record)
                if previous is not None and transaction.sort_key >= previous:
                    raise ValueError("정렬 순서 또는 ID 중복 오류")
            except (AppError, ValueError, TypeError, KeyError) as exc:
                raise self.corrupt(self.transactions_path, number) from exc
            previous = transaction.sort_key
            yield transaction

    def merge_transactions(
        self, incoming: Iterable[Transaction], remove_id: str | None = None,
    ) -> None:
        """정렬된 새 거래와 기존 스트림을 병합한다. 수정·삭제 ID는 제외한다."""
        def merged() -> Iterator[dict[str, Any]]:
            additions = iter(incoming)
            candidate = next(additions, None)
            for current in self.iter_transactions():
                if current.id == remove_id:
                    continue
                while candidate is not None and candidate.sort_key > current.sort_key:
                    yield asdict(candidate)
                    candidate = next(additions, None)
                yield asdict(current)
            while candidate is not None:
                yield asdict(candidate)
                candidate = next(additions, None)

        self.write_records(self.transactions_path, merged())

    def categories(self) -> list[str]:
        result: list[str] = []
        for number, record in self.records(self.categories_path):
            name = record.get("name")
            if not isinstance(name, str) or not name.strip() or name in result:
                raise self.corrupt(self.categories_path, number)
            result.append(name)
        return result

    def save_categories(self, categories: list[str]) -> None:
        self.write_records(self.categories_path, ({"name": name} for name in categories))

    def budgets(self) -> dict[str, int]:
        result: dict[str, int] = {}
        for number, record in self.records(self.budgets_path):
            try:
                month, amount = record["month"], record["amount"]
                valid_month(month)
                if type(amount) is not int or month in result:
                    raise ValueError("잘못된 예산")
                result[month] = positive_int(amount)
            except (AppError, TypeError, ValueError, KeyError) as exc:
                raise self.corrupt(self.budgets_path, number) from exc
        return result

    def save_budgets(self, budgets: dict[str, int]) -> None:
        self.write_records(self.budgets_path, (
            {"month": month, "amount": amount} for month, amount in sorted(budgets.items())
        ))
