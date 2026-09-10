# CLI 사용법

[소개](../README.ko.md) · [English](usage.md) · [설치](../INSTALL.md) · [에이전트 연동](agents.md)

대상 저장소에서 실행하거나 `--repo /absolute/path/to/project`를 지정합니다. 인자 없이 `columbus`를 실행하면 색인을 만들지 않고 짧은 사용 가이드를 보여줍니다. `explore`의 기본 출력은 text이며, 기존 조회 명령의 JSON 기본값은 유지합니다.

## 명령 하나로 시작하기

```sh
columbus explore
columbus explore "checkout validation"
columbus explore checkout --session checkout-task
columbus stats checkout-task
```

`explore`는 검색어가 없으면 저장소 지도를, 검색어가 있으면 관련 소스를 반환합니다. 기본 예산은 메타데이터를 포함한 추정 토큰 2,000개입니다. JSON이 필요하면 `--format json`을 붙이세요. 색인은 자동 동기화하며, 저장된 스냅샷만 읽으려면 `--snapshot`을 사용합니다.

세션을 지정하면 대상 저장소의 `.columbus/sessions/checkout-task/` 아래에 `receipt.json`과 `queries.jsonl`을 사용합니다. 같은 세션으로 소스를 더 조회하면 이미 전달한 범위를 제외하고 응답량을 기록합니다. 세션은 선택 사항입니다. 새 작업이거나 컨텍스트가 압축된 뒤, 또는 이전 소스를 받지 않은 다른 에이전트라면 새 이름을 사용하세요.

`stats NAME`은 세션의 계측값을 text로 요약합니다. `--format json`도 지원합니다. 기록을 만들거나 색인을 동기화하지 않으며, 색인 DB를 지운 뒤에도 사용할 수 있습니다. 없는 세션을 지정하면 파일을 만들지 않고 오류를 반환합니다.

## 진입점 찾기

```sh
columbus map --format text --budget-tokens 2000
columbus search checkout --format text --limit 5
columbus context checkout --mode signatures --format text --budget-tokens 1500
```

검색어가 없는 map은 포함 관계를 제외한 들어오는 관계 수로 선언을 정렬합니다. 검색어가 있으면 이름 일치와 전체 텍스트 검색 순위를 사용합니다. 관련도를 판단하는 신호이므로 결과의 경로와 선언을 확인한 뒤 심볼을 고르세요.

| 조회 | 반환 내용 | 동기화 이후 소스 본문 읽기 |
| --- | --- | --- |
| `explore` | 짧은 저장소 지도, text 출력 | 없음 |
| `explore QUERY` | 예산을 적용한 소스 조각, text 출력 | 선택한 파일 |
| `map [QUERY]` | 주요 선언·위치·색인 범위 | 없음 |
| `search QUERY` | 검색 결과와 정확한 심볼 ID | 없음 |
| `context QUERY --mode signatures` | 선언과 가까운 관계 후보 | 없음 |
| `implementations SYMBOL_ID` | 하위 타입이나 메서드의 구현 후보 | 없음 |
| `resources [QUERY]` | HTTP·Kafka·테이블·캐시 선언과 근거 | 없음 |
| `context QUERY --mode snippets` | 선택한 소스 범위와 해시 검증 | 선택한 파일 |
| `symbol EXACT_SYMBOL_ID` | 지정한 선언의 현재 코드 | 해당 파일 |

첫 색인은 소스를 읽고 이후 동기화도 변경된 파일을 읽을 수 있습니다. 표의 `없음`은 동기화가 끝난 뒤 조회하는 단계를 뜻합니다.

## 소스와 관계 읽기

`search` 결과의 정확한 `id`를 사용합니다.

```sh
columbus symbol 'EXACT_SYMBOL_ID' --max-lines 80 --format text
columbus neighbors 'EXACT_SYMBOL_ID' --hops 1 --kinds calls imports --format text
columbus impact 'EXACT_SYMBOL_ID' --hops 2 --format text
columbus context checkout --mode snippets --format text --budget-tokens 2000
```

`neighbors`는 `--direction in|out|both`를 받으며 기본값은 `both`입니다. 관계 종류는 `contains`, `calls`, `imports`, `inherits`입니다. `impact`는 들어오는 `calls`와 `inherits`를 따라갑니다. 두 명령 모두 범위가 제한된 그래프 조회이며, 미해결 관계나 동적 동작은 빠질 수 있습니다.

