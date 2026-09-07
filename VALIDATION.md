# RepoAtlas 0.5.0 검증 기록

2026-09-07, macOS arm64에서 실행했습니다. 로컬 소스와 배포 파일의 검증이며 PyPI·GitHub Release 공개 또는 원격 CI 통과를 뜻하지 않습니다.

## 자동 테스트

| 범위 | 실행 결과 | 확인한 계약 |
| --- | --- | --- |
| 엔진 | **161개 통과** | 파싱·검색·그래프·증분 색인·소스 최신성·MCP·컨텍스트 |
| 설치·배포 | **39개 통과** | 부트스트랩·관리 파일 충돌·체크섬·재현 가능한 ZIP |
| 관측 하네스 | **8개 통과** | 사용량·캐시 계산·인용 근거·실험 고정·현재 DB preflight |
| 합계 | **208개 통과, 건너뜀 0개** | 모델 호출 없이 실행하는 회귀 검사 |

```sh
python -m unittest discover -s tests -v
# skills/repoatlas-jvm/scripts 디렉터리에서:
python -m unittest discover -s tests -v
# 다시 저장소 루트에서:
python -m unittest discover -s evals/exploration -p 'test_*.py' -v
python scripts/observe_delivery.py
```

엔진 검증에는 optional MCP SDK를 설치했습니다. 실제 stdio initialize, 7개 도구 발견과 호출, 인자 오류를 확인했습니다. SDK가 없는 환경에서 발생한 skip은 MCP 검증으로 간주하지 않습니다. CI도 해당 SDK를 명시적으로 설치하도록 구성했습니다.

## 회귀로 확인한 동작

- `repoatlas`만 실행하면 사용 가이드를 보여주며 색인을 만들지 않습니다. `explore`는 기본 text/2,000 추정 토큰으로 지도 또는 관련 소스를 반환합니다. 명시한 예산은 기본값을 대체합니다.
- `--session NAME`은 receipt/telemetry 경로를 자동으로 선택하고 `stats NAME`은 DB 없이도 로그만 읽습니다. 경로 탈출·symlink·장치 예약 이름·파일 충돌을 거부합니다.
- Python-only 설치기는 체크섬·설치 버전·실제 venv 경계를 확인하고 정상 상태를 확인한 뒤 launcher를 바꿉니다. 중단된 관리 환경의 재실행, 기존 명령 보존, 일반 파일의 외부 hard link, Python 3.14 표준 symlink, pip 설정 격리를 검사했습니다.
- 릴리스 준비는 태그·패키지·스킬 번들·standalone installer의 기본 버전이 모두 같은지 검사합니다. 잘못된 기본 버전은 자산 생성 전에 거부합니다.
- JSON 기본 출력을 유지하면서 6개 조회 명령의 text 출력을 지원합니다. JSON/text 모두 최종 렌더링 결과, 한글, 메타데이터, 잘림 표시를 포함해 바이트 예산을 검사합니다.
- Receipt는 실제 전달한 문자 범위만 기록합니다. 부모·자식의 겹치는 범위, 긴 함수, 한글 긴 줄의 일부를 다시 보내지 않고 나머지를 이어 읽습니다.
- 원본 바이트와 디코딩 후 소스 뷰의 두 해시가 맞아야 이전 범위를 재사용합니다. 파일은 그대로이고 언어 설정만 바뀐 경우도 검사합니다.
- 긴 함수·클래스의 검색 일치점을 먼저 발췌하되 다른 선언의 범위를 침범하지 않습니다. 정확한 이름 검색은 헤더를 유지하고 receipt는 앞뒤의 읽지 않은 범위를 소진합니다. 수정 전 누락을 재현한 뒤 회귀 테스트 4개를 추가했습니다.
- Telemetry는 명시한 로컬 JSONL 파일에만 쓰며 실제 stdout 바이트와 집계가 일치합니다. 원문·검색어·소스 경로를 기록하지 않고, 잘못된 기존 파일과 symlink를 보존합니다.
- 사용자가 명시한 루트가 상위 Git 저장소에서 무시되는 경우 빈 색인 대신 파일 시스템 탐색으로 전환합니다. 선택한 Git 루트의 일반 ignore 동작은 유지합니다.
- 관측 하네스는 소스·질문·엔진 해시와 설정 일치를 확인합니다. 모델 호출 직전에 현재 SQLite의 존재·루트·revision·개수를 검사하며, DB를 삭제한 회귀 사례에서 모델 프로세스가 시작되지 않았습니다.

