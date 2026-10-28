import contextlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from budget_app.cli import main
from budget_app.models import AppError
from budget_app.repository import TransactionRepository
from budget_app.service import BudgetService


class LedgerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.repo = TransactionRepository(self.directory / "data")
        self.service = BudgetService(self.repo)

    def add(self, day="2026-10-02", amount=10000, category="food", type="expense"):
        return self.service.add(day, type, category, amount, "점심", "meal,work")

    def test_persistence_order_limit_and_categories(self):
        old = self.add("2026-10-01")
        new = self.add("2026-10-03")
        self.add("2026-10-02")
        reopened = TransactionRepository(self.repo.data_dir)
        self.assertEqual([tx.date for tx in reopened.iter_transactions()],
                         ["2026-10-03", "2026-10-02", "2026-10-01"])
        self.assertEqual([tx.id for tx in self.service.list_transactions(1)], [new.id])
        self.assertNotEqual(old.id, new.id)
        self.assertTrue(all(path.exists() for path in reopened.storage_paths))
        self.service.category_add("coffee")
        self.assertIn("coffee", TransactionRepository(self.repo.data_dir).categories())
        self.service.category_remove("coffee")
        self.assertNotIn("coffee", self.repo.categories())
        with self.assertRaises(AppError):
            self.service.category_remove("food")

    def test_invalid_input_and_error_exit(self):
        for amount in (0, -1, "1.5", "abc"):
            with self.subTest(amount=amount), self.assertRaises(AppError):
                self.add(amount=amount)
        for day in ("2026-02-30", "2026-1-01"):
            with self.subTest(day=day), self.assertRaises(AppError):
                self.add(day=day)
        with self.assertRaises(AppError):
            self.add(category="missing")
        with self.assertRaises(AppError):
            self.add(type="other")
        error = io.StringIO()
        with contextlib.redirect_stderr(error):
            result = main(["--data-dir", str(self.repo.data_dir), "list", "--limit", "0"])
        self.assertEqual(result, 1)
        self.assertIn("[힌트]", error.getvalue())
        self.assertNotIn("Traceback", error.getvalue())

    def test_failed_replace_keeps_original_and_cleans_temp(self):
        self.add()
        original = self.repo.transactions_path.read_bytes()
        with patch("budget_app.repository.os.replace", side_effect=OSError("blocked")):
            with self.assertRaises(OSError):
                self.add("2026-10-03")
        self.assertEqual(self.repo.transactions_path.read_bytes(), original)
        self.assertEqual(list(self.repo.data_dir.glob(".ledger-*.tmp")), [])

    def test_corrupt_file_not_overwritten(self):
        self.repo.transactions_path.write_text('{broken}\n', encoding="utf-8")
        with self.assertRaises(AppError):
            self.add()
        self.assertEqual(self.repo.transactions_path.read_text(encoding="utf-8"), '{broken}\n')


if __name__ == "__main__":
    unittest.main()