소스 조각은 색인의 해시와 비교해 검증합니다. 검증하지 못한 소스를 최신 코드로 반환하지 않습니다. stale·잘림 표시를 확인하고 필요하면 검색 범위를 좁히거나 다시 동기화하세요.

## 구현 후보 찾기

타입이나 재정의 가능한 메서드의 정확한 ID를 지정합니다.

```sh
columbus implementations 'EXACT_SYMBOL_ID' --format text
columbus implementations 'EXACT_SYMBOL_ID' --hops 4 --limit 10 --budget-tokens 2000
columbus implementations 'EXACT_SYMBOL_ID' --hops 4 --cursor 'NEXT_CURSOR' --snapshot --format json
```

`implementations SYMBOL_ID`는 색인의 상속 관계를 따라가며 메서드에 선언된 매개변수 타입을 비교합니다. 결과에는 `relation: implementation_candidate`, 상속 경로의 근거, `signature_match`가 나옵니다. `generic_or_type_unresolved`는 타입 비교에 불확실성이 남았다는 뜻입니다. 구현 후보만으로 런타임 DI 빈이나 프록시 동작, 실제 호출 대상을 확정할 수 없으며, `runtime_verified`와 `semantic_complete`는 false입니다. 제네릭, 외부 타입, 누락된 상속 관계 때문에 후보가 빠질 수 있습니다.

`--limit`은 기본 30개, 범위는 1–200입니다. `--hops`는 기본 6, 범위는 1–8이며 방문 타입과 후보 수도 각각 200개로 제한합니다. `next_cursor`는 같은 저장소·색인 revision·심볼 ID·홉 수에 재사용합니다. 페이지 크기와 응답 예산은 바꿀 수 있습니다. `scan_truncated`는 탐색 자체가 한도에 도달했다는 뜻이므로 커서를 모두 읽어도 전체 구현을 찾았다고 볼 수 없습니다. 다음 후보가 예산에 들어가지 않으면 바이트·토큰 예산을 늘리세요.

## 리소스 선언 찾기

```sh
columbus resources --kind http --path 'src/*' --limit 10 --format text
columbus resources checkout --kind kafka --format json
columbus resources checkout --kind table --budget-bytes 6000 --budget-tokens 2000
columbus resources checkout --kind cache --format text
columbus resources --kind http --path 'src/*' --cursor 'NEXT_CURSOR' --snapshot --format json
```

`resources [QUERY]`는 색인에 저장된 JVM annotation 근거를 조회합니다. 검색어를 넣으면 선언과 근거에 포함된 텍스트를 대소문자 구분 없이 찾습니다. `--kind http|kafka|table|cache`는 리소스 종류, `--path GLOB`은 저장소 기준 경로를 제한합니다. `--limit`은 기본 30개, 범위는 1–100입니다. resources와 implementations의 기본 출력은 JSON이며 `--format json|text`를 지원합니다. 두 명령 모두 `--snapshot`이 없으면 자동 동기화합니다.

| 종류 | 선언에서 추출하는 근거 |
| --- | --- |
| `http` | Spring 요청 매핑, HTTP 메서드, 결합 가능한 클래스·메서드 경로 |
| `kafka` | Spring Kafka listener의 토픽·패턴, group ID, 선언된 시작 설정 |
| `table` | JPA `@Table`의 이름·schema·catalog |
| `cache` | Spring 캐시 연산, 이름·키·조건·무효화 옵션 |

각 결과에는 `owner_id`, 소스 경로와 annotation 줄 번호, `evidence`, `limitations`가 나옵니다. 선언 본문은 `symbol OWNER_ID`로 읽습니다. `resolution`은 다음과 같이 해석하세요.

| 상태 | 의미 |
| --- | --- |
| `literal` | 추출기가 지원하는 범위에서 annotation을 식별했고 값이 리터럴로 확인됨 |
| `dynamic` | 표현식·placeholder·SpEL을 평가하지 않고 선언 텍스트로 보존함 |
| `incomplete` | 누락·모호성·잘림·미지원 구문으로 추출이 불완전함. `limitations` 확인 필요 |

`literal`도 실제 HTTP 등록, DI 선택, 브로커 구독, SQL 접근, 캐시 실행을 검증했다는 뜻은 아닙니다. `runtime_verified`와 `semantic_complete`는 false입니다. 메타 annotation, annotation 컨테이너, 상속된 선언, 외부 설정, 프레임워크 기본값은 펼치지 않습니다. 테이블 선언만으로 쿼리 경로를 알 수 없으며, `declared_disabled`인 listener를 활성 구독으로 해석하지 마세요.

