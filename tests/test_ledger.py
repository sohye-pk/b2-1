import contextlib
import csv
import io
import os
from pathlib import Path
import subprocess
import sys
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

    def test_update_reorders_and_delete_preserves_other_fields(self):
        first = self.add("2026-10-01")
        second = self.add("2026-10-02")
        self.service.update(first.id, date="2026-10-03", amount="12000", memo="", tags="")
        transactions = list(self.repo.iter_transactions())
        self.assertEqual([tx.id for tx in transactions], [first.id, second.id])
        self.assertEqual(transactions[0].amount, 12000)
        self.assertEqual(transactions[0].memo, "")
        self.assertEqual(transactions[0].tags, [])
        self.assertEqual(transactions[0].category, "food")
        self.service.delete(first.id)
        self.assertEqual([tx.id for tx in self.repo.iter_transactions()], [second.id])
        original = self.repo.transactions_path.read_bytes()
        for operation in (lambda: self.service.update("missing", amount="1"),
                          lambda: self.service.delete("missing"),
                          lambda: self.service.update(second.id)):
            with self.assertRaises(AppError):
                operation()
        self.assertEqual(self.repo.transactions_path.read_bytes(), original)

    def test_search_combines_conditions_and_includes_endpoints(self):
        first = self.add("2026-10-01")
        second = self.add("2026-10-31")
        self.add("2026-09-30")
        self.add("2026-10-15", category="transport")
        results = self.service.search("2026-10-01", "2026-10-31", "food", "expense", "점", "meal")
        self.assertEqual([tx.id for tx in results], [second.id, first.id])
        self.assertEqual(list(self.service.search(tag="mea")), [])
        with self.assertRaises(AppError):
            list(self.service.search("2026-10-31", "2026-10-01"))

    def test_list_does_not_read_past_limit(self):
        self.add()
        with self.repo.transactions_path.open("a", encoding="utf-8") as output:
            output.write("broken\n")
        self.assertEqual(len(list(self.service.list_transactions(1))), 1)
        with self.assertRaises(AppError):
            list(self.service.search())

    def test_summary_budget_persistence_and_warning(self):
        self.add(amount=100000, category="salary", type="income")
        self.add(amount=12000)
        self.add(amount=8000)
        self.add(amount=5000, category="transport")
        self.add("2026-09-30", amount=99999)
        self.service.set_budget("2026-10", 20000)
        reopened = BudgetService(TransactionRepository(self.repo.data_dir))
        result = reopened.summary("2026-10", 1)
        self.assertEqual((result.income, result.expense, result.balance), (100000, 25000, 75000))
        self.assertEqual(result.top_categories, [("food", 20000)])
        self.assertEqual(result.budget, 20000)
        self.assertEqual(reopened.summary("2026-08").count, 0)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(["--data-dir", str(self.repo.data_dir), "summary", "--month", "2026-10"])
        self.assertEqual(code, 0)
        self.assertIn("125.0%", output.getvalue())
        self.assertIn("예산 초과", output.getvalue())
        for month, amount in (("2026-13", 1), ("2026-1", 1), ("2026-10", 0)):
            with self.assertRaises(AppError):
                self.service.set_budget(month, amount)

    def test_csv_round_trip_filter_and_unicode_tags(self):
        self.add("2026-10-03")
        self.add("2026-09-30")
        self.service.add("2026-10-01", "expense", "food", 123, '식사, "친구"', "meal,work")
        output = self.directory / "export.csv"
        self.assertEqual(self.service.export_csv(output, month="2026-10"), 2)
        with output.open(encoding="utf-8", newline="") as source:
            rows = list(csv.DictReader(source))
        self.assertEqual(rows[1]["memo"], '식사, "친구"')
        self.assertEqual(rows[1]["tags"], "meal,work")
        other = BudgetService(TransactionRepository(self.directory / "other"))
        self.assertEqual(other.import_csv(output), 2)
        imported = list(other.repository.iter_transactions())
        self.assertEqual(imported[1].tags, ["meal", "work"])
        self.assertEqual(imported[1].memo, '식사, "친구"')
        self.assertNotEqual(imported[1].id, list(self.repo.iter_transactions())[1].id)
        self.assertEqual(self.service.export_csv(output, start="2026-10-03", end="2026-10-03"), 1)

    def test_invalid_csv_rolls_back_entire_import(self):
        self.add()
        original = self.repo.transactions_path.read_bytes()
        source = self.directory / "bad.csv"
        header = "date,type,category,amount\n"
        good = "2026-10-03,expense,food,10\n"
        for bad in ("2026-10-03,expense,food,0\n", "2026-10-03,expense,unknown,10\n",
                    "2026-02-30,expense,food,10\n", "2026-10-03,expense,food,10,extra\n",
                    '2026-10-03,expense,food,"10\n'):
            source.write_text(header + good + bad, encoding="utf-8")
            with self.subTest(bad=bad), self.assertRaises(AppError) as error:
                self.service.import_csv(source)
            self.assertIn("행", str(error.exception))
            self.assertEqual(self.repo.transactions_path.read_bytes(), original)
        source.write_text("date,amount\n2026-10-01,10\n", encoding="utf-8")
        with self.assertRaises(AppError):
            self.service.import_csv(source)

    def test_export_guards_and_original_output_preserved(self):
        self.add()
        output = self.directory / "export.csv"
        output.write_text("original", encoding="utf-8")
        for options in ({}, {"start": "2026-10-01"},
                        {"month": "2026-10", "start": "2026-10-01"},
                        {"start": "2026-10-31", "end": "2026-10-01"}):
            with self.subTest(options=options), self.assertRaises(AppError):
                self.service.export_csv(output, **options)
            self.assertEqual(output.read_text(encoding="utf-8"), "original")
        original = self.repo.transactions_path.read_bytes()
        with self.assertRaises(AppError):
            self.service.export_csv(self.repo.transactions_path, month="2026-10")
        self.assertEqual(self.repo.transactions_path.read_bytes(), original)

    def test_help_for_all_commands(self):
        for command in ([], ["add"], ["list"], ["search"], ["update"], ["delete"],
                        ["summary"], ["budget"], ["budget", "set"], ["category"],
                        ["category", "add"], ["category", "list"], ["category", "remove"],
                        ["import"], ["export"]):
            with self.subTest(command=command), contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaises(SystemExit) as exit:
                    main(command + ["--help"])
            self.assertEqual(exit.exception.code, 0)

    def test_real_cli_interactive_restart_and_exit_codes(self):
        base = [sys.executable, "-m", "budget_app", "--data-dir", str(self.repo.data_dir)]

        def run(*args, input=None):
            return subprocess.run(base + list(args), input=input, capture_output=True,
                                  text=True, encoding="utf-8", env={
                                      **os.environ, "PYTHONIOENCODING": "utf-8",
                                  })

        added = run("add", input="2026-10-02\nexpense\nfood\n15000\n점심\nmeal,work\n")
        self.assertEqual(added.returncode, 0, added.stderr)
        self.assertIn("id=", added.stdout)
        listed = run("list")
        self.assertEqual(listed.returncode, 0)
        self.assertIn("15000", listed.stdout)
        self.assertIn("점심", listed.stdout)
        for arguments in (("delete", "--id", "missing"),
                          ("import", "--from", str(self.directory / "missing.csv"))):
            result = run(*arguments)
            self.assertEqual(result.returncode, 1)
            self.assertIn("[힌트]", result.stderr)
            self.assertNotIn("Traceback", result.stderr)
        result = run("unknown")
        self.assertEqual(result.returncode, 2)
        self.assertIn("[힌트]", result.stderr)

    def test_update_and_delete_replace_failure_preserve_original(self):
        transaction = self.add()
        original = self.repo.transactions_path.read_bytes()
        for operation in (lambda: self.service.update(transaction.id, amount="123"),
                          lambda: self.service.delete(transaction.id)):
            with patch("budget_app.repository.os.replace", side_effect=OSError("blocked")):
                with self.assertRaises(OSError):
                    operation()
            self.assertEqual(self.repo.transactions_path.read_bytes(), original)
            self.assertEqual(list(self.repo.data_dir.glob(".ledger-*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
