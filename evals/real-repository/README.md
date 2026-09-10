# 실제 Kotlin/Spring 저장소 탐색 평가

이 문서는 **수정 전 엔진의 관측 기록**이다. 후속 수정과 동일 입력의 Graphify 비교는 [수정·비교 보고서](repairs-and-comparison.md)에 따로 기록한다. 아래 수치를 현재 엔진의 결과로 해석하지 않는다.

**코드 위치와 원문을 찾는 보조 도구로는 사용할 수 있다. 호출 경로 전체나 변경 영향의 완전성을 판단하는 근거로는 부족하다.** 2026-09-10에 비공개 다중 모듈 저장소를 Columbus로 색인하고, 세 진입점의 검색·원문·관계·반복 조회와 HTML 탐색을 실행했다.

엔진은 `06fe8079d9b5ea95deaa134b72b5434e8cc8938f`다. 버전 문자열은 1.0.0이지만, 이 관측은 해당 소스 커밋의 결과이며 v1.0.0 배포 파일의 검증이 아니다. macOS arm64, Python 3.14.7, Tree-sitter 0.26.0 / Kotlin 1.1.0 / Java 0.23.5를 사용했다.

## 측정 결과

| 항목 | 관측값 |
| --- | ---: |
| 색인 파일 | 2,742개: Kotlin 2,148, Java 91, 그 외 503 |
| 색인한 소스 | 12,799,646 bytes |
| 심볼 / 관계 | 18,023 / 25,291 |
| 관계 종류 | contains 15,214 / calls 3,836 / imports 5,546 / inherits 695 |
| 최초 색인 | 내부 12.1011초, 프로세스 wall 12.57초, 1회 |
| SQLite 크기 | 209,350,656 bytes, 소스 대비 16.36배 |
| 최대 RSS | 496,058,368 bytes |
| 변경 없는 sync | 내부 1.8627 / 1.7364 / 1.7102초, 3회 |
| 동일 sync 프로세스 wall | 2.093508 / 1.877646 / 1.856565초 |
| 동일 sync stdout | 매회 305,303 bytes |
| 스냅샷 검색·원문·관계·context | 21회, 0.091838–0.177004초 |

변경 없는 sync는 hash/parse 0개, 재연결 없음으로 확인됐다. OS 캐시는 비우지 않았으며, 최초 색인은 프로세스가 새로 시작됐다는 의미다. 파일 한 개 변경 후의 성능은 이번 평가에서 측정하지 않았다. 재실행 검증은 별도 디렉터리에 남겼으며 위 시간 표는 첫 관측에 해당한다.

## 질문별 결과와 검증 범위

| 탐색 질문 | 확인된 결과 | 한계 |
| --- | --- | --- |
| HTTP 요청에서 실행기로 이동 | 정확한 진입점이 검색 첫 결과, 원문 줄 일치, 직접 호출 연결 | 실행기 이후의 일부 인터페이스 호출 누락 |
| 기업 차단에서 저장소로 이동 | 컨트롤러 → 서비스 연결, 원문과 캐시 annotation 확인 | 외부 Spring Data 메서드와 annotation 기반 캐시 동작은 그래프로 완결되지 않음 |
| Kafka 분석 리스너에서 작업자로 이동 | 리스너 → 작업자 → registry 조회 연결 | registry 반환 객체의 후속 `process` 호출 누락, 구체 구현 선택은 동적 |

별도로 원문에서 먼저 선정한 API·저장소·이벤트 처리 관계 18개를 DB와 대조했다. 로컬 대상 호출은 **7/13**, 로컬 상속은 **1/1**이 연결됐다. 나머지 4개는 외부 Spring Data 대상이므로 로컬 호출 누락의 분모에서 제외했다. 이 표본은 세 CLI 진입점과 일부 겹치지만 동일한 집합은 아니다.

여섯 진입 클래스에서 그래프가 반환한 호출을 따라 확인한 25개 관계에서는 오연결을 찾지 못했다. 그중 3개는 인터페이스 선언을 올바르게 가리키지만 런타임 구현체는 검증하지 않았다. **선정한 작은 표본의 결과이며 전체 precision/recall이 아니다.**

추출 참조 52,672개 중 4,557개가 연결됐다. 8.65%는 추출한 참조의 연결 비율이다. 구문 복구 진단이 있는 Kotlin 파일은 10개다. 원본이 컴파일되는지, 모든 런타임 호출을 추출했는지는 이 실험으로 확인하지 않았다.

세 진입점 모두 검색과 소스 줄 검증을 통과했다. 반복 조회는 물리적 소스 범위가 겹치지 않았고, 최종 조회의 새 소스는 모두 0 bytes였다. map/context/neighbors/impact는 6,000 UTF-8 bytes 예산 이내였다. `semantic_complete=false`, unresolved 수, payload/traversal truncation을 확인했다. `search`와 `symbol`의 출력은 이 동일한 byte 예산 검증 대상이 아니다.

## 그래프와 미비점