`next_cursor`는 같은 저장소·revision·검색어·`--kind`·`--path`에 전달합니다. `--limit`과 응답 예산은 바꿔도 됩니다. 한 번에 최대 200개의 annotation 후보를 확인하므로 필터링된 빈 페이지에도 다음 커서가 있을 수 있습니다. 잘린 응답의 `omitted_candidates`는 정확한 남은 결과 수가 아니라 이어 읽을 후보가 있다는 표시입니다(`omitted_candidates_exact: false`). 커서가 없어도 색인 조회가 끝났다는 뜻일 뿐, 모든 런타임 리소스를 찾았다는 뜻은 아닙니다.

## 조회 범위 좁히기

`explore`, `search`, `map`, `context`, `graph`, 호환 명령 `export`에 경로·언어 필터를 적용합니다.

```sh
columbus search checkout --language typescript --path 'web/*' --format text
columbus explore checkout --language typescript --path 'web/*'
columbus context checkout --path 'web/*' --mode signatures --format text
```

glob은 셸이 먼저 펼치지 않도록 따옴표로 감쌉니다. 언어 이름에는 `typescript`, `cpp`, `csharp`처럼 감지된 소문자 값을 넣습니다. 사용자 언어 설정은 [언어 지원](languages.md)을 참고하세요.

`resources`도 `--path`를 받지만 언어 필터는 지원하지 않습니다. `implementations`는 대상 심볼과 홉 수로 탐색 범위를 정합니다.

## 응답 크기 제한하기

| 옵션 | 범위 | 의미 |
| --- | --- | --- |
| `--budget-bytes` | 2,048–64,000 | explore/map/context/neighbors/impact/implementations/resources의 UTF-8 응답 예산 |
| `--budget-tokens` | 700–21,000 | `tokens × 3`으로 계산한 바이트 예산 |
| search의 `--limit` | 결과 수 | 검색 후보 제한 |
| implementations/resources의 `--limit` | 1–200 / 1–100 | 페이지당 최대 항목 수. 기본 30개 |
| symbol의 `--max-lines` | 코드 줄 수 | 소스 조각 제한 |

explore의 기본 예산은 추정 토큰 2,000개, 즉 6,000바이트입니다. `--budget-tokens`나 `--budget-bytes`를 명시하면 그 값이 기본 예산을 대체합니다. 둘 다 지정하면 더 작은 바이트 한도를 적용합니다.

```sh
columbus explore checkout --budget-tokens 3000
columbus explore checkout --budget-bytes 2048
```

기존 map과 context의 기본 바이트 예산은 각각 6,000과 12,000입니다. 두 명령은 `--budget-tokens`만 높여도 기본 바이트 한도가 늘지 않으므로 큰 응답이 필요하면 둘 다 지정합니다.

`implementations`와 `resources`의 기본 예산은 12,000바이트이며 근거·커서·계측 필드도 포함합니다. 바이트·토큰 한도 중 작은 값을 적용하므로 기본 상한을 높이려면 두 옵션을 함께 지정하세요. 담지 못한 항목은 커서로 이어 읽습니다. 항목 하나와 메타데이터도 담을 수 없는 예산이면 오류를 반환합니다.

```sh
columbus context checkout --budget-bytes 18000 --budget-tokens 6000 --format text
```

예산에는 선택한 JSON 또는 text 출력의 계측 필드와 메타데이터도 포함합니다. `estimated_tokens`는 `ceil(UTF-8 output bytes / 3)`이며 모델 토크나이저의 실측값이 아닙니다. 형식별 출력 계측값과 telemetry를 기준으로 비교하세요. MCP 전송 봉투와 직렬화 비용은 core 응답 예산 밖에 있습니다.

`truncated`, `omitted_candidates`, `stale_candidates`, 개별 소스의 잘림 여부를 확인하세요. 작은 예산 때문에 관련 후보가 빠질 수 있으므로 잘린 응답을 저장소 전체 설명으로 해석하지 않습니다.

`neighbors`와 `impact`도 `--budget-bytes`/`--budget-tokens`를 지원하며 기본 상한은 12,000바이트입니다. 전체 docstring은 제외하고 signature와 edge evidence는 각각 UTF-8 240바이트까지 반환합니다. `omitted_text_bytes`는 선택한 그래프에서 먼저 제거한 텍스트, `omitted_nodes`/`omitted_edges`는 직렬화 예산으로 생략한 항목 수입니다. `traversal_truncated`와 `payload_truncated`로 탐색 제한과 응답 생략을 구분하며, `truncated`는 둘을 합친 상태입니다. 남은 edge에는 양쪽 endpoint ID가 모두 포함됩니다. 예산이 있는 JSON은 `--pretty`를 주어도 compact 형식을 유지합니다.