기존 JVM 오버로드·shadowing·호출 후보, 다언어 선언과 보수적 receiver 처리, 문자열·주석 오인 방지, custom 언어·미지원 UTF-8 파일, 비밀 파일·바이너리·symlink 제외, 증분·삭제·설정 변경·worktree, 그래프 escaping과 dangling edge 검사도 통과했습니다.

## 설치 패키지

**Python 3.11.14와 3.14.7 각각의 새 가상환경**에서 같은 0.5.0 wheel과 소스 ZIP을 검사했습니다. 미리 준비한 parser wheelhouse만 사용한 오프라인 설치입니다.

```sh
python -m pip wheel --no-deps --wheel-dir dist .
python scripts/build_bundle.py
python scripts/verify_distribution.py \
  --wheel dist/repoatlas-0.5.0-py3-none-any.whl \
  --bundle dist/repoatlas-0.5.0.zip \
  --wheelhouse /absolute/path/to/wheelhouse --offline
```

| 확인 항목 | 결과 |
| --- | --- |
| 새 환경과 무관한 작업 디렉터리, 공백 포함 경로 | 통과 |
| 인자 없는 가이드·explore 기본 예산·작업별 세션·stats | 통과 |
| Python-only 전역 설치·반복 설치·launcher 실행 | 통과 |
| 전역 CLI·다언어·custom 선언·미지원 텍스트 검색 | 통과 |
| JSON/text 컨텍스트와 텍스트 지도 예산 | 통과 |
| 설치본 receipt 이어 읽기·telemetry stdout/합계 일치 | 통과 |
| JSON·Mermaid·GraphML·HTML 그래프 생성 | 4종 통과 |
| 변경 없는 sync | 재파싱·재해싱 없음 |
| Skill 설치·재설치·관리 파일 SHA-256 | 37파일 검사, 재설치 noop |
| 로컬 수정 후 재설치 | 덮어쓰기 거부, 수정 보존 |
| Wheel 강제 재설치 후 CLI·리소스 | 통과 |
| ZIP 초기 설치·반복 설치·Kotlin 초기 색인 | 통과 |
| ZIP 원본 디렉터리 이동 후 설치본 단독 실행 | 통과 |
| ZIP 전체 inventory·각 파일 SHA-256·고정 timestamp | 통과 |

설치 검증 후 이 기록과 최종 체크섬을 갱신합니다. 최종 ZIP은 설치 검증한 번들과 실행 코드·설치 리소스가 같은지 대조하고, 전체 파일 해시와 재현성을 다시 검사합니다. Wheel은 실행 코드의 복사본을 중첩해 넣지 않고 설치 시 필요한 스킬 리소스를 복원합니다.

최종 배포 파일과 체크섬은 `dist/`에 있습니다. `scripts/release_assets.py`가 wheel·ZIP·standalone installer의 배포 체크섬을 만듭니다. 루트 `SHA256SUMS.txt`는 현재 배포 대상 소스의 inventory이며 자기 자신을 포함하지 않습니다.

## Linux 컨테이너 검증

GitHub 호스팅 작업이 시작되지 않아 로컬 Rancher Desktop의 Linux aarch64 컨테이너로 추가 확인했습니다. 입력은 소스 ZIP과 wheel이며 호스트 인증 정보는 전달하지 않았습니다. 실행 후 두 검증 컨테이너는 제거했습니다.

| 환경 | 테스트 | 설치·배포 검증 |
| --- | --- | --- |
| Linux aarch64 · Python 3.11.16 | 208개 통과 | wheel·ZIP·standalone·세션·stats 통과 |
| Linux aarch64 · Python 3.14.7 | 208개 통과 | wheel·ZIP·standalone·세션·stats 통과 |

처음 3.11 컨테이너의 OS 패키지 설치가 중단되어, 다운로드 재시도·시간 제한을 설정한 새 컨테이너에서 실행했습니다. 완료하지 못한 준비 작업을 테스트 성공으로 세지 않습니다. 이미지 digest, 실제 환경 버전, 검사 결과와 검증한 코드 해시는 [구조화한 검증 기록](docs/validation/0.5.0.json)에 보관합니다. Windows 네이티브 검증을 대신하는 결과는 아닙니다.

## 실제 관측과 문서

