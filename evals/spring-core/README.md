# spring-core 실제 탐색 검증 — 2026-09-07

**판정: 수정 후 심볼·소스·기본 상속 탐색에는 유용하다. 전체 호출 그래프나 비용 절감 도구로 믿기에는 한계가 크다.** 원본 Columbus `a1b44af`는 이 저장소를 색인하다 네이티브 크래시로 종료했다. 실제 사용 과정에서 확인한 크래시, Java 어노테이션 누락, 정확한 ID 검색 실패를 고쳤다. 미해결 문법·디스패치·저장 공간 문제는 별도 이슈로 남겼다.

## 대상과 방법

- 공식 [Spring Framework](https://github.com/spring-projects/spring-framework/tree/4c8c6409a27a62ab163d3b6196ad862b7c835440/spring-core)의 `spring-core` 모듈. 커밋 `4c8c6409a27a62ab163d3b6196ad862b7c835440`에 고정했다. 운영 소스뿐 아니라 테스트, JMH, 리소스를 포함한다. 다른 Spring 모듈과 JDK 의존성은 색인에 없다.
- macOS arm64, CPython 3.11.16, tree-sitter 0.26.0 / Java 0.23.5 / Kotlin 1.1.0. Spring 빌드·테스트 코드는 실행하지 않았다.
- 이 작업의 에이전트가 실제 CLI로 탐색하고 원본 소스를 대조했다. 재현용 [observe.py](observe.py)는 같은 명령과 소스 검사를 자동화한다. 별도 모델 A/B 실험이나 정답 추론 정확도 실험은 아니다.
- 초기 색인은 매번 새 SQLite DB로 3회 실행했다. OS 캐시는 비우지 않았고 공유 호스트 부하도 통제하지 않았다. 이후 탐색은 `--snapshot`으로 저장된 그래프를 읽는다. 기본 자동 동기화 비용은 변경 없는 sync 항목에 따로 측정했다.
- 파일 1개 변경 실험은 `DefaultResourceLoader.java`에 주석을 추가한 후 `finally`에서 원본 바이트를 복구하고 재동기화했다. [파일 해시](results/2026-09-07/source-sha256.json)를 보존했다.
- [최종 원본 측정](results/2026-09-07/summary.json), [ID 수정 전 관측](results/2026-09-07-before-id-fix/summary.json), [원본 크래시 기록](results/crash/). ID 수정 전 관측은 이미 크래시·어노테이션 수정이 적용된 중간 단계다. 원본 제품의 성공한 baseline으로 해석하면 안 된다. 초기 harness에서 `impact --kinds`를 잘못 사용한 불완전 실행은 결과 비교에서 제외하고 올바른 명령으로 다시 실행했다.

## 얼마나 드는가

| 항목 | 최종 실측 |
| --- | ---: |
| 색인 파일 / 소스 | 1,166개 / 7,120,331 bytes (6.79 MiB) |
| 심볼 / 관계 | 20,811개 / 34,314개 |
| 초기 색인 CLI 중앙값, 범위 | **5.24초**, 5.12–5.34초 |
| 변경 없는 sync CLI 중앙값, 범위 | **1.12초**, 1.04–1.15초 |
| 변경 없는 sync 파싱 / 해싱 | 0개 / 0개 |
| 파일 1개 수정 후 sync | **4.58초**; 1개 파싱·해싱, 전체 관계 재연결 |
| SQLite 크기 | **199,421,952 bytes (190.18 MiB)**; 소스의 약 28배 |
| 별도 메모리 측정 최대 RSS | **286,949,376 bytes (273.66 MiB)**; `/usr/bin/time -l`, 해당 실행 6.91초 |
| snapshot 검색·소스·관계 CLI | 약 0.07–0.20초 (개별 관측, 반복 통계 아님) |
| 일반 `rg` + 해당 메서드 범위 읽기 | 0.053초 합계 / 출력 1,112 bytes |
| Columbus 검색 + `symbol` JSON | 0.275초 합계 / 출력 12,722 bytes |
| 정확한 ID의 첫 bounded context | 0.123초 / 5,388 bytes; 요청한 메서드가 첫 항목 |

색인과 재현 harness 자체의 LLM/API 호출은 **0회, 모델 청구액 $0**이다. 이 대화의 에이전트 사용료, 컴퓨터 비용, 네트워크 비용은 포함하지 않았다. 실제 모델 토큰·금액은 측정하지 않았고 CLI의 `bytes/3` 추정량과 구분한다. 알려진 파일·메서드를 읽는 작은 작업에서는 이번 `rg` 경로가 더 빠르고 출력도 작았다. 따라서 모델 토큰이나 전체 비용이 줄었다고 주장할 근거는 없다.

`sync`는 약 99.5 KB의 전체 inventory 메타데이터를 출력한다. `impact`도 기본 한도에서 40,014 bytes였다. 모든 명령이 2,000 토큰 예산을 공유하는 것은 아니다. 에이전트는 초기 sync 출력을 파일에 보관하고 필요한 수치만 읽으며, 소스 전달에는 bounded `context`/`explore`를 사용하는 편이 적절하다.

## 탐색 케이스와 판정

| 질문 / 검사 | 결과와 근거 |
| --- | --- |
| 모듈 전체를 실제로 색인할 수 있는가? | 원본 **실패(SIGBUS)** → 수정 후 새 DB 3회 성공. 작은 기존 JVM 테스트 14개로는 실패를 잡지 못했다. |
| `AliasFor`의 정확한 선언과 속성을 찾는가? | 원래 선언 0개 → 첫 검색 결과가 `AliasFor.java:182`의 annotation interface. `value`, `attribute`, `annotation`을 소유 타입 아래 추출하고, 들어오는 import 6개 확인. |
| `DefaultResourceLoader.getResource`의 분기 로직을 찾는가? | qualified-name 검색 첫 항목으로 적중. `symbol`이 원본 154–185행과 연속으로 일치. 프로토콜 처리, `/`, `classpath:`, `classpath*:`, URL, 경로 fallback 분기를 확인. |
| 검색에서 받은 ID를 context에 복사해도 같은 메서드를 주는가? | 수정 전 필드·다른 메서드가 먼저 나와 **실패**. 수정 후 첫 항목이 요청한 메서드이며 classpath 분기를 포함. |
| 리소스 생성 호출을 따라가는가? | `getResource` → `ClassPathResource`, `ResourceUtils.toURL` 등 실제 소스의 관계를 찾았다. 생성 호출의 대상은 클래스이며 생성자 오버로드 선택을 증명하지 않는다. |
| 상속을 여러 단계 따라가는가? | `ClassPathResource` → `AbstractFileResolvingResource` → `AbstractResource` → `Resource`, 소스 47/46/48행과 대조해 3-hop 연결 확인. |
| 역방향 영향과 공유 그래프를 볼 수 있는가? | `impact` 실행 성공, JSON/HTML/Mermaid/GraphML 내보내기 성공. 이 작업은 bounded 출력이며 완전한 런타임 영향 분석이 아니다. |
| 같은 소스를 반복 전달하지 않는가? | 세 receipt 응답의 6개 소스 범위가 겹치지 않고 각 응답이 6,000-byte 예산 이내. 첫 응답이 올바른 메서드라는 검사를 별도로 추가했다. |
| 변경 감지가 비용을 줄이는가? | unchanged 파싱·해싱 0개, 한 파일 수정 시 1개. 그래도 전체 relink 때문에 수정 처리 시간은 초기 색인과 크게 다르지 않다. |
| 모든 호출을 그래프로 설명할 수 있는가? | **아니다.** 68,007개 추출 reference 중 13,027개(19.16%)만 resolved. `protocolResolver.resolve`는 loop scope로 미해결이며 실제 분기 이해에는 소스가 필요하다. |
| 최신 문법을 모두 읽는가? | **아니다.** Java 운영 파일 5개와 Kotlin 테스트 2개가 partial. 이 한계가 계속 표시되는 것을 검사했을 뿐, 해결됐다는 pass가 아니다. |

자동 검사는 **22개 assertion 통과**다. 이는 위 탐색 시나리오의 계약 검사이며, 22개의 독립적인 질의 정답률이나 그래프 전체 정확도를 의미하지 않는다.

반복 context의 최종 출력 합계는 receipt 사용 **16,847 bytes**, 미사용 **15,945 bytes**로 오히려 **5.7% 증가**했다. receipt는 미전달 범위를 계속 가져와 서로 다른 소스 2,805 → 2,967 → 3,084 bytes를 반환했고, 미사용은 같은 내용을 반복했다. 세 번 만에 전체 후보를 소진한 것은 아니다. 중복 억제는 확인했지만 응답량·모델 토큰 절감은 확인하지 못했다.

## 그래프에 실제로 들어 있는 것과 빠진 것

관계 구성은 contains 19,644 / calls 12,506 / imports 1,759 / inherits 405이다. reference resolved 수와 edge 수는 같은 지표가 아니다(중복 제거 및 서로 다른 언어 추출기 등). 19.16%는 추출된 reference의 해결 비율이며, 외부 라이브러리와 런타임 전체를 정답으로 삼은 recall이나 precision이 아니다.

주요 미해결 이유는 복합·this/super receiver 18,192개, overload·외부·모호한 선언 17,312개, 외부/알 수 없는 receiver 7,927개, lambda/loop/catch scope 7,109개, generic receiver 2,315개다. 정확하지 않은 관계를 꾸며 넣는 대신 unresolved로 두는 보수적 정책이다. 하지만 에이전트가 여기서 탐색을 중단하면 호출 경로를 놓친다.

`ResolvableType`, `ClassUtils`, `MethodInvoker`, `ObjectUtils`, `ReflectionUtils`는 `int @Nullable ... indexes` 같은 합법적 annotated varargs에서 pinned Java grammar가 recovery를 낸다. 해당 partial 파일의 outgoing reference 1,117개는 해석을 포기하고, target 후보에서도 partial 선언이 배제된다. `AliasFor` 사용과 import 관계는 annotation 의미 분석이나 alias 충돌 해석을 대신하지 않는다.

[실제 HTML 그래프](results/2026-09-07/resource-graph.html)는 다운로드 후 브라우저에서 열 수 있다. 이 그래프는 `ClassPathResource` 중심 2-hop, 최대 100개 노드로 제한했다. [JSON](results/2026-09-07/resource-graph.json)의 truncation과 confidence도 함께 확인해야 한다.

## 이슈와 개선

| 이슈 | 처리 |
| --- | --- |
| [#2 네이티브 크래시](https://github.com/ch4570/columbus/issues/2) | native Point `.row` 접근을 없애고 UTF-8 byte offset과 newline index로 행을 계산. Java/Kotlin 300행 이상·CRLF·한글·반복 GC subprocess 회귀 검사. |
| [#3 annotation 선언 누락](https://github.com/ch4570/columbus/issues/3) | annotation interface와 element method를 AST로 추출. 중첩 선언·기본값·import·주석/문자열 음성 사례 검사. |
| [#5 정확한 ID 검색 실패](https://github.com/ch4570/columbus/issues/5) | 이름 검색에 앞서 정확한 ID를 직접 선택하고 source excerpt에도 적용. 긴 경로·200개 잡음 선언·overload·path/language filter 회귀 검사. |
| [#4 문법·디스패치 한계](https://github.com/ch4570/columbus/issues/4) | **미해결 후속 이슈.** 새 grammar/범위 해석에는 별도 정확도 검증이 필요하다. |
| [#6 DB 크기·sync 비용](https://github.com/ch4570/columbus/issues/6) | **미해결 후속 이슈.** 28배 저장 공간과 전체 relink 비용을 명시하고 같은 corpus 기준 개선 조건을 등록했다. |

크래시 원인 분석은 pinned upstream [point.c](https://github.com/tree-sitter/py-tree-sitter/blob/v0.26.0/tree_sitter/binding/point.c)의 getter가 borrowed reference를 반환하는 구현과, 기존 코드에서 재현되는 subprocess 크래시 및 수정 후 생존을 근거로 했다. 의존성 버전 변경이나 예외를 숨기는 방식은 사용하지 않았다.

## 재현

Python 3.11 이상을 명시적으로 선택한다. 이 머신의 기본 `/usr/bin/python3`는 지원 버전보다 낮아서 초기 설치가 실패했고, `python3.11`로 환경을 다시 만든 뒤 정상 설치했다.

```sh
python3.11 -m venv .venv
.venv/bin/python -m pip install -e '.[mcp]'
git clone --filter=blob:none --sparse https://github.com/spring-projects/spring-framework.git /tmp/spring-framework
git -C /tmp/spring-framework sparse-checkout set spring-core
git -C /tmp/spring-framework checkout 4c8c6409a27a62ab163d3b6196ad862b7c835440
.venv/bin/python evals/spring-core/observe.py \
  --repo /tmp/spring-framework/spring-core \
  --output /tmp/spring-core-new-observation
```

결과 디렉터리가 이미 있으면 덮어쓰지 않는다. `--baseline-db`는 크래시만 수정한 중간 snapshot의 annotation 검색 비교용 선택 인자다. DB 190 MiB 자체는 배포하지 않고 소스 해시, 명령, 응답, 엔진 fingerprint, 측정값을 보존한다. 중간 ID 수정 전 실행의 pass 수는 올바른 대상 확인 검사가 없었으므로 최종 pass 수와 직접 비교할 수 없다.

로컬 검증: root 49개, engine 172개, 기존 exploration harness 12개 테스트 통과. 추가 배포 검증·원격 CI·머지 상태는 연결된 PR의 기록을 따른다.

이 디렉터리의 Spring 코드·문서 발췌는 원본 Spring Framework의 Apache License 2.0 적용을 받는다. [라이선스 사본](SPRING-LICENSE.txt). Columbus 실험 코드의 라이선스는 저장소 루트 LICENSE를 따른다.
