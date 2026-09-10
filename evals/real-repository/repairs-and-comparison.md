# 탐색 결함 수정과 Graphify 비교

2026-09-10의 [수정 전 평가](README.md)를 바탕으로 파일 그래프, 변경 없는 refresh, JVM 호출 추론, 구현 후보·프레임워크 선언 탐색, HTML 가독성을 수정했다. 비교 대상의 관계 수를 늘리는 것이 아니라, 원문에서 확인한 관계를 놓치는 이유와 잘못 연결할 위험을 함께 점검했다.

## 무엇이 문제였나

| 원인 | 수정 | 남는 한계 |
| --- | --- | --- |
| 같은 파일의 `contains`까지 포함한 symbol edge 20,000개를 먼저 자른 뒤 파일 간 관계로 투영 | SQL에서 파일 간 관계를 묶은 뒤 제한 적용. 관계 개수와 결정적인 대표 근거 유지 | SQL은 관련 행을 스캔·정렬한다. 실제 투영 결과가 한도를 넘으면 계속 잘림을 표시 |
| 변경이 없어도 약 95 MB의 JSON 파싱 캐시를 읽고 역직렬화 | metadata만 조회하는 경로와 실제 재연결에 필요한 캐시 로딩 분리. 내부 캐시를 stdlib zlib BLOB으로 저장 | 파일·Git·설정·재확인 절차는 유지. 변경 파일이 있으면 전체 관계 재연결 비용이 남음 |
| wildcard import가 명시적 import까지 막고, 상속·제네릭·컬렉션 원소와 반환형 추론 부족 | 명시적 import 우선, 제네릭 bound, 상속 멤버, 선언된 반환형, 제한된 List/Map/lambda 추론 | 동명 overload·사용자 extension/operator·typealias가 모호하면 추론을 중단. 컴파일러 수준 분석 아님 |
| 인터페이스 선언까지는 호출이 연결돼도 구현 메서드로 이동할 방법이 없음 | `implementations`로 상속·선언 시그니처 기반 후보와 근거 제공 | 실제 DI 선택·프록시·런타임 dispatch는 확인하지 않음 |
| Spring annotation이 텍스트에만 남음 | `resources`로 HTTP/Kafka/JPA table/cache 선언과 원문 hash·위치·표현식·해석 한계 조회 | meta-annotation, 설정값, 외부 repository 동작, live SQL/broker/cache는 확장하지 않음 |
| 긴 공통 경로 접두사로 모든 라벨이 같아지고 모바일 선택 노드가 화면 밖으로 나감 | 구분 가능한 suffix, 전체 accessible identity, 선택 노드 양축 중앙 이동 | 큰 그래프의 이웃 전체를 한 화면에 넣지는 않음. 가로·세로 스크롤 유지 |

`--summary`는 `sync`, `index`, `status`의 경로별 inventory를 생략한다. 확인된 stale 건수와 원인은 유지하며, 검사하지 않은 상태를 정상으로 바꾸지 않는다. 새 구현 후보·리소스 조회는 기존 `calls`에 추측 관계를 삽입하지 않는다. JSON과 text 모두 전체 응답 byte/token 예산과 revision-bound cursor를 적용한다.

실제 HTTP 선언 대조에서는 Kotlin grammar가 클래스 앞의 연속 annotation 일부를 `annotated_expression`으로 분리하는 결함도 확인했다. 인접한 annotation-only 구간만 제한적으로 복구하고 선언 span을 맞췄다. 실행식·구분자·이전 선언을 가로지르는 구간은 붙이지 않는다. 구버전이나 불완전한 클래스 metadata로는 전체 HTTP 경로를 확정하지 않으며, 경로가 비었다고 `/`를 만들어 내지 않는다.

## 동일 저장소의 수정 전후 실측

최종 측정은 같은 파일 hash 목록, 교대 순서 3회, 새 DB, 별도 프로세스 기준이다. OS 캐시는 비우지 않았다. 최초 색인은 빈 DB 생성이며 cold disk를 뜻하지 않는다. `sync`와 검색 시간에는 프로세스 시작·기존 전체 JSON 직렬화가 포함되므로 `--summary` 효과를 섞지 않는다.

평가 도중 원본 저장소에 외부 커밋이 반영되는 것을 감지했다. 변경과 겹친 추가 추출은 잠정 결과로만 보존하고 최종 정확도 비교에서 제외했다. 마지막 측정·검증은 최초 커밋의 별도 로컬 체크아웃에서 실행했다. 원본 worktree를 되돌리거나 수정하지 않았다.

