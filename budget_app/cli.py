"""명령 해석, 사용자 입력과 출력."""

import argparse
from pathlib import Path
from typing import Iterable

from .decorators import handle_errors
from .models import Transaction, positive_int
from .repository import TransactionRepository
from .service import BudgetService


class Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        self.exit(2, f"[오류] {message}\n[힌트] {self.prog} --help로 사용법을 확인하세요.\n")


def build_parser() -> Parser:
    parser = Parser(description="파일 기반 콘솔 가계부")
    parser.add_argument("--data-dir", type=Path, default=Path("data"), help="저장 폴더 (기본 ./data)")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("add", help="대화형 거래 추가")
    listing = commands.add_parser("list", help="최신순 거래 목록")
    listing.add_argument("--limit", default="10", help="출력 건수 (기본 10)")
    update = commands.add_parser("update", help="옵션으로 지정한 거래 필드 수정")
    update.add_argument("--id", required=True)
    for field in ("date", "type", "category", "amount", "memo", "tags"):
        update.add_argument(f"--{field}")
    delete = commands.add_parser("delete", help="ID로 거래 삭제")
    delete.add_argument("--id", required=True)
    search = commands.add_parser("search", help="모든 지정 조건을 만족하는 거래 검색")
    search.add_argument("--from", dest="start")
    search.add_argument("--to", dest="end")
    for field in ("category", "type", "q", "tag"):
        search.add_argument(f"--{field}")
    summary = commands.add_parser("summary", help="월별 요약과 예산 조회")
    summary.add_argument("--month", required=True)
    summary.add_argument("--top", default="3")
    budget = commands.add_parser("budget", help="월 예산 설정 (조회는 summary)")
    budget_actions = budget.add_subparsers(dest="action", required=True)
    setting = budget_actions.add_parser("set", help="월 예산 저장")
    setting.add_argument("--month", required=True)
    setting.add_argument("--amount", required=True)
    importing = commands.add_parser("import", help="CSV 전체 검증 후 거래 가져오기")
    importing.add_argument("--from", dest="source", type=Path, required=True)
    exporting = commands.add_parser("export", help="지정 기간 거래를 CSV로 내보내기")
    exporting.add_argument("--out", type=Path, required=True)
    exporting.add_argument("--month")
    exporting.add_argument("--from", dest="start")
    exporting.add_argument("--to", dest="end")
    category = commands.add_parser("category", help="카테고리 관리")
    actions = category.add_subparsers(dest="action", required=True)
    for action in ("add", "list", "remove"):
        actions.add_parser(action, help=f"카테고리 {action}")
    return parser


def print_transactions(transactions: Iterable[Transaction]) -> None:
    found = False
    for tx in transactions:
        found = True
        print(f"{tx.id} | {tx.date} | {tx.type} | {tx.category} | {tx.amount} | {tx.memo} | {','.join(tx.tags)}")
    if not found:
        print("데이터 없음")


@handle_errors
def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repository = TransactionRepository(args.data_dir)
    service = BudgetService(repository)
    if args.command == "add":
        print("등록 카테고리: " + ", ".join(repository.categories()))
        transaction = service.add(
            input("날짜(YYYY-MM-DD): ").strip(), input("타입(income/expense): ").strip(),
            input("카테고리: ").strip(), input("금액(양수 정수): ").strip(),
            input("메모(선택): "), input("태그(쉼표 구분, 선택): "),
        )
        print(f"[저장 완료] id={transaction.id}")
    elif args.command == "list":
        print_transactions(service.list_transactions(positive_int(args.limit)))
    elif args.command == "update":
        service.update(args.id, args.date, args.type, args.category, args.amount, args.memo, args.tags)
        print(f"[수정 완료] id={args.id}")
    elif args.command == "delete":
        service.delete(args.id)
        print(f"[삭제 완료] id={args.id}")
    elif args.command == "search":
        print_transactions(service.search(args.start, args.end, args.category, args.type, args.q, args.tag))
    elif args.command == "budget":
        service.set_budget(args.month, args.amount)
        print(f"[저장 완료] {args.month} 예산 {args.amount}원")
    elif args.command == "import":
        count = service.import_csv(args.source)
        print(f"[완료] imported={count}")
    elif args.command == "export":
        count = service.export_csv(args.out, args.month, args.start, args.end)
        print(f"[완료] {args.out} ({count} records)")
    elif args.command == "summary":
        result = service.summary(args.month, positive_int(args.top))
        if result.count == 0:
            print("데이터 없음")
        print(f"총 수입: {result.income}원\n총 지출: {result.expense}원\n잔액: {result.balance}원")
        if result.budget is not None:
            print(f"예산: {result.budget}원 (사용률 {result.expense / result.budget:.1%})")
            if result.expense > result.budget:
                print("[경고] 예산 초과")
        print(f"지출 TOP {args.top}")
        for index, (category, amount) in enumerate(result.top_categories, 1):
            print(f"{index}) {category} {amount}원")
    elif args.command == "category":
        if args.action == "list":
            for name in repository.categories():
                print(f"- {name}")
        else:
            name = input("카테고리명: ").strip()
            if args.action == "add":
                service.category_add(name)
            else:
                service.category_remove(name)
            print(f"[완료] category {args.action}: {name}")
    return 0
