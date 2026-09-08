![나침반을 든 탐험가 콜럼버스가 코드 지도를 살펴보는 모습](docs/assets/columbus-hero.png)

# Columbus · 콜럼버스

**코드의 지도를 펼치고, 필요한 맥락만 가져옵니다.**

[English](README.md) · [1.1.0 다운로드](https://github.com/ch4570/columbus/releases/tag/v1.1.0) · [벤치마크](docs/benchmarks/README.md) · [설치](INSTALL.md) · [검증 기록](VALIDATION.md)

[실제 spring-core 검증: 탐색 결함 3개 수정, 색인 비용과 미해결 그래프 한계.](evals/spring-core/README.md)

Columbus는 코딩 에이전트가 저장소를 탐색하는 로컬 코드 지도입니다. 진입점을 찾고, 관계를 따라가고, 현재 소스에서 확인한 코드만 제한된 크기로 읽습니다. 나침반과 지도를 든 탐험가 캐릭터를 담았으며, 탐색 근거는 실제 코드에서 가져옵니다.

**66개 언어 감지 프로필 · 증분 SQLite 색인 · 그래프 형식 4종 · CLI·스킬·선택형 MCP · MIT**

색인에 LLM이나 API 키가 필요하지 않으며 대상 프로젝트를 빌드하거나 실행하지 않습니다. Python·Java·Kotlin은 AST, 43개 프로필은 선언 추출 휴리스틱을 사용합니다. 나머지 UTF-8 텍스트도 파일 단위로 검색합니다. 언어 감지와 분석 정확도는 다릅니다. [지원 범위](docs/languages.md).

Columbus 1.1에는 부모 관계를 보존하는 AST JSONL 트리(`columbus tree --label NAME`), 다른 레포에 설치하는 에이전트 스킬, pre-commit 갱신 기능이 포함되어 있습니다. [AST 처리·레포 설치·훅 사용법](docs/portable-ast-workflow.md).

gzip/XZ 압축 그래프를 Git에 보관하고 원본 소스·SQLite 없이 저장된 관계를 조회할 수 있습니다. 같은 소스 체크아웃이 있으면 그래프의 해시를 검증해 필요한 선언 본문도 제한된 크기로 읽습니다. [레포에 그래프 보관하기](docs/portable-graph-workflow.md).

일반 배포는 upstream Java 문법 `0.23.5`를 사용합니다. 애너테이션 파싱을 수정한 실험용 후보 `0.23.5+columbus.1`은 별도입니다. [릴리스 범위와 호환성](docs/releases/1.1.0.md).

## 세 명령으로 출발하기

**Python 3.11 이상**과 [uv](https://docs.astral.sh/uv/getting-started/installation/)가 필요합니다. 설치한 뒤 탐색할 프로젝트 디렉터리에서 실행하세요.

```sh
uv tool install https://github.com/ch4570/columbus/releases/download/v1.1.0/columbus-1.1.0-py3-none-any.whl
columbus explore
columbus explore checkout
```

`explore`는 작은 저장소 지도를, `explore checkout`은 관련 소스를 보여줍니다. 기본 상한은 2,000 추정 토큰이며 색인은 자동으로 만들고 갱신합니다. `checkout`을 프로젝트의 이름이나 키워드로 바꾸세요. 다른 디렉터리에서는 `--repo /path/to/project`를 붙입니다. `columbus`만 실행하면 짧은 가이드가 나옵니다.

**pipx를 쓴다면** 설치 명령의 `uv tool install`을 `pipx install`로 바꾸세요. 명령을 찾지 못하면 설치 도구의 PATH 안내를 적용합니다. uv는 `uv tool update-shell`, pipx는 `pipx ensurepath`를 제공합니다. 배포 경로는 버전을 고정한 GitHub wheel이며, 동명의 PyPI 패키지 설치를 전제하지 않습니다.

<details>
<summary>Python만 설치되어 있다면</summary>

설치기를 파일로 내려받고 실행합니다.

```sh
curl -fL https://github.com/ch4570/columbus/releases/download/v1.1.0/get-columbus.py -o get-columbus.py
python3 get-columbus.py
```

Windows에서는 [get-columbus.py](https://github.com/ch4570/columbus/releases/download/v1.1.0/get-columbus.py)를 내려받아 `py -3 get-columbus.py`로 실행하세요. 설치기가 wheel 체크섬을 확인하고 사용자 전용 환경을 만든 뒤 명령 위치를 안내합니다. 다른 프로그램의 설치와 셸 설정 파일은 보존합니다. [오프라인 설치·문제 해결](INSTALL.md).

</details>

RepoAtlas 프리뷰를 사용했다면 명령·스킬·설정 이름과 캐시 경로가 바뀝니다. [이전 방법](INSTALL.md#moving-from-the-repoatlas-preview)을 확인하세요.

## 질문에 맞는 경로 고르기

| 하고 싶은 일 | 명령 |
| --- | --- |
| 처음 보는 저장소 파악하기 | `columbus explore` |
| 기능 위치와 정확한 심볼 ID 찾기 | `columbus search checkout --format text --limit 5` |
| 소스를 읽기 전에 선언 확인하기 | `columbus context checkout --mode signatures --format text` |
| 필요한 소스 읽기 | `columbus explore checkout` |
| 호출·임포트·상속 관계 따라가기 | `columbus neighbors EXACT_SYMBOL_ID --kinds calls imports inherits --format text` |
| 들어오는 관계 살펴보기 | `columbus impact EXACT_SYMBOL_ID --format text` |
| 탐색 가능한 그래프 내보내기 | `columbus graph --level file --format html --output graph.html` |

심볼 ID는 `search` 결과에서 가져옵니다. `impact`는 제한된 그래프 탐색이며 모든 런타임 영향을 증명하지는 않습니다. 기존 자동화 명령의 기본 출력은 JSON이고, `explore`는 text입니다.

## 에이전트의 짐 줄이기

이름이나 파일을 알면 짧은 검색이나 필요한 소스 범위부터 읽습니다. 구조를 모를 때 작은 지도를 보고, 관계는 질문에 도움이 될 때 조회합니다. 근거가 충분하면 탐색을 멈춥니다.

```sh
columbus init
columbus explore checkout --session checkout
columbus explore calculateTotal --session checkout
columbus stats checkout
```

`init`은 현재 프로젝트에 `.agents/skills/columbus/SKILL.md`를 설치합니다. `--session checkout`은 `.columbus/sessions/checkout/`에 소스 receipt와 조회 기록을 남깁니다. 이후 snippet 조회는 앞서 전달한 범위를 제외하고 읽지 않은 부분을 이어 받습니다. `stats`에서 조회 횟수, 응답 바이트, 소스 바이트를 확인합니다.

Receipt는 전달한 소스의 기록이며 모델의 잃어버린 컨텍스트를 복구하지 않습니다. 새 작업·다른 에이전트·컨텍스트 유실 후에는 새 세션을 쓰세요. Telemetry는 선택 사항이고 원문이나 질문을 기록하지 않습니다. 프로젝트 ignore 규칙에 `.columbus/`를 추가하세요.

```text
.agents/skills/columbus/SKILL.md를 읽어줘. 질문에 답할 수 있는 가장
작은 검색이나 소스 범위부터 확인하고, 구조를 모를 때만 제한된 크기의
map을 사용해줘. 이번 작업의 소스 조회에는 같은 세션을 쓰고 근거가
충분하면 탐색을 멈춰줘. 수정 전 소스를 확인하고 수정 후에는 관련
테스트와 sync를 실행해줘.
```

[에이전트 사용법·receipt 한계·MCP 설정](docs/agents.md).

## 좋은 결과와 회귀를 함께 보여주는 벤치마크

**도구 응답이 작아지는 것과 실제 모델 토큰이 줄어드는 것은 다른 측정입니다.** 그래프는 기록한 JSON에서 생성하며, 데이터와 생성 스크립트를 소스 릴리스에 포함합니다.

[최근 모델 비교 11쌍](evals/model-usage-overview/REPORT.md) 중 기존 품질을 유지하면서 전체 입력·출력을 줄이는 합격 조건을 충족한 쌍은 없습니다. Columbus 1.1의 실제 모델 토큰 절감을 주장하지 않습니다. 아래 그래프는 당시 엔진 버전과 측정값을 그대로 보여줍니다.

### Columbus 1.0 응답량

![지도 출력 형식과 receipt 사용 여부에 따른 Columbus의 실제 응답 바이트 비교](docs/assets/benchmark-delivery.svg)

포함된 polyglot 예제에서 모델 호출 없이 실제 UTF-8 CLI 출력을 측정했습니다. 지도 비교는 선택한 심볼 ID와 순서가 같은지 검사합니다. 같은 context를 세 번 조회하는 비교에서 receipt는 아직 읽지 않은 범위를 먼저 전달하고, 모두 읽으면 상태 메타데이터만 반환합니다. 바이트와 CLI의 바이트 기반 토큰 추정치는 실제 모델 사용량이나 청구 비용이 아닙니다.

| 비교 | 이전 | 이후 | 변화 |
| --- | ---: | ---: | ---: |
| 같은 지도 28개 항목: JSON → text | 6,639바이트 | 3,534바이트 | **46.8% 감소** |
| context 3회: receipt 없음 → 사용 | 9,612바이트 | 4,474바이트 | **53.5% 감소** |
| receipt 1 → 2 → 3회차 소스 | 1,423바이트 | 188 → 0바이트 | 모두 읽은 뒤 중복 소스 없음 |

[새 버전 측정값·fixture 해시·방법·재현 명령](docs/benchmarks/README.md).

### 다시 방문할 때는 바뀐 파일만 분석하기

![Python 합성 파일 1,001개에서 단계별로 세 번 측정한 증분 색인 시간과 파싱 파일 수](docs/assets/benchmark-incremental.svg)

같은 방식으로 생성한 Python 파일 1,001개에서 첫 색인은 1,001개, 변경 없는 갱신은 0개, 파일 하나를 수정한 갱신은 1개를 파싱했습니다. 변경 없는 갱신은 파일 해시도 다시 계산하지 않았습니다. 그래프는 macOS arm64에서 세 번 측정한 중앙값과 최솟값·최댓값입니다. 파일 메타데이터 검사는 여전히 필요하며, OS 캐시를 비우지 않았으므로 다른 기계의 실행 시간을 보장하지 않습니다. [예제 생성·실행 원본·재현](docs/benchmarks/README.md).

### 실제 에이전트 탐색: 이전 파일럿

![이전 Codex 실험의 누적 입력 토큰. 두 답변이 모두 인용 검사를 통과한 사례에서도 입력이 증가함](docs/assets/benchmark-agent-tokens.svg)

이 실험은 이름 변경 전 **RepoAtlas 0.4.0** 엔진으로 실행했습니다. 같은 실제 소스에서 고정한 질문 세 개를 일반 `rg`·범위 읽기와 그래프를 추가한 탐색으로 각각 한 번 비교했습니다. Codex CLI 0.153.4, 요청 모델 `gpt-5.6-sol`, effort `xhigh`를 사용했습니다. 그래프 색인은 미리 제공했고 생성 시간 1.105초를 별도로 측정했습니다.

| 질문 | 인용 검사: 일반 → 그래프 | 실제 누적 입력: 일반 → 그래프 | 변화 |
| --- | --- | ---: | ---: |
| 그래프 내보내기 보호 | 통과 → 통과 | 79,358 → 106,334 | **+34.0%** |
| 설정 변경과 색인 무효화 | 실패 → 통과 | 157,482 → 138,864 | −11.8% |
| 관리 설치 경로 충돌 | 실패 → 통과 | 70,775 → 88,411 | **+24.9%** |

일반 탐색의 인용 실패 두 건은 연속된 원문 대신 생략 부호를 썼기 때문입니다. 동작을 이해하지 못했다는 증거로 보지 않으며 동일 품질의 절감 비교에서 제외합니다. **양쪽 인용이 통과한 한 쌍에서는 입력이 34.0% 늘었습니다. 일반적인 모델 토큰 절감은 입증하지 못했습니다.** 설치 사례는 명령 출력이 49.0% 줄었지만 입력 토큰은 늘었습니다.

실제 사용량에는 시작 지침, 반복 컨텍스트, 도구 교환, 캐시 동작이 영향을 줍니다. 캐시 입력은 입력 합계에 이미 포함됩니다. 전체 6회와 초기 빈 색인으로 제외한 실험 묶음을 보존했습니다. 작은 읽기 전용 파일럿이며 Columbus 1.0의 새 모델 A/B 결과가 아닙니다. [프롬프트·답변·사용량·채점](evals/exploration/results/2026-09-07/controlled.json) · [이전 관측 상세](docs/token-efficiency.md).

## 그래프로 가져오기

```sh
columbus graph --format html --level file --output graph.html
columbus graph --format mermaid --level file --kinds imports calls --output dependencies.mmd
columbus graph --format graphml --language typescript --path 'src/*' --output frontend.graphml
```

| 형식 | 용도 |
| --- | --- |
| HTML | 오프라인에서 탐색 가능한 그래프 |
| Mermaid | 문서용 편집 가능한 다이어그램 |
| GraphML | 외부 그래프 도구로 가져오기 |
| JSON | 스크립트와 구조화한 분석 |

언어·경로·관계·방향·기준 심볼로 범위를 좁힙니다. 그래프에 신뢰도와 잘림 여부를 표시하며 미지원 언어도 파일 노드를 제공합니다. 기존 출력 파일은 덮어쓰지 않습니다. [그래프 옵션](docs/usage.md#export-a-graph).

## 나침반 아래의 구조

파일 탐색기가 대상 파일을 찾고, AST·휴리스틱 분석기가 소스 근거를 로컬 SQLite 그래프에 기록합니다. 조회기는 응답 예산 안에서 선언이나 검증한 소스 범위를 선택합니다. CLI·내보내기·스킬·MCP가 같은 엔진을 씁니다.

색인은 `.columbus/index-v1.sqlite`에 저장합니다. 에이전트에게 보여준 저장소 소스는 여전히 신뢰할 수 없는 입력입니다. [아키텍처와 데이터 경계](docs/architecture.md).

| 문서 | 내용 |
| --- | --- |
| [설치](INSTALL.md) | wheel·Python 설치기·오프라인·업데이트·프리뷰 이전 |
| [CLI 사용법](docs/usage.ko.md) · [English](docs/usage.md) | 조회·출력·예산·최신성 |
| [에이전트 통합](docs/agents.md) | 스킬·세션·receipt·telemetry·MCP |
| [벤치마크](docs/benchmarks/README.md) | 그래프·데이터·방법·재현 |
| [검증 기록](VALIDATION.md) | 실행한 검사와 플랫폼 한계 |
| [기여](CONTRIBUTING.md) · [변경 기록](CHANGELOG.md) | 개발과 릴리스 이력 |

[지원](SUPPORT.md) · [보안](SECURITY.md) · [MIT 라이선스](LICENSE) · [캐릭터 이미지와 제작 기록](docs/assets/columbus-art.md)
