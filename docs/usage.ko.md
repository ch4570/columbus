# CLI 사용법

[소개](../README.ko.md) · [English](usage.md) · [설치](../INSTALL.md) · [에이전트 연동](agents.md)

대상 저장소에서 실행하거나 `--repo /absolute/path/to/project`를 지정합니다. 인자 없이 `repoatlas`를 실행하면 색인을 만들지 않고 짧은 사용 가이드를 보여줍니다. `explore`의 기본 출력은 text이며, 기존 조회 명령의 JSON 기본값은 유지합니다.

## 명령 하나로 시작하기

```sh
repoatlas explore
repoatlas explore "checkout validation"
repoatlas explore checkout --session checkout-task
repoatlas stats checkout-task
```

`explore`는 검색어가 없으면 저장소 지도를, 검색어가 있으면 관련 소스를 반환합니다. 기본 예산은 메타데이터를 포함한 추정 토큰 2,000개입니다. JSON이 필요하면 `--format json`을 붙이세요. 색인은 자동 동기화하며, 저장된 스냅샷만 읽으려면 `--snapshot`을 사용합니다.

세션을 지정하면 대상 저장소의 `.repoatlas/sessions/checkout-task/` 아래에 `receipt.json`과 `queries.jsonl`을 사용합니다. 같은 세션으로 소스를 더 조회하면 이미 전달한 범위를 제외하고 응답량을 기록합니다. 세션은 선택 사항입니다. 새 작업이거나 컨텍스트가 압축된 뒤, 또는 이전 소스를 받지 않은 다른 에이전트라면 새 이름을 사용하세요.

`stats NAME`은 세션의 계측값을 text로 요약합니다. `--format json`도 지원합니다. 기록을 만들거나 색인을 동기화하지 않으며, 색인 DB를 지운 뒤에도 사용할 수 있습니다. 없는 세션을 지정하면 파일을 만들지 않고 오류를 반환합니다.

## 진입점 찾기

```sh
repoatlas map --format text --budget-tokens 2000
repoatlas search checkout --format text --limit 5
repoatlas context checkout --mode signatures --format text --budget-tokens 1500
```

검색어가 없는 map은 포함 관계를 제외한 들어오는 관계 수로 선언을 정렬합니다. 검색어가 있으면 이름 일치와 전체 텍스트 검색 순위를 사용합니다. 관련도를 판단하는 신호이므로 결과의 경로와 선언을 확인한 뒤 심볼을 고르세요.

| 조회 | 반환 내용 | 동기화 이후 소스 본문 읽기 |
| --- | --- | --- |
| `explore` | 짧은 저장소 지도, text 출력 | 없음 |
| `explore QUERY` | 예산을 적용한 소스 조각, text 출력 | 선택한 파일 |
| `map [QUERY]` | 주요 선언·위치·색인 범위 | 없음 |
| `search QUERY` | 검색 결과와 정확한 심볼 ID | 없음 |
| `context QUERY --mode signatures` | 선언과 가까운 관계 후보 | 없음 |
| `context QUERY --mode snippets` | 선택한 소스 범위와 해시 검증 | 선택한 파일 |
| `symbol EXACT_SYMBOL_ID` | 지정한 선언의 현재 코드 | 해당 파일 |

첫 색인은 소스를 읽고 이후 동기화도 변경된 파일을 읽을 수 있습니다. 표의 `없음`은 동기화가 끝난 뒤 조회하는 단계를 뜻합니다.

## 소스와 관계 읽기

`search` 결과의 정확한 `id`를 사용합니다.

```sh
repoatlas symbol 'EXACT_SYMBOL_ID' --max-lines 80 --format text
repoatlas neighbors 'EXACT_SYMBOL_ID' --hops 1 --kinds calls imports --format text
repoatlas impact 'EXACT_SYMBOL_ID' --hops 2 --format text
repoatlas context checkout --mode snippets --format text --budget-tokens 2000
```

`neighbors`는 `--direction in|out|both`를 받으며 기본값은 `both`입니다. 관계 종류는 `contains`, `calls`, `imports`, `inherits`입니다. `impact`는 들어오는 `calls`와 `inherits`를 따라갑니다. 두 명령 모두 범위가 제한된 그래프 조회이며, 미해결 관계나 동적 동작은 빠질 수 있습니다.