macOS arm64, Python 3.14.7에서 2,742개 파일·12,799,646 source bytes를 양쪽 엔진으로 측정했다. 시간과 RSS는 각 3회 중앙값이다.

| 항목 | 수정 전 | 수정 후 |
| --- | ---: | ---: |
| 최초 색인 wall | 20.952초 | 20.686초 |
| 변경 없는 sync wall | 2.928초 | 2.565초 |
| 자동 refresh 포함 검색 wall | 3.985초 | 3.055초 |
| snapshot 검색 wall | 0.188초 | 0.219초 |
| 변경 없는 sync 최대 RSS | 437,583,872 bytes | 47,382,528 bytes |
| 최초 색인 최대 RSS | 500,023,296 bytes | 259,817,472 bytes |
| 새 SQLite 파일 | 209,350,656 bytes | 126,529,536 bytes |
| 내부 파싱 캐시 | 95,093,219 bytes | 8,587,063 bytes |

자동 검색 중앙값은 약 23%, 변경 없는 sync는 약 12% 줄었다. 더 분명한 변화는 반복 sync의 최대 메모리 약 89%, DB 파일 약 40% 감소다. 최초 색인은 사실상 비슷하고 snapshot 검색은 빨라지지 않았다. 3회 소표본이며 시간 변동이 크다. before sync는 2.421–10.921초, after sync는 2.510–3.141초였고, after snapshot에도 0.566초 관측이 있었다. 이 결과를 일반적인 지연 보장이나 통계적 우위로 해석하지 않는다.

여섯 DB 모두 파일 목록·내용 hash가 같았고, SQLite/FK 무결성·자동/snapshot 검색 ID 일치·변경 없는 hash/parse/relink 0을 통과했다. 최종 코드 hash도 측정 전후 같다. 심볼은 양쪽 18,023개, 관계는 25,291 → 25,600개다. 참조 연결은 4,557/52,672 → 4,866/52,672이며 이 비율은 recall이 아니다.

기본 파일 export는 이제 저장된 파일 간 관계 **7,444/7,444개**, 누락 0, `truncated=false`다. 관계 추론 자체가 개선돼 수정 전 DB의 7,257개와 분모가 다르다. 공개 20,000-containment 회귀 fixture는 기본·필터 export 모두 3 nodes / 2 edges, `truncated=false`다. 원문에서 확인한 기존 호출 25개도 모두 유지됐다.

## Graphify와 비교한 범위

비공개 저장소에서 동일한 `.kt` 2,043개와 `.java` 91개, 총 2,134개를 양쪽에 전달했다. `.kts` 105개는 이 비교에서 제외했다. private source는 로컬 code-only 실행에만 사용했다. Graphify 실행에는 Python socket/DNS/subprocess audit guard를 적용했으며, 이것을 임의 native code까지 막는 sandbox 보장으로 해석하지 않는다.

- Graphify: `Graphify-Labs/graphify`, commit `3f82bf7f837a07fb0f7668fbdbd5662801906942`, package `graphifyy==0.9.57`. 기본 브랜치 `v8`은 package major version이 아니다.
- Columbus baseline: `098f3ab136b2188b5c4db7a963bbdbaa1d9e0fd9`의 frozen source. 이 커밋의 엔진은 최초 평가의 `06fe807`과 같다.
- Columbus Python 3.14.7/Tree-sitter 0.26.0, Graphify Python 3.12.12/Tree-sitter 0.25.2. 양쪽 Java grammar 0.23.5, Kotlin grammar 1.1.0.

| 원문에서 먼저 고른 관계 | 수정 전 Columbus | Graphify raw / built | 수정 후 Columbus |
| --- | ---: | ---: | ---: |
| 로컬 호출 13개 | 7 | 1 / 1 | 12 |
| 로컬 상속·구현 1개 | 1 | 1 / 1 | 1 |

기존 누락 6개 중 5개가 연결됐다. 나머지 하나는 동명 bulk-index 메서드의 overload 선택이다. 모호한 대상을 임의 연결하지 않았다. 수정 후 동일 JVM 목록은 16,750 symbols / 24,213 edges / 3,336 calls / 805 inherits, dangling endpoint 0이다. 원문 hash와 정확한 호출 파일·줄·선언 ID까지 확인했다. 수정 후 추출 단계의 시간은 다른 검증과 겹쳤으므로 속도 비교에서 제외했다.