## 같은 코드를 반복해서 받지 않기

같은 에이전트가 한 작업에서 소스를 계속 조회한다면 세션 하나를 사용합니다.

```sh
columbus explore checkout --session checkout-task
columbus explore calculateTotal --session checkout-task
columbus stats checkout-task --format json
```

`context QUERY --session NAME`도 같은 파일을 사용하며, context의 JSON 기본 출력은 유지합니다. 세션 이름은 영문자·숫자로 시작하는 1~64자의 영문자·숫자·하이픈·밑줄입니다. `CON` 같은 예약 장치 이름은 거부합니다. 세션 디렉터리와 파일에는 심볼릭 링크를 사용할 수 없습니다. `--session`과 직접 지정한 `--receipt`·`--telemetry`는 함께 쓰지 않습니다.

세션은 실제 소스를 반환하는 snippets 조회에만 적용합니다. 검색어 없는 `explore`나 `--mode signatures`에 `--session`을 붙이면 receipt를 만들지 않고 오류를 반환합니다. 선언만 탐색할 때는 세션을 생략하세요.

새 세션의 첫 조회에 `--max-queries 8 --max-session-bytes 24000 --max-no-progress 2`를 붙이면 누적 한도를 저장합니다. 이후 옵션을 생략해도 같은 정책을 적용하며, 기존 한도를 바꾸거나 이미 사용한 무제한 세션에 소급 적용하지 않습니다. 조회 횟수에는 허용 후 실패한 시도도 포함합니다. 새 소스나 실제로 전진한 continuation은 진행으로 계산하고, 반복된 빈 결과는 진행 없는 횟수를 늘립니다. revision이 바뀌어도 누적 사용량은 유지합니다.

소진 시 동기화·소스 조회 전에 종료 코드 3으로 중단하며 stdout은 비워 둡니다. stderr에는 이유·사용량·남은 바이트를 짧게 표시합니다. 전송 도중 실패하면 사용량을 0으로 돌리지 않고 `pending` 예약량을 남겨 재호출을 막습니다. `stats --format json`의 `session_budget`은 이 사용량과 예약량을 조회 로그와 구분해 보여 줍니다. 동시 호출은 거부합니다.

이 한도는 이름 있는 CLI snippets 세션의 허용된 조회와 UTF-8 stdout 응답만 통제합니다. stderr·stats·map/search·직접 receipt·MCP·다른 도구/에이전트·모델 청구 비용은 제외합니다. 소진은 작업 완료가 아니며, 새 이름으로 반복 우회하지 마세요. 컨텍스트 손실로 새 receipt가 필요해도 이전 비용은 호스트의 작업 합계에 남겨야 합니다. 상태 손상, 부분 전달, 정책 변경과 수동 복구의 자세한 규칙은 [세션 예산](../skills/columbus/references/session-budgets.md)을 참고하세요.

파일 위치를 직접 정하려면 작업별 receipt를 대신 사용합니다. `--mode signatures`에는 receipt를 지정하지 않습니다.

```sh
columbus context checkout --receipt .columbus/checkout-receipt.json --format text
columbus context calculateTotal --receipt .columbus/checkout-receipt.json --format text
```