[관측 보고서 원본](docs/token-efficiency.md)과 [오프라인 HTML](docs/report.html)에 결과를 공개했습니다. 같은 28개 지도 항목은 JSON 6,639바이트, text 3,535바이트로 **46.8% 감소**했습니다. 동일 context를 세 번 요청한 전체 응답은 receipt 사용 시 **53.5% 감소**했고, 마지막 소스 본문은 0바이트였습니다. 이는 모델을 호출하지 않은 CLI 측정입니다.

실제 Codex 탐색은 같은 소스·모델 요청·reasoning 설정으로 **3개 질문 × 2조건, 6회** 실행했습니다. 두 조건의 인용 검사가 모두 통과한 한 쌍에서는 누적 입력 토큰이 **34.0% 증가**했습니다. 다른 두 쌍의 baseline 답변에는 연속 인용 대신 생략 부호가 있어 동일 품질 절감 비교에서 제외했습니다. 초기 빈 색인 문제로 제외한 5회도 별도 보존합니다. 모델 토큰·요금 절감을 입증했다는 주장은 하지 않습니다.

공개 관측값은 로컬 원본의 사용량·명령 수·출력량·이벤트 해시와 대조했습니다. 재현 하네스는 당시 소스와 엔진 ZIP을 보존합니다. 그 뒤 보완한 긴 함수 발췌와 탐색 안내의 모델 효과는 별도로 측정하지 않았습니다.

Python 3.11 문법 검사, compileall, pip check와 Markdown 내부 링크 검사를 통과했습니다. 설치기 회귀 20개는 Python 3.11·3.14에서 각각 통과했으며, 실제 3.14 venv에서 의존성 설치 실패 → 같은 경로 재실행 → no-op를 확인했습니다. 공식 스킬 quick_validate는 로컬 검사 환경의 PyYAML 부재로 실행하지 못했으며 통과로 표시하지 않습니다. 별도 lint/typecheck 도구 설정이 없어 새 검사 의존성을 추가하지 않았습니다. HTML은 원격 자원 없이 본문·표·한글을 렌더링하며, 원본 사본과 HTML 해시는 `docs/artifact-manifest.json`에 기록합니다. `docs/source.md`는 publisher가 만든 원본 사본이고, 편집할 문서는 `docs/token-efficiency.md`입니다.

## 남은 범위

- GitHub Actions의 [첫 실행](https://github.com/ch4570/repo-graph/actions/runs/34094599664)은 계정 결제 실패 또는 사용 한도 제한으로 6개 작업 모두 step 실행 전에 차단됐습니다. 코드 테스트 실패나 통과로 해석하지 않습니다. Windows 검증은 실행하지 못했습니다. 계정 결제 설정과 저장소 공개 범위는 변경하지 않았습니다.
- Python·Java·Kotlin 외에는 heuristic 또는 text 수준이며 모든 언어의 타입·동적 호출·매크로를 증명하지 않습니다.
- 작은 저장소의 코드 위치 질문 세 개를 한 번씩 비교했습니다. 대형 모노레포·장기 구현·다른 모델의 토큰 효과와 성능 상한은 측정하지 않았습니다.
- Receipt는 모델의 기억을 복구하지 않습니다. 새 세션·다른 에이전트·컨텍스트 유실 후에는 새 receipt가 필요하며 동시 에이전트는 각자 파일을 써야 합니다.
- 별도 모델 토크나이저나 NVIDIA SkillEvaluator를 의존성으로 추가하지 않았습니다. 스킬 frontmatter·설치 경로·관리 파일 체크섬은 검사했지만 모든 호스트의 자동 발견을 보장하지 않습니다.

## 비공개 프리뷰 게시

사용자의 비공개 유지 지시에 따라 저장소 공개 범위를 유지하고, 이번 v0.5.0은 로컬 검증 산출물을 GitHub의 **prerelease**로 게시합니다. 자동 정식 릴리스 워크플로의 플랫폼 검증 조건은 유지합니다. 호스팅 작업이 차단된 이번 프리뷰는 그 조건을 통과했다고 표시하지 않으며, 릴리스 노트에 수동 게시와 검증 한계를 기록합니다.

차단 근거: [GitHub 작업 annotation](https://github.com/ch4570/repo-graph/actions/runs/34094599664/job/101655249074). GitHub는 계정의 결제 실패 또는 사용 한도 상향 필요로 작업을 시작하지 못했다고 보고했습니다.
