# 파일 기반 콘솔 가계부

## 미션 소개

Python으로 거래를 기록하고 검색·집계할 수 있는 콘솔 가계부를 만드는 프로젝트입니다. 기능 구현과 함께 파일 기반 영구 저장, 예외 상황에서의 데이터 보호, 유지보수 가능한 구조를 연습합니다.

## 요구사항과 구현 방향

| 요구사항 | 구현 내용 |
| --- | --- |
| 거래 추가·조회·검색·수정·삭제 | 대화형 추가, 옵션 기반 조회·검색·수정·삭제 |
| 월별 요약·카테고리별 지출 TOP N | 월별 수입·지출·잔액과 카테고리 합계 |
| 카테고리 관리·월 예산 | 사용 중 카테고리 삭제 방지, 예산 사용률·초과 경고 |
| CSV 가져오기·내보내기 | 고정 스키마, 검증 실패 시 전체 가져오기 취소 |
| 3개 이상 파일에 영구 저장 | 거래·카테고리·예산 JSONL 파일 분리 |
| 제너레이터 스트리밍 | 거래를 한 건씩 읽고 최신순 조회·검색 |
| 공통 기능 데코레이터 | 오류 안내와 종료 코드 처리 분리 |
| 클래스·모듈 분리와 타입 힌트 | 모델·저장소·서비스·CLI 책임 분리 |
| 표준 라이브러리만 사용 | Python 3.10 이상, 추가 패키지 설치 없음 |

## 작업 내용

1. `Transaction` 데이터클래스로 거래 필드와 타입을 정의하고 날짜·금액·타입을 검증했습니다. ID는 UUID를 사용합니다.
2. `TransactionRepository`에서 거래·카테고리·예산 파일을 관리하도록 분리했습니다. 거래 파일을 날짜 내림차순으로 유지해 조회 시 전체 정렬이 필요 없도록 했습니다.
3. `BudgetService`에 거래 CRUD, 조건 검색, 카테고리 삭제 제한, 월별 집계, 예산, CSV 입출력을 구현했습니다.
4. `iter_transactions()`와 `search()`를 제너레이터로 구현하고, 목록은 `islice()`로 지정 건수까지만 읽도록 했습니다.
5. 파일 변경은 임시 파일을 완성한 뒤 원본을 교체하도록 했습니다. CSV는 전체 행 검증에 성공했을 때만 반영합니다.
6. `handle_errors` 데코레이터를 CLI 진입점에 적용해 공통 오류 메시지·해결 힌트·종료 코드를 처리했습니다. 함수 인자와 반환값에 타입 힌트를 적용했습니다.
7. 표준 `unittest`로 실제 명령 실행, 저장 유지, 집계, CSV 왕복, 잘못된 입력, 파일 교체 실패를 검증했습니다.

기능은 필수 범위로 한정했습니다. 파일 잠금, 백업 명령, 반복 거래, 별도 화면 꾸미기는 추가하지 않았습니다.

## 실행

macOS 터미널에서 프로젝트 폴더로 이동한 뒤 실행합니다.

```sh
python3 --version
python3 -m budget_app --help
python3 -m budget_app add
python3 -m budget_app list --limit 10
```

모든 명령과 하위 명령은 `--help`를 지원합니다. 옵션은 `--`로 통일합니다. `--data-dir`는 명령 **앞에** 지정합니다.

```sh
python3 -m budget_app --data-dir ./demo-data list
```

## 저장 파일

기본 위치는 실행한 디렉터리의 `./data`입니다. 처음 실행하면 다음 세 파일을 자동 생성합니다. 한 줄에 JSON 객체 하나를 저장하는 UTF-8 JSONL 형식입니다.

| 파일 | 내용 |
| --- | --- |
| `transactions.jsonl` | id, type, date, amount, category, memo, tags |
| `categories.jsonl` | name |
| `budgets.jsonl` | month, amount |

카테고리 파일이 비어 있으면 `food`, `transport`, `rent`, `salary`, `etc`를 생성합니다. 금액은 양수 정수이며, 날짜는 `YYYY-MM-DD`, 월은 `YYYY-MM`입니다. 거래 ID는 UUID로 생성합니다.

거래 파일은 날짜 내림차순으로 유지하며 같은 날짜는 ID 내림차순입니다. 목록과 검색은 파일을 한 건씩 읽습니다. 쓰기는 같은 폴더의 임시 파일을 완성하고 닫은 다음 `os.replace()`로 교체합니다. 이 프로그램은 한 번에 한 프로세스로 사용합니다. 동시 쓰기 잠금은 구현하지 않습니다.

## 명령 예시

### 거래 추가·목록·수정·삭제

```sh
python3 -m budget_app add
python3 -m budget_app list --limit 3
python3 -m budget_app update --id 거래ID --amount 12000 --memo "점심 수정"
python3 -m budget_app update --id 거래ID --date 2026-10-15 --tags "meal,work"
python3 -m budget_app delete --id 거래ID
```

`add`는 날짜, 타입(`income`/`expense`), 등록된 카테고리, 금액, 메모, 쉼표로 구분한 태그를 순서대로 입력합니다. 입력이 잘못되면 오류와 힌트를 출력하고 종료하므로 다시 실행합니다. 성공하면 생성한 ID를 출력합니다.