소스 조각은 색인의 해시와 비교해 검증합니다. 검증하지 못한 소스를 최신 코드로 반환하지 않습니다. stale·잘림 표시를 확인하고 필요하면 검색 범위를 좁히거나 다시 동기화하세요.

## 조회 범위 좁히기

`explore`, `search`, `map`, `context`, `graph`, 호환 명령 `export`에 경로·언어 필터를 적용합니다.

```sh
repoatlas search checkout --language typescript --path 'web/*' --format text
repoatlas explore checkout --language typescript --path 'web/*'
repoatlas context checkout --path 'web/*' --mode signatures --format text
```

glob은 셸이 먼저 펼치지 않도록 따옴표로 감쌉니다. 언어 이름에는 `typescript`, `cpp`, `csharp`처럼 감지된 소문자 값을 넣습니다. 사용자 언어 설정은 [언어 지원](languages.md)을 참고하세요.

## 응답 크기 제한하기

| 옵션 | 범위 | 의미 |
| --- | --- | --- |
| `--budget-bytes` | 2,048–64,000 | explore/map/context의 UTF-8 응답 예산 |
| `--budget-tokens` | 700–21,000 | `tokens × 3`으로 계산한 바이트 예산 |
| search의 `--limit` | 결과 수 | 검색 후보 제한 |
| symbol의 `--max-lines` | 코드 줄 수 | 소스 조각 제한 |

explore의 기본 예산은 추정 토큰 2,000개, 즉 6,000바이트입니다. `--budget-tokens`나 `--budget-bytes`를 명시하면 그 값이 기본 예산을 대체합니다. 둘 다 지정하면 더 작은 바이트 한도를 적용합니다.

```sh
repoatlas explore checkout --budget-tokens 3000
repoatlas explore checkout --budget-bytes 2048
```

기존 map과 context의 기본 바이트 예산은 각각 6,000과 12,000입니다. 두 명령은 `--budget-tokens`만 높여도 기본 바이트 한도가 늘지 않으므로 큰 응답이 필요하면 둘 다 지정합니다.

```sh
repoatlas context checkout --budget-bytes 18000 --budget-tokens 6000 --format text
```

예산에는 선택한 JSON 또는 text 출력의 계측 필드와 메타데이터도 포함합니다. `estimated_tokens`는 `ceil(UTF-8 output bytes / 3)`이며 모델 토크나이저의 실측값이 아닙니다. 형식별 출력 계측값과 telemetry를 기준으로 비교하세요. MCP 전송 봉투와 직렬화 비용은 core 응답 예산 밖에 있습니다.

`truncated`, `omitted_candidates`, `stale_candidates`, 개별 소스의 잘림 여부를 확인하세요. 작은 예산 때문에 관련 후보가 빠질 수 있으므로 잘린 응답을 저장소 전체 설명으로 해석하지 않습니다.

## 같은 코드를 반복해서 받지 않기

같은 에이전트가 한 작업에서 소스를 계속 조회한다면 세션 하나를 사용합니다.

```sh
repoatlas explore checkout --session checkout-task
repoatlas explore calculateTotal --session checkout-task
repoatlas stats checkout-task --format json
```

`context QUERY --session NAME`도 같은 파일을 사용하며, context의 JSON 기본 출력은 유지합니다. 세션 이름은 영문자·숫자로 시작하는 1~64자의 영문자·숫자·하이픈·밑줄입니다. `CON` 같은 예약 장치 이름은 거부합니다. 세션 디렉터리와 파일에는 심볼릭 링크를 사용할 수 없습니다. `--session`과 직접 지정한 `--receipt`·`--telemetry`는 함께 쓰지 않습니다.

세션은 실제 소스를 반환하는 snippets 조회에만 적용합니다. 검색어 없는 `explore`나 `--mode signatures`에 `--session`을 붙이면 receipt를 만들지 않고 오류를 반환합니다. 선언만 탐색할 때는 세션을 생략하세요.

파일 위치를 직접 정하려면 작업별 receipt를 대신 사용합니다. `--mode signatures`에는 receipt를 지정하지 않습니다.

```sh
repoatlas context checkout --receipt .repoatlas/checkout-receipt.json --format text
repoatlas context calculateTotal --receipt .repoatlas/checkout-receipt.json --format text
```

