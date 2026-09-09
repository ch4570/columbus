# Columbus 검증 기록

1.1.0 후보의 다국어·회귀 검사 결과와 한계는 [릴리스 평가](evals/release-v1.1.0/REPORT.md)에 있습니다. 최종 커밋의 플랫폼·설치 검사는 [PR #12](https://github.com/ch4570/columbus/pull/12)의 CI로 확인합니다. 아래는 1.0.0 당시 기록이며 1.1.0의 실행 결과를 대신하지 않습니다.

# Columbus 1.0.0 검증 기록

2026-09-07 · 이름 변경, 배포 경로, 기존 동작, 벤치마크의 근거 연결을 검사했습니다. 테스트 정의와 실제 실행을 구분하며, 이전 RepoAtlas 프리뷰의 검증은 [0.5.0 기록](docs/validation/0.5.0.json)에 남아 있습니다.

## 자동 테스트

macOS arm64, Python 3.14.7에서 **230개가 통과**했습니다. 건너뛴 테스트는 없습니다.

| 범위 | 통과 | 확인한 동작 |
| --- | ---: | --- |
| 엔진 | 169 | AST·휴리스틱·텍스트 탐색, 증분 색인, 응답 예산, 소스 최신성, receipt·세션·MCP·그래프 |
| 설치·패키징·벤치마크 계약 | 49 | 사용자 환경 소유권, 실패 후 재개, wheel·ZIP·버전 검증, 근거 데이터와 차트의 일치 |
| 관측 하네스 | 12 | 실제 응답 인용·사용량 검증, 새 Columbus 엔진과 보존된 이전 엔진의 구분 |

Python 3.11 문법 검사, `compileall`, 설치 환경의 `pip check`도 통과했습니다. 기존 208개 테스트를 먼저 통과시킨 뒤 이름을 변경했고, 이전 캐시 제외·과거 엔진 재현·벤치마크 계약 회귀를 추가했습니다. 별도 lint/typecheck 도구 설정은 없으며 새 런타임 의존성을 추가하지 않았습니다.

## 배포 검증

설치 검사는 source checkout 밖의 새 환경에서 수행하며, 공백이 있는 경로와 wheel·ZIP·Python-only 설치기 경로를 포함합니다. 이전 빌드의 `repoatlas` 패키지가 섞이지 않도록 새 소스 ZIP을 풀어 격리된 위치에서 wheel을 만듭니다.

- 패키지·스킬 번들·standalone 설치기·릴리스 태그의 버전 일치를 확인합니다.
- 배포 wheel의 최상위에는 `columbus/`와 해당 `.dist-info/`만 허용합니다.
- bare command 안내, `explore`, 세션 중복 제거, `stats`, polyglot 조회와 4종 그래프를 확인합니다.
- 설치한 스킬의 재설치는 no-op이며, 사용자가 수정한 관리 파일은 보존합니다.
- wheel·ZIP·설치기의 SHA-256을 만들고 릴리스 다운로드와 대조합니다.

실행된 플랫폼과 산출물의 상세 결과는 [구조화한 검증 기록](docs/validation/1.0.0.json)에 기록합니다. [GitHub Actions](https://github.com/ch4570/columbus/actions/workflows/distribution.yml)는 Ubuntu·macOS·Windows와 Python 3.11·3.14의 6개 조합을 검사합니다. 정식 릴리스 워크플로는 이 검증이 모두 성공한 뒤에만 파일을 게시합니다.

첫 공개 CI에서 Ubuntu·macOS의 두 Python 버전은 통과했고, Windows 두 버전에서 파일 상태 비교와 기본 문자 인코딩 문제가 드러났습니다. Windows의 실제 파일 변경 시각을 조회해 읽기 전·중·후 검증에 사용하고, CLI 출력은 파이프에서도 UTF-8/LF로 고정했습니다. 새 회귀 테스트에서 이전 구현이 실패하는 것을 확인했으며, 열린 테스트 DB 연결과 UTF-8 fixture도 정리했습니다. 이 수정 후 Windows 3.11을 포함한 5개 CI 조합이 설치·배포 검사까지 통과했습니다. Windows 3.14의 현재 Columbus 엔진 169개 검사도 통과했습니다. 과거 엔진의 재실행 호환성은 다음과 같이 별도로 표시합니다.

Windows에서는 POSIX 전용 인터프리터 별칭 검사 1개가 적용되지 않아 제외됩니다. Windows/Python 3.14에서는 변경하지 않고 보존한 RepoAtlas 0.4 엔진의 재실행 검사 1개도 제외합니다. 그 원본은 이전 파일 시각 처리 때문에 해당 조합에서 실행되지 않습니다. 원본 ZIP·모듈 해시 검사와 현재 Columbus 엔진·배포 검사는 계속 실행합니다. 이 재실행은 다른 5개 플랫폼 조합에서 검사하며, Windows 3.14의 실제 집계는 228개 통과·2개 제외입니다. [재현 환경 제한](evals/exploration/README.md)을 명시하고 호환되지 않는 원본 엔진 실행은 사전에 거절합니다.

## 호스팅 플랫폼 결과

[최종 플랫폼 CI](https://github.com/ch4570/columbus/actions/runs/34102393386)의 **6개 작업 모두 통과**했습니다. 모든 작업에서 테스트, wheel·ZIP 빌드, 실제 새 환경 설치·세션·그래프 출력을 실행했습니다.

| 환경 | Python | 테스트 결과 | 배포 검사 |
| --- | --- | --- | --- |
| Ubuntu | 3.11, 3.14 | 각각 230개 통과 | 각각 통과 |
| macOS | 3.11, 3.14 | 각각 230개 통과 | 각각 통과 |
| Windows | 3.11 | 229개 통과·POSIX 전용 1개 제외 | 통과 |
| Windows | 3.14 | 228개 통과·POSIX 전용 및 과거 엔진 재현 각 1개 제외 | 통과 |

현재 엔진 169개 검사와 실제 Windows 배포 검사는 모두 실행했습니다. POSIX 전용 별칭은 Ubuntu·macOS에서 검사합니다. 제외한 과거 원본 엔진은 호환 환경에서 재실행하고, 모든 환경에서 원본 바이트와 모듈 목록을 검사합니다.

## 벤치마크와 이미지

[Columbus 1.0 벤치마크](docs/benchmarks/README.md)는 새 버전에서 실행한 CLI 응답량과 1,001개 합성 파일의 증분 색인 기록입니다. 원본 JSON, fixture·엔진 해시, 재현 명령, SVG·PNG와 생성 스크립트를 제공합니다.

| 측정 | 관측 |
| --- | --- |
| 같은 지도 28개 항목 | JSON 6,639 → text 3,534바이트, 46.8% 감소 |
| context 세 번의 전체 응답 | receipt 없음 9,612 → 사용 4,474바이트, 53.5% 감소 |
| receipt로 전달한 소스 | 1,423 → 188 → 0바이트 |
| 증분 색인 파싱 파일 | 처음 1,001 → 변경 없음 0 → 하나 수정 1 |

측정 도중 발견한 이전 `.repoatlas` 캐시의 fixture 목록 혼입을 수정한 뒤 다시 측정했습니다. 최종 fixture 해시는 배포할 소스와 대조합니다.

이전 실제 Codex 실험은 [RepoAtlas 0.4.0 기록](evals/exploration/results/2026-09-07/controlled.json)을 수정하지 않고 별도 그래프로 표시합니다. 양쪽 인용이 통과한 사례에서 누적 입력은 34.0% 늘었습니다. 이를 Columbus 1.0의 새 모델 실험이나 일반적인 토큰 절감으로 표시하지 않습니다. 초기 빈 색인 실험과 인용 실패도 보존했습니다.

[배너와 캐릭터](docs/assets/columbus-art.md)는 내장 이미지 생성 도구로 제작하고 최종 파일을 시각 검수했습니다. 벤치마크 그래프는 matplotlib으로 실제 데이터에서 생성하며, 수치·0 기준축·단위·인용 통과 여부·잘림을 확인했습니다.

## 이전 설치와 한계

새 경로는 `.agents/skills/columbus/`, `.columbus.json`, `.columbusignore`, `.columbus/index-v1.sqlite`입니다. 예전 설정과 캐시는 자동 이동하지 않고 새 탐색에서도 제외합니다. [프리뷰 이전 방법](INSTALL.md#moving-from-the-repoatlas-preview)을 제공합니다.

Python·Java·Kotlin 이외의 분석 수준은 언어에 따라 heuristic·text이며, 동적 호출이나 타입을 모두 증명하지 않습니다. Receipt는 모델의 기억을 복원하지 않으므로 다른 작업·에이전트·컨텍스트 유실 후에는 새 세션이 필요합니다. 합성 파일의 시간은 해당 기계에서 측정했으며 다른 저장소의 성능 상한을 뜻하지 않습니다.

스킬 구조·관리 파일·실행 경로는 검사했습니다. 로컬 공식 `quick_validate.py`는 PyYAML 부재로 실행하지 않았고, 모든 호스트의 자동 스킬 발견이나 별도 NVIDIA SkillEvaluator 통과를 주장하지 않습니다.
