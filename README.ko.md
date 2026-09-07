![RepoAtlas — 작업에 필요한 코드만 연결해 보여주는 작은 저장소 지도](docs/assets/repoatlas-hero.png)

# RepoAtlas

[English](README.md) · [한국어](README.ko.md) · [v0.5.0 다운로드](https://github.com/ch4570/repo-graph/releases/tag/v0.5.0)

[![테스트](https://github.com/ch4570/repo-graph/actions/workflows/distribution.yml/badge.svg)](https://github.com/ch4570/repo-graph/actions/workflows/distribution.yml)

**코드를 찾고, 필요한 맥락만 가져갑니다.**

RepoAtlas는 저장소를 로컬 코드 그래프로 색인합니다. 코딩 에이전트가 작은 지도에서 시작해 관련 심볼과 검증된 소스로 범위를 좁힙니다. 진입점을 찾고, 의존성을 따라가고, 작업에 필요한 코드만 읽는 도구입니다.

**로컬 색인 · 66개 언어 감지 프로필 · 그래프 형식 4종 · CLI + 선택형 MCP · MIT**

색인에 LLM이나 API 키가 필요하지 않으며 대상 프로젝트를 빌드하거나 실행하지 않습니다. 언어 감지와 분석 정확도는 다릅니다. Python·Java·Kotlin은 AST, 43개 프로필은 선언 추출 휴리스틱을 사용하며, 나머지 UTF-8 텍스트도 파일 단위로 검색합니다. [지원 범위와 한계](docs/languages.md).

[빠른 시작](#빠른-시작) · [에이전트 사용](#에이전트가-필요한-맥락만-읽게-하기) · [그래프](#원하는-그래프-만들기) · [관측](#응답-크기와-실제-작업을-함께-관측하기) · [문서](#문서)

## 빠른 시작

**현재 비공개 프리뷰입니다.** 저장소 접근 권한이 필요합니다. 로그인된 GitHub CLI로 wheel을 내려받거나 [릴리스 페이지](https://github.com/ch4570/repo-graph/releases/tag/v0.5.0)에서 다운로드하세요. 설치 후 탐색할 프로젝트 디렉터리에서 실행합니다. **Python 3.11 이상**이 필요하며, 프로젝트 언어는 상관없습니다.

```sh
gh release download v0.5.0 --repo ch4570/repo-graph --pattern 'repoatlas-0.5.0-py3-none-any.whl'
uv tool install ./repoatlas-0.5.0-py3-none-any.whl
repoatlas explore
repoatlas explore checkout
```

`explore`는 작은 지도를, `explore checkout`은 관련 소스를 읽기 쉬운 텍스트로 보여줍니다. 기본 상한은 2,000 추정 토큰이며 색인은 자동으로 만들고 갱신합니다. `checkout`을 프로젝트의 이름이나 키워드로 바꾸세요. 다른 디렉터리에서는 `--repo /path/to/project`를 붙입니다. `repoatlas`만 실행하면 짧은 사용 가이드가 나옵니다.

**pipx를 쓴다면** 설치 명령의 `uv tool install`을 `pipx install`로 바꾸세요. RepoAtlas를 clone하거나 대상 프로젝트에 Python 의존성을 추가할 필요가 없습니다. 명령을 찾지 못하면 설치 도구가 안내한 PATH 설정을 적용하세요. uv는 `uv tool update-shell`을 제공합니다.

<details>
<summary>Python만 설치되어 있다면</summary>

로그인한 [릴리스 페이지](https://github.com/ch4570/repo-graph/releases/tag/v0.5.0)에서 `get-repoatlas.py`, wheel, `SHA256SUMS.txt`를 내려받고 실행합니다.

```sh
python3 get-repoatlas.py --wheel ./repoatlas-0.5.0-py3-none-any.whl --checksum-file ./SHA256SUMS.txt
```

Windows에서는 `python3`를 `py -3`로 바꾸세요. 설치기가 wheel 체크섬을 확인하고 사용자 전용 환경을 만든 뒤 명령 위치와 필요한 PATH 설정을 안내합니다. 다른 프로그램의 설치나 셸 설정 파일은 보존합니다. 최초 설치에는 인터넷이 필요하며, [오프라인·고급 설치](INSTALL.md)도 지원합니다.

</details>

소스 checkout에서는 `uv tool install .`을 사용할 수 있습니다. [릴리스 페이지](https://github.com/ch4570/repo-graph/releases/tag/v0.5.0)에 wheel·소스 ZIP·체크섬을 제공합니다. 공개 배포 경로는 GitHub Releases이며, PyPI 설치를 전제하지 않습니다.

## 질문에 맞는 명령 고르기

| 하고 싶은 일 | 명령 |
| --- | --- |
| 처음 보는 저장소 파악하기 | `repoatlas explore` |
| 기능 위치와 정확한 심볼 ID 찾기 | `repoatlas search checkout --format text --limit 5` |
| 코드를 읽기 전에 선언 확인하기 | `repoatlas context checkout --mode signatures --format text` |
| 필요한 코드를 제한된 크기로 받기 | `repoatlas explore checkout` |
| 호출·임포트·상속 관계 따라가기 | `repoatlas neighbors EXACT_SYMBOL_ID --kinds calls imports inherits --format text` |
| 들어오는 호출과 상속 살펴보기 | `repoatlas impact EXACT_SYMBOL_ID --format text` |
| 의존성 그래프를 문서에 넣기 | `repoatlas graph --level file --format mermaid --output dependencies.mmd` |

대상 저장소 안에서 실행하거나 `--repo /absolute/path/to/project`를 붙입니다. `EXACT_SYMBOL_ID`에는 `search` 결과의 ID를 사용하세요. `impact`는 제한된 그래프 탐색이며 모든 런타임 영향을 증명하지는 않습니다.

## 에이전트가 필요한 맥락만 읽게 하기

**질문에 답할 수 있는 가장 작은 조회부터 시작합니다.** 이름이나 파일을 알면 짧게 검색하거나 필요한 소스 범위를 바로 읽습니다. 구조를 모를 때만 작은 지도를 보고, 선언·관계는 필요할 때 조회합니다. 근거가 충분하면 탐색을 멈춥니다. 자동화용 기본 출력은 JSON이며, `--format text`를 쓰면 에이전트 대화에서 읽기 쉬운 짧은 결과를 받습니다.

```sh
repoatlas init
repoatlas explore checkout --session checkout
repoatlas explore calculateTotal --session checkout
repoatlas stats checkout
```

`init`은 현재 프로젝트에 스킬을 설치합니다. `--session checkout`은 `.repoatlas/sessions/checkout/` 아래 receipt와 telemetry 경로를 자동으로 선택합니다. 다음 소스 조회는 앞서 전달한 범위를 제외하고 읽지 않은 부분을 이어 받습니다. `stats`에서 조회 횟수, 응답 크기, 소스 바이트를 확인합니다.

새 작업이나 이전 출력을 받지 못한 에이전트에는 새 세션 이름을 쓰세요. Receipt는 사라진 모델 컨텍스트를 복구하지 않습니다. 세션은 소스를 가져오는 조회에만 쓰며 지도·선언만 조회할 때는 사용하지 않습니다. 기록은 로컬에만 남고 telemetry에는 원문이나 질문을 넣지 않습니다. 프로젝트의 ignore 규칙에 `.repoatlas/`를 추가하세요. 파일 경로를 직접 지정하는 기존 `context --receipt PATH --telemetry PATH`도 지원합니다.

설치 후 에이전트에 이렇게 요청할 수 있습니다.

```text
.agents/skills/repoatlas-jvm/SKILL.md를 읽어줘. 이름이나 파일을 알면
짧게 검색하거나 필요한 소스 범위를 바로 읽고, 구조를 모를 때만
2,000 추정 토큰 이내의 map을 사용해줘. 선언과 관계는 필요할 때
조회하고 근거가 충분하면 탐색을 멈춰줘. 이번 작업의 snippet 조회에
receipt 하나를 재사용하고 조회 메타데이터를 로컬에 기록해줘.
수정 전에 소스를 확인하고, 수정 후 관련 테스트와 sync를 실행해줘.
```

스킬 경로 `repoatlas-jvm`과 캐시 파일명 `jvm-v2.sqlite`는 기존 설치와의 호환성을 위해 유지합니다. 분석 언어를 제한하는 이름은 아닙니다. [에이전트 사용법·receipt·MCP](docs/agents.md).

## 원하는 그래프 만들기

| 형식 | 용도 |
| --- | --- |
| JSON | 스크립트와 도구에서 그래프 데이터 사용 |
| Mermaid | 문서에 넣을 편집 가능한 다이어그램 |
| GraphML | 외부 그래프 도구로 가져오기 |
| HTML | 오프라인에서 그래프 탐색 |

```sh
repoatlas graph --repo /absolute/path/to/project --format html --output graph.html
repoatlas graph --repo /absolute/path/to/project --format mermaid --level file \
  --kinds imports calls --output dependencies.mmd
repoatlas graph --repo /absolute/path/to/project --format graphml \
  --language typescript --path 'src/*' --output frontend.graphml
```

언어·경로·관계·방향·중심 심볼을 기준으로 범위를 고릅니다. 그래프에 관계 신뢰도와 잘림 여부를 표시하며, 미지원 언어도 파일 노드로 남습니다. 기존 출력 파일은 덮어쓰지 않습니다. [그래프 옵션과 예제](docs/usage.ko.md#그래프-내보내기).

## 응답 크기와 실제 작업을 함께 관측하기

**응답 크기가 줄어드는 것은 확인했습니다. 모델 전체 토큰은 질문과 탐색 방식에 따라 달라집니다.** 유리한 결과와 불리한 결과를 모두 담았습니다.

### CLI에서 줄어든 양

0.4.0 엔진과 번들의 혼합 언어 예제로 측정했습니다. 모델을 호출하지 않은 결과입니다.

| 비교 | 이전 | 이후 | 변화 |
| --- | ---: | ---: | ---: |
| 같은 지도 항목 28개: JSON → text | 6,639바이트 | 3,535바이트 | **응답 46.8% 감소** |
| 같은 context 세 번: receipt 없음 → 사용 | 9,633바이트 | 4,483바이트 | **전체 응답 53.5% 감소** |
| Receipt의 1 → 2 → 3차 소스 본문 | 1,429바이트 | 188 → 0바이트 | 읽지 않은 범위를 이어 읽고 재전송 종료 |

텍스트는 같은 지도 항목과 탐색 근거를 보존하지만 JSON의 모든 메타데이터까지 담지는 않습니다. Receipt의 후속 조회는 일반 반복 조회가 놓친 다른 범위를 보여줄 수 있습니다. 소스를 모두 전달한 뒤에도 상태 메타데이터는 반환합니다. [정확한 측정값과 파일 해시](evals/exploration/results/2026-09-07/delivery.json).

### 실제 Codex 탐색에서 쓴 토큰

동일한 실제 소스 스냅샷에서 질문 세 개를 고정하고, 일반적인 `rg`·부분 읽기와 RepoAtlas를 함께 쓰는 탐색을 비교했습니다. 질문·조건별로 한 번씩, 총 6회입니다. Codex CLI 0.153.4에서 `gpt-5.6-sol`, effort `xhigh`를 요청했고 같은 스킬 목록을 사용했습니다. RepoAtlas에는 미리 만든 색인을 제공했으며 생성 시간 1.105초는 별도 측정했습니다. 화살표는 **일반 탐색 → RepoAtlas 탐색**입니다.

| 질문 | 인용 검사 | 누적 입력 토큰 | 입력 변화 | 명령 수 | 명령 출력 바이트 |
| --- | --- | ---: | ---: | ---: | ---: |
| 그래프 export 보호 | 통과 → 통과 | 79,358 → 106,334 | **+34.0%** | 4 → 7 | 49,750 → 66,502 |
| 설정 변경과 재색인 | 실패 → 통과 | 157,482 → 138,864 | −11.8% | 10 → 8 | 81,885 → 43,542 |
| 관리 스킬 설치 충돌 | 실패 → 통과 | 70,775 → 88,411 | **+24.9%** | 4 → 3 | 23,514 → 11,993 |

일반 탐색의 두 인용 실패는 연속된 원문 대신 생략 부호를 썼기 때문입니다. 이를 곧바로 코드 이해 실패로 해석하지 않으며, 두 쌍은 동일 품질에서의 절감 비교에 쓰지 않습니다. **양쪽 인용 검사를 통과한 한 쌍에서는 입력이 34.0% 늘었습니다. 일반적인 모델 토큰 절감은 입증하지 못했습니다.** 설치 충돌 사례는 명령 출력이 49.0% 줄었는데도 입력은 늘어, 응답 크기만으로 판단할 수 없음을 보여줍니다.

실제 사용량은 런타임에서 읽었습니다. 캐시된 입력은 이미 입력 토큰에 포함되므로 다시 더하지 않습니다. 시작 지침, 도구 왕복, 반복 문맥, 추론과 캐시 동작이 전체 사용량에 영향을 줍니다. 요금 절감이나 보편적인 정확도 향상을 주장하지 않습니다. 작은 저장소의 읽기 질문 세 개라 대형 저장소나 구현 작업으로 일반화할 수도 없습니다. 초기 빈 색인 문제로 제외한 5회와 유효한 6회 모두 보존했습니다. [프롬프트·답변·사용량·판정 기록](evals/exploration/results/2026-09-07/controlled.json).

### 관측을 실제 사용에 반영하기

위치를 알면 짧은 검색이나 직접 읽기부터 시작하고, 구조를 모를 때 작은 지도를 봅니다. 관계가 필요할 때만 그래프를 따라가고, 긴 자연어 검색을 반복하지 않습니다. 작업별로 receipt 하나를 쓰되 근거가 충분하면 조회를 마칩니다. 이 원칙을 `explore`와 세션 기능에 반영했습니다. **0.5.0의 편의 기능은 기능 테스트로 검증했으며 새로운 모델 토큰 비교 결과는 아닙니다.**

소스 checkout에서 CLI 측정을 재현하려면 다음을 실행합니다.

```sh
python scripts/observe_delivery.py
```

[상세 관측 방법](docs/token-efficiency.md) · [에이전트 실험 하네스](evals/exploration/README.md) · [검증 기록](VALIDATION.md)

## 동작 구조

먼저 색인 가능한 파일을 찾고 언어를 감지합니다. AST·휴리스틱 분석기가 소스 근거가 있는 사실을 SQLite 그래프와 전체 텍스트 검색 색인에 저장합니다. 조회기는 예산 안에서 선언이나 해시를 검증한 소스 범위를 선택하고, 그래프 출력과 MCP도 같은 색인을 사용합니다.

색인과 선택형 receipt·telemetry 파일은 로컬에 둡니다. 에이전트가 읽는 소스는 신뢰할 수 없는 저장소 데이터로 취급해야 합니다. [아키텍처와 데이터 경계](docs/architecture.md).

## 문서

| 문서 | 내용 |
| --- | --- |
| [설치](INSTALL.md) | Wheel·ZIP·오프라인 설치, 업데이트, 문제 해결 |
| [한국어 사용법](docs/usage.ko.md) · [English usage](docs/usage.md) | 조회·필터·출력 형식·예산·최신성 |
| [에이전트 연동](docs/agents.md) | 스킬 설치, 단계별 탐색, receipt, telemetry, MCP |
| [언어 지원](docs/languages.md) | AST·heuristic·text 계약과 사용자 언어 설정 |
| [아키텍처](docs/architecture.md) | 코드 위치, 색인 수명 주기, 로컬 데이터 |
| [토큰 관측](docs/token-efficiency.md) | 재현 방법과 측정값 해석 |
| [기여 안내](CONTRIBUTING.md) | 개발 환경, 테스트, 변경 기준 |
| [변경 기록](CHANGELOG.md) | 소스와 번들의 변경 사항 |

질문과 버그는 [지원 안내](SUPPORT.md), 보안 문제는 [보안 정책](SECURITY.md)을 확인하세요. 코드와 문서는 [MIT 라이선스](LICENSE)를 따릅니다.