receipt는 앞선 조회에서 전달한 소스의 문자 범위를 기록합니다. 같은 검색을 반복하거나 부모·자식 심볼이 겹치는 경우 이미 전달한 범위를 제외하며, 긴 줄의 일부만 받았을 때도 이어 읽을 수 있습니다. 최신성·부분 출력·새 receipt를 시작할 조건은 [receipt 계약](agents.md#context-receipts)에 정리했습니다.

호출 측에서 심볼 ID를 관리한다면 `--exclude-id`를 반복할 수도 있습니다.

```sh
columbus context checkout --exclude-id 'EXACT_SYMBOL_ID' --format text
```

이 옵션은 정확히 같은 ID만 제외합니다. 잘린 심볼을 제외하면 아직 읽지 않은 나머지 코드도 제외하며, 다른 ID의 겹치는 코드는 제외하지 않습니다. 색인 `revision`이 바뀌면 호출 측 제외 목록을 비우세요.

## 검색 결과 이어 읽기

`search` 응답의 `next_cursor`가 있으면 같은 검색어·필터에 `--cursor CURSOR`를 전달합니다. 페이지 크기는 바꿀 수 있지만 인덱스 revision이 바뀌면 검색을 다시 시작해야 합니다. Context receipt는 내부에서 이어 읽기 위치를 관리합니다. `receipt.has_more`가 참인 동안 같은 snippet 조회를 반복하면 첫 20개 이후의 후보와 부분적으로 읽은 소스도 조회합니다. 조회 소진은 의미 분석이 완전하다는 뜻이 아닙니다.

## 그래프 내보내기

```sh
columbus graph --format html --output graph.html
columbus graph --format mermaid --level file --kinds imports calls --output dependencies.mmd
columbus graph --format graphml --language typescript --path 'src/*' --output frontend.graphml
columbus graph --format json --focus 'EXACT_SYMBOL_ID' --hops 2 --kinds calls --output flow.json
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

기존 출력 파일은 덮어쓰지 않습니다. 새 경로를 사용하거나 이전 출력 파일을 직접 지우세요. HTML은 자체 포함 파일이라 Columbus 서버 없이 열립니다. `export`는 `graph`의 호환 명령으로 유지합니다.

## 색인 최신성 확인하기

```sh
columbus sync
columbus sync --summary
columbus index /absolute/path/to/project --summary
columbus status --summary
columbus status --verify-content
columbus sync --verify-content
```

`sync`, 호환 명령 `index ROOT`, `status`에 `--summary`를 붙이면 전체 파일 목록과 진단 상세를 생략하고 집계·최신성을 JSON으로 반환합니다. `summary: true`, `inventory_omitted: true`, 진단 수와 제공 가능한 stale 경로 수가 포함됩니다. 평소에는 요약을 사용하고 상세 확인이 필요하면 옵션을 빼세요. 출력만 바꾸는 옵션이므로 해시 검증이 필요하면 `--verify-content`를 함께 지정합니다. 세 명령은 `--format`이나 바이트·토큰 예산 옵션을 받지 않습니다.

코드 조회는 `--snapshot`이 없으면 자동 동기화합니다. 시작 가이드, `stats`, `telemetry`는 동기화하지 않습니다. 빠른 동기화는 파일 메타데이터로 변경 없는 알려진 파일의 해시 재계산을 건너뜁니다. 타임스탬프를 신뢰하기 어렵거나 본문 검증이 필요하면 `--verify-content`를 사용하세요. 알 수 없는 확장자는 텍스트 판별을 위해 내용을 읽을 수 있으며, 이 비용은 `inventory.probe_files`와 `inventory.probe_bytes`에 표시합니다.

색인은 소스·설정·분석기·저장소/worktree 상태를 반영합니다. 다른 DB를 쓰려면 `--db PATH`를 지정하세요. 스냅샷의 저장소 경로가 다르면 조회를 거부합니다. MCP는 저장된 스냅샷을 사용하므로 수정이나 브랜치 변경 뒤 CLI로 동기화해야 합니다.

내부 파싱 캐시는 압축될 수 있지만 CLI 응답은 일반 JSON이나 text를 유지합니다. 이전 버전의 호환 가능한 색인은 `sync`를 한 번 실행해 탐색 메타데이터를 갱신한 뒤 `--snapshot`으로 읽으세요. 구버전 실행 파일은 압축 캐시를 읽지 못할 수 있으므로 버전을 내릴 때는 그 실행 파일로 새 `--db` 경로에 별도 색인을 만드세요. 지원하지 않는 schema도 오류 안내에 따라 새 `--db` 경로에서 다시 색인해야 합니다.

## 탐색 과정 관측하기

```sh
columbus explore checkout --session checkout-task
columbus stats checkout-task
```

explore의 세션 기록에는 실제 호출한 `context` 명령이 남습니다. 요약에는 출력 바이트·추정 토큰·소스 바이트·응답 시간·반환 건수가 나옵니다. 로그 경로를 직접 정하거나 지도 조회만 계측하려면 `--telemetry`를 사용하세요.

```sh
columbus map --format text --telemetry .columbus/exploration.jsonl
columbus context checkout --format text --receipt .columbus/checkout-receipt.json \
  --telemetry .columbus/exploration.jsonl
columbus telemetry .columbus/exploration.jsonl --format text
```

telemetry는 명시했을 때 로컬에 남기는 조회 메타데이터입니다. 응답량과 탐색 동작을 보여주며 모델 요금을 조회하지 않습니다. 측정 정의·비교 탐색·증거는 [관측 가이드](token-efficiency.md)를 참고하세요.
