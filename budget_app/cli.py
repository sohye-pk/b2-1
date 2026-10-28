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