`list`의 기본 제한은 10건입니다. **update는 옵션 방식**으로 고정하며 지정하지 않은 필드는 유지합니다. `--memo ""`, `--tags ""`로 값을 비울 수 있습니다. 없는 ID는 오류로 처리합니다.

### 검색

```sh
python3 -m budget_app search --from 2026-10-01 --to 2026-10-31
python3 -m budget_app search --category food --type expense --q 점심 --tag meal
```

기간 양끝을 포함합니다. 여러 조건은 AND로 결합하며 결과는 최신순입니다. 메모는 부분 일치, 태그는 개별 태그 일치입니다. 기간의 한쪽만 지정할 수도 있습니다.

### 카테고리

```sh
python3 -m budget_app category list
python3 -m budget_app category add
python3 -m budget_app category remove
```

추가·삭제할 이름은 대화형으로 입력합니다. 중복 이름, 없는 이름, 사용 중인 카테고리의 삭제는 오류로 처리합니다.

### 월별 요약·예산

```sh
python3 -m budget_app budget set --month 2026-10 --amount 500000
python3 -m budget_app summary --month 2026-10 --top 3
```

요약은 총수입, 총지출, 잔액, 카테고리별 지출 TOP N(기본 3)을 출력합니다. 거래가 없으면 `데이터 없음`을 출력합니다. 예산이 있으면 예산과 사용률을 출력하며, 지출이 예산보다 클 때 초과 경고를 표시합니다. 예산 조회는 `summary`에서 합니다.

### CSV 가져오기·내보내기

```sh
python3 -m budget_app import --from import.csv
python3 -m budget_app export --out export.csv --month 2026-10
python3 -m budget_app export --out export.csv --from 2026-10-01 --to 2026-10-15
```

내보내기는 월 또는 시작일·종료일 쌍 중 하나를 필수로 지정합니다. 두 방식을 함께 지정하면 오류입니다. 기존 출력 파일은 성공 시 교체합니다. 저장소 파일을 출력 대상으로 지정할 수 없습니다.

CSV는 UTF-8, 헤더 포함이며 다음 스키마를 사용합니다. 내보내기는 항상 아래 여섯 컬럼을 출력하며, 가져오기는 선택 컬럼 생략을 허용합니다.

| 컬럼 | 필수 | 값 |
| --- | --- | --- |
| date | Y | YYYY-MM-DD |
| type | Y | income 또는 expense |
| category | Y | 등록된 카테고리 |
| amount | Y | 양수 정수 |
| memo | N | 문자열, 기본 빈 문자열 |
| tags | N | 쉼표로 구분한 태그, 기본 빈 목록 |

```csv
date,type,category,amount,memo,tags
2026-10-01,income,salary,3000000,급여,
2026-10-02,expense,food,10000,점심,"meal,work"
```

가져온 행마다 새 ID를 생성합니다. 같은 CSV를 다시 가져오면 중복 거래가 추가됩니다. 일부 행이 잘못되면 행 번호·원인·힌트를 표시하고 **전체 가져오기를 취소**합니다. 기존 데이터는 유지됩니다. CSV 데이터를 검증하고 정렬하는 동안 가져올 거래는 메모리에 보관하며, 기존 저장 거래는 스트리밍으로 병합합니다. 성공하면 처리 건수를 출력합니다.

## 오류와 종료 코드

정상 종료는 0, 입력·파일 오류는 1입니다. 잘못된 명령이나 옵션은 2입니다. 스택트레이스 대신 원인과 해결 힌트를 출력합니다. macOS에서는 오류 명령 바로 다음에 종료 코드를 확인합니다.

```sh
python3 -m budget_app delete --id missing
echo $?
```

손상된 저장 파일은 파일명과 행 번호를 안내하고 중단합니다. 자동으로 버리거나 초기화하지 않습니다.

## 코드 구조

| 모듈 | 책임 |
| --- | --- |
| `__main__.py` | 실행 진입점과 종료 코드 |
| `cli.py` | argparse, input, 화면 출력 |
| `models.py` | 거래 dataclass, 값 검증, 사용자 오류 |
| `repository.py` | JSONL 읽기·쓰기, 초기화, 정렬 병합 |
| `service.py` | 거래·카테고리·예산 규칙, 검색·집계, CSV 처리 |
| `decorators.py` | 오류 메시지와 종료 코드를 공통 처리 |

기능 범위는 과제 필수 항목입니다. 백업, 반복 거래, 외부 라이브러리는 추가하지 않습니다. 전체 파일 검색과 거래 변경은 O(n)이며, 대량 CSV는 메모리를 사용합니다.

## 검증

```sh
python3 -m unittest discover -s tests -v
```

테스트는 임시 폴더를 사용해 실제 데이터에 영향을 주지 않습니다. 저장 순서, 재실행 후 유지, 요약, CSV 실패 시 원본 보존, 파일 교체 실패, 오류 종료 코드를 확인합니다.

개발 환경인 Windows / Python 3.10.1에서 14개 테스트가 통과했습니다. macOS 전용 실행 확인은 아직 하지 않았으며, iMac에서도 위 `python3` 명령으로 테스트할 수 있습니다.