별도 Java 합성 9개 사례에서 Graphify는 잘못된 패키지와 상속 overload 대상 두 개를 반환했다. 수정 후 Columbus는 금지된 대상 0개로 safety gate를 통과했지만, 기대한 긍정 관계도 8개 중 4개만 찾았다. `this`, enhanced-for, 상속 overload, 부분 복구 구문 등의 보수적인 미연결이 남는다. 이 적대적 소표본 역시 전체 정확도 순위가 아니다.

외부 Spring Data 대상 4개는 로컬 분모에 넣지 않았다. 표본은 Kotlin의 주입된 receiver와 업무 흐름에 치우쳐 있으며 **전체 precision/recall이 아니다**. 이름만 맞추지 않고 실제 소유 클래스와 선언 ID를 대조했다. Graphify의 동일 이름 overload는 단일 ID에 합쳐질 수 있어, 이름 수준 관계만으로 overload 선택이 맞았다고 판정하지 않았다. [Graphify method ID 생성](https://github.com/Graphify-Labs/graphify/blob/3f82bf7f837a07fb0f7668fbdbd5662801906942/graphify/extractors/engine.py#L3205)

Graphify의 code-only 첫 추출(AST + cross-file resolution)은 19.789초, 두 번째 프로세스의 변경 없는 cache 추출은 6.839초였다. 이후 directed graph build는 각각 0.768초와 0.562초다. Columbus baseline의 동일 목록 `parse_jvm`과 `resolve_jvm`은 각각 2.367초와 0.105초였다. **스키마·Python 환경·수행 단계가 다르므로 SQLite 구축·최신성 검사까지 포함한 위 표와 직접 비교하거나 일반적인 속도 순위로 해석하지 않는다.**

Graphify raw는 10,990 nodes / 32,201 edges / 3,972 calls, built graph는 10,990 / 24,743 / 3,877이었다. raw의 dangling endpoint 6,275개는 build에서 제외됐다. 관계 쌍도 NetworkX `DiGraph`로 병합된다. 따라서 더 많은 raw edge가 더 높은 탐색 정확도를 뜻하지 않는다. cold/warm raw 및 built JSON은 각각 byte-identical이었다. [Graphify graph build](https://github.com/Graphify-Labs/graphify/blob/3f82bf7f837a07fb0f7668fbdbd5662801906942/graphify/build.py#L1210)

양쪽 parser는 같은 Kotlin 파일 10개에서 복구 진단을 냈다. Graphify는 cache에 이를 남기지만 top-level `failed_sources=[]`이고, 그중 6개만 경고 출력 기준에 해당했다. Columbus는 partial 진단을 결과에 유지한다. 이번 실험은 Graphify의 문법 지원이 더 완전하다는 근거가 아니다. [Graphify parse 경고](https://github.com/Graphify-Labs/graphify/blob/3f82bf7f837a07fb0f7668fbdbd5662801906942/graphify/extract.py#L6451)

## 다른 도구에서 참고할 점

Graphify는 파일별 AST 캐시와 조회용 graph context를 분리하고, graph 파일 변경 시 조회 캐시를 갱신한다. 이것은 원본 저장소가 색인과 같은지 검사하는 Columbus의 자동 refresh와 다른 최신성 계약이다. 캐시 분리 구조는 참고하되 검사 비용을 없애고 동일한 보장을 한다고 주장해서는 안 된다. [Graphify cache](https://github.com/Graphify-Labs/graphify/blob/3f82bf7f837a07fb0f7668fbdbd5662801906942/graphify/cache.py#L428), [조회 context](https://github.com/Graphify-Labs/graphify/blob/3f82bf7f837a07fb0f7668fbdbd5662801906942/graphify/serve.py#L112)

추가로 GitNexus commit `506432017fcf4321b7eb51ffa0db001a2014312a`의 소스만 검토했다. parse chunk 재사용과 전체 관계 재연결, 별도 `METHOD_IMPLEMENTS`/`METHOD_OVERRIDES`/`INJECTS` 단계는 구현 후보 탐색의 참고점이다. GitNexus를 이 입력에 실행하지 않았으므로 정확도·성능 우열은 측정하지 않았다. 현재 backend 명칭은 LadybugDB다. [구조 문서](https://github.com/abhigyanpatwari/GitNexus/blob/506432017fcf4321b7eb51ffa0db001a2014312a/ARCHITECTURE.md), [MRO](https://github.com/abhigyanpatwari/GitNexus/blob/506432017fcf4321b7eb51ffa0db001a2014312a/gitnexus/src/core/ingestion/pipeline-phases/mro.ts#L1), [DI](https://github.com/abhigyanpatwari/GitNexus/blob/506432017fcf4321b7eb51ffa0db001a2014312a/gitnexus/src/core/ingestion/pipeline-phases/di.ts#L24)

요청의 “gravity”는 정확한 저장소가 확인되지 않았다. 확인한 `gravity-ui/graph`는 Canvas/React 시각화 라이브러리이므로 코드 분석 엔진과 혼동하지 않았다. GitNexus를 “gravity”라고 단정한 것도 아니다. [Gravity UI Graph](https://github.com/gravity-ui/graph)

## 재실행·호환성

```sh
.venv/bin/python evals/real-repository/compare.py \
  --repo /absolute/path/to/source \
  --baseline /absolute/path/to/frozen-columbus \
  --candidate "$PWD" \
  --output "$PWD/.columbus/comparison-NEW" \
  --query fully.qualified.Controller.method --samples 3
```

[compare.py](compare.py)는 명령·stdout/stderr·wall time·macOS peak RSS·DB 크기·실제 UTF-8 cache bytes를 기록한다. 실행 전후 engine hash와 대상 Git 상태를 비교하고, 모든 sample의 path/content-hash 목록 일치, SQLite 무결성, snapshot/auto 검색 parity, 변경 없는 hash/parse/relink 0을 검사한다. 원본 앱·빌드·서비스는 실행하지 않는다.

새 엔진은 기존 TEXT 캐시를 읽고, analyzer fingerprint가 달라지면 재색인한다. 새 BLOB을 예전 엔진이 읽을 수 있다는 보장은 없다. 다운그레이드 시 별도의 새 `--db`로 색인한다. schema는 같아도 내부 캐시 형식은 바뀌었다. 기존 SQLite는 빈 페이지를 유지할 수 있어 새 DB와 같은 파일 크기로 즉시 줄지 않는다. 자동 `VACUUM`은 하지 않는다. 새 제품 의존성은 추가하지 않았다.

## 검증과 남은 범위

- 고정된 원문/DB 대조 27/27: 선정 관계, 기존 호출, 소스 hash·위치, 구현 후보, 리소스 선언, 입력 불변성.
- 선정 리소스 11개: HTTP 4개와 table 1개는 원문과 일치하는 literal, cache 3개는 표현식을 보존한 dynamic, Kafka 3개는 긴 annotation 잘림을 표시한 incomplete. 실제 활성 consumer나 구독을 확인한 것이 아니다.
- 로컬 엔진 322 tests, 설치 50 tests, 관측 harness 90 tests 통과. byte/token 예산·pagination·이전 cache·잘림·shadowing·overload·동시 수정 보호를 포함한다. compileall, pip check, diff whitespace 검사를 통과했다. 별도 lint/type checker는 저장소에 구성돼 있지 않다. OS/Python 배포 결과는 [PR #47](https://github.com/ch4570/columbus/pull/47)의 CI에서 확인한다.
- Chrome 1440×1000 / 390×844: 실제 기본 파일 그래프의 검색·선택·필터·근거·빈 검색·구분 라벨·선택 노드 중앙 표시. 합성 그래프의 keyboard·resize·동명 suffix도 확인했다. JS 오류/HTTP 요청 0. 실제 화면도 검사했으며 큰 그래프의 주변 노드에는 계속 스크롤이 필요하다.
- 단일 파일 변경 뒤 전체 재연결, 초기 색인 시간, 컴파일러·runtime 분석, 외부 Spring Data API, meta-annotation, 긴 annotation의 완전한 해석은 남아 있다. #6/#8을 이 수정만으로 완료 처리하지 않는다.

공개 자료에는 집계·소스 링크·합성 회귀 테스트만 포함한다. 비공개 원본의 커밋·경로·심볼·소스·그래프·스크린샷·전체 로그는 ignored 로컬 산출물이다. live Spring/DB/Kafka/OpenSearch, 실제 모델 토큰·과금, private corpus의 Windows/Linux 실행과 실제 모바일 기기 검증은 범위 밖이다.