receipt는 앞선 조회에서 전달한 소스의 문자 범위를 기록합니다. 같은 검색을 반복하거나 부모·자식 심볼이 겹치는 경우 이미 전달한 범위를 제외하며, 긴 줄의 일부만 받았을 때도 이어 읽을 수 있습니다. 최신성·부분 출력·새 receipt를 시작할 조건은 [receipt 계약](agents.md#context-receipts)에 정리했습니다.

호출 측에서 심볼 ID를 관리한다면 `--exclude-id`를 반복할 수도 있습니다.

```sh
repoatlas context checkout --exclude-id 'EXACT_SYMBOL_ID' --format text
```

이 옵션은 정확히 같은 ID만 제외합니다. 잘린 심볼을 제외하면 아직 읽지 않은 나머지 코드도 제외하며, 다른 ID의 겹치는 코드는 제외하지 않습니다. 색인 `revision`이 바뀌면 호출 측 제외 목록을 비우세요.

## 그래프 내보내기

```sh
repoatlas graph --format html --output graph.html
repoatlas graph --format mermaid --level file --kinds imports calls --output dependencies.mmd
repoatlas graph --format graphml --language typescript --path 'src/*' --output frontend.graphml
repoatlas graph --format json --focus 'EXACT_SYMBOL_ID' --hops 2 --kinds calls --output flow.json
```

| 옵션 | 동작 |
| --- | --- |
| `--format json\|mermaid\|graphml\|html` | 데이터·문서 다이어그램·외부 도구·오프라인 탐색 |
| `--level symbol\|file` | 선언별 그래프 또는 파일 간 관계 |
| `--focus ID` | 정확한 ID를 중심으로 탐색. 모호하지 않은 이름도 허용 |
| `--direction in\|out\|both` | 중심 심볼의 관계 방향 |
| `--kinds KIND ...` | 관계 종류 |
| `--path GLOB`, `--language NAME` | 경로·언어 범위 |
| `--limit N` | 출력 노드 수 |

전체 그래프는 기본 1,000노드, 최대 5,000노드입니다. 중심 탐색은 최대 200노드·3홉이며 관계 수도 제한합니다. 잘림 표시가 있으면 범위를 나누어 조회하세요.

기존 출력 파일은 덮어쓰지 않습니다. 새 경로를 사용하거나 이전 출력 파일을 직접 지우세요. HTML은 자체 포함 파일이라 RepoAtlas 서버 없이 열립니다. `export`는 `graph`의 호환 명령으로 유지합니다.

## 색인 최신성 확인하기

```sh
repoatlas sync
repoatlas status --verify-content
repoatlas sync --verify-content
```

코드 조회는 `--snapshot`이 없으면 자동 동기화합니다. 시작 가이드, `stats`, `telemetry`는 동기화하지 않습니다. 빠른 동기화는 파일 메타데이터로 변경 없는 알려진 파일의 해시 재계산을 건너뜁니다. 타임스탬프를 신뢰하기 어렵거나 본문 검증이 필요하면 `--verify-content`를 사용하세요. 알 수 없는 확장자는 텍스트 판별을 위해 내용을 읽을 수 있으며, 이 비용은 `inventory.probe_files`와 `inventory.probe_bytes`에 표시합니다.

색인은 소스·설정·분석기·저장소/worktree 상태를 반영합니다. 다른 DB를 쓰려면 `--db PATH`를 지정하세요. 스냅샷의 저장소 경로가 다르면 조회를 거부합니다. MCP는 저장된 스냅샷을 사용하므로 수정이나 브랜치 변경 뒤 CLI로 동기화해야 합니다.

## 탐색 과정 관측하기

```sh
repoatlas explore checkout --session checkout-task
repoatlas stats checkout-task
```

explore의 세션 기록에는 실제 호출한 `context` 명령이 남습니다. 요약에는 출력 바이트·추정 토큰·소스 바이트·응답 시간·반환 건수가 나옵니다. 로그 경로를 직접 정하거나 지도 조회만 계측하려면 `--telemetry`를 사용하세요.

```sh
repoatlas map --format text --telemetry .repoatlas/exploration.jsonl
repoatlas context checkout --format text --receipt .repoatlas/checkout-receipt.json \
  --telemetry .repoatlas/exploration.jsonl
repoatlas telemetry .repoatlas/exploration.jsonl --format text
```

telemetry는 명시했을 때 로컬에 남기는 조회 메타데이터입니다. 응답량과 탐색 동작을 보여주며 모델 요금을 조회하지 않습니다. 측정 정의·비교 탐색·증거는 [관측 가이드](token-efficiency.md)를 참고하세요.
