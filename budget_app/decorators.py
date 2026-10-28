"""CLI의 공통 오류 처리."""

from functools import wraps
import sys
from typing import Callable, ParamSpec

from .models import AppError

P = ParamSpec("P")


def handle_errors(function: Callable[P, int]) -> Callable[P, int]:
    @wraps(function)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> int:
        try:
            return function(*args, **kwargs)
        except AppError as exc:
            message, hint = str(exc), exc.hint
        except (OSError, UnicodeError) as exc:
            message = f"파일을 처리할 수 없습니다: {exc}"
            hint = "파일 경로, 접근 권한, UTF-8 인코딩을 확인하세요."
        except (EOFError, KeyboardInterrupt):
            message, hint = "입력이 취소되었습니다.", "명령을 다시 실행해 입력을 완료하세요."
        print(f"[오류] {message}\n[힌트] {hint}", file=sys.stderr)
        return 1
    return wrapper