- [#44: 파일 그래프의 투영 전 관계 제한](https://github.com/ch4570/columbus/issues/44): 기본 파일 export는 2,742개 파일과 6,221개 관계를 반환하며 `truncated=true`다. DB에 이미 있는 파일 간 관계 7,257개 중 1,036개가 누락됐다. `--kinds calls imports inherits`를 지정하면 7,257개 전부와 `truncated=false`를 확인할 수 있다. 기본 JSON/HTML/GraphML 및 Mermaid를 생성했고, Mermaid는 별도의 80-node/160-edge 렌더링 제한도 표시한다.
- [#45: Spring 경계와 구현 후보 탐색](https://github.com/ch4570/columbus/issues/45): HTTP/Kafka/JPA/cache annotation은 텍스트로 남지만 자원 관계가 아니다. 인터페이스의 구현 후보와 실제 DI 선택을 분리해 탐색할 기능이 필요하다.
- [#46: 긴 그래프 라벨과 모바일 선택 노드](https://github.com/ch4570/columbus/issues/46): 공통 경로 접두사 때문에 서로 다른 노드가 같은 라벨로 잘리고, 모바일에서 선택 노드가 화면 밖으로 잘리는 현상을 합성 그래프로 재현했다.
- [#6: 색인 크기와 변경 없는 refresh](https://github.com/ch4570/columbus/issues/6#issuecomment-5612963798): 이번 관측의 용량·시간·stdout 크기를 기존 Issue에 추가했다.
- [#8: JVM 연결과 불완전성](https://github.com/ch4570/columbus/issues/8#issuecomment-5612964477): 원문 대비 누락과 25개 호출 표본, 현재 응답의 불완전성 표시를 추가했다. 기존 오연결 사례를 해결했다고 주장하지 않는다.

수정된 관계 필터로 내보낸 2,742-node/7,257-edge HTML은 Chrome에서 검색, 노드 선택, 방향/관계 필터, 근거 보기, 빈 검색 결과, 모바일 선택을 확인했다. JavaScript 오류와 HTTP 요청은 0건이었다. 긴 공통 경로를 가진 노드는 라벨이 비슷하게 잘리고, 모바일 그래프는 가로 스크롤이 필요하다. 기능 검증 통과가 작은 화면의 가독성까지 보장하지는 않는다.

## 재실행

저장소 전용 Python 환경에 프로젝트의 기존 의존성을 설치한 뒤 실행한다. 관측 결과에는 비공개 경로와 원문이 들어가므로 Git에서 제외된 로컬 경로를 사용한다. 대상 프로젝트의 코드·빌드·서비스를 실행하지 않는다.

```sh
# 새 DB이면 최초 색인부터 실행한다. 기존 DB이면 같은 저장소인지 엔진이 확인한다.
.venv/bin/python evals/real-repository/observe.py \
  --repo /absolute/path/to/source \
  --db "$PWD/.columbus/real-eval-NEW/index.sqlite" \
  --output "$PWD/.columbus/real-eval-NEW/navigation" \
  --query fully.qualified.Controller.method \
  --query fully.qualified.Listener.method

# 공개 가능한 3-file / 20,000-declaration 재현 예제
.venv/bin/python evals/real-repository/probe_projection.py \
  --output "$PWD/.columbus/projection-NEW"
```

출력 디렉터리가 이미 있으면 중단한다. [observe.py](observe.py)는 CLI stdout/stderr, 명령·시간·출력 hash, 색인 통계, 소스/receipt/예산/무결성 검증과 파일 투영의 DB 대비 누락 수를 기록한다. 스크립트 성공은 실행·소스·예산 검증의 성공이다. `file_projections.missing`이나 의미 분석의 한계가 해결됐다는 뜻은 아니다.

[probe_projection.py](probe_projection.py)는 같은 파일의 20,000개 containment 관계가 앞에 있는 입력을 만든다. 위 수정 전 커밋에서 기본 파일 export는 3 nodes / 0 edges, 필터 적용 시 3 nodes / 2 edges다. 이 스크립트도 결함을 관측하므로 종료 코드 0만 보고 결함이 고쳐졌다고 판단하면 안 된다.

[Flow.kt](fixtures/Flow.kt)는 #45의 합성 parser fixture다. Spring 의존성을 내려받거나 애플리케이션으로 컴파일하지 않았다. 18 symbols / 22 edges / 0 unresolved로 색인되지만 Controller → Executor → UseCase에서 호출 탐색이 끝나며 `semantic_complete=false`를 반환한다. 이를 비공개 원본의 대체 정확도 검증으로 사용하지 않는다.

## 검증과 공개 범위

실제 저장소 관측의 14개 검증, 기존 엔진 234 tests, 루트 50 tests가 통과했다. 수정된 두 Python 스크립트의 컴파일과 템플릿 YAML 검증도 통과했다. 저장소에는 별도 lint/type checker가 구성돼 있지 않다.

관측 스크립트의 소스 비교는 Python 인코딩 선언, UTF-8 BOM, 물리적 줄바꿈과 byte 제한으로 잘린 마지막 줄을 처리한다. cp1252 / BOM+CRLF / 20,000-character 줄을 가진 독립 합성 입력에서도 최종 14개 검증을 통과했다. 초기 합성 실행에서 Python의 qualname에 모듈명을 잘못 붙여 발생한 검색 실패는 조회 ID를 바로잡은 뒤 재검증했다. 이는 제품 결함으로 집계하지 않았다. Git HEAD/status 비교는 이미 dirty인 파일이나 ignored 파일의 바이트 불변성을 증명하지 않는다.

공개 파일에는 집계 결과, 재실행 스크립트, 합성 fixture만 포함한다. 원본 커밋·경로·원문·그래프·스크린샷·전체 로그는 로컬에 보관했다. 원본 저장소의 HEAD와 worktree 상태는 실행 전후 같았다. live Spring/DB/Kafka/OpenSearch, MCP 전송, 모델 토큰·과금 및 일반적인 절감 효과는 이번 검증 범위에 포함하지 않았다.
