# Columbus 1.0.0 벤치마크

Columbus 1.0.0에서 CLI 출력과 증분 색인을 새로 측정했습니다. 실제 모델 입력 토큰 그래프는 **RepoAtlas 0.4.0 당시의 실험**입니다. 모델 실험을 1.0.0 결과로 바꾸거나, 바이트 감소율을 토큰 절감률로 표시하지 않았습니다.

## 같은 심볼, 작은 출력

![같은 28개 심볼 지도는 JSON 6,639바이트, 텍스트 3,534바이트다. 같은 질의를 세 번 호출하면 전체 응답 합계는 receipt 없이 9,612바이트, receipt를 쓰면 4,474바이트다. Receipt의 세 번째 호출에서는 소스 0바이트와 메타데이터 333바이트를 반환한다.](../../assets/benchmark-delivery.svg)

| 비교 | 기본 동작 | 출력 최적화 | 관측 결과 |
| --- | ---: | ---: | --- |
| 같은 28개 심볼 지도 | JSON 6,639 B | 텍스트 3,534 B | 46.8% 감소 |
| `checkout` 문맥 질의 3회, 전체 응답 합계 | Receipt 없이 9,612 B | Receipt 사용 4,474 B | 53.5% 감소 |
| Receipt 사용 시 각 호출의 소스 바이트 | 1회 1,423 B | 2회 188 B → 3회 0 B | 이미 전달한 소스 재전송 억제 |

단위는 UTF-8 바이트입니다. [관측 스크립트](../../../scripts/observe_delivery.py)가 실제 CLI의 표준 출력을 캡처하고, 텔레메트리에 기록한 `output_bytes`와 일치하는지 검사합니다. 지도 비교는 동일한 ID 28개와 순서를 유지하지만, 텍스트 출력은 JSON 메타데이터 일부를 생략합니다.

실험 대상은 저장소에 포함된 `examples/polyglot-demo`입니다. 임시 디렉터리에 복사한 뒤 새로 색인했고, 파일 11개·심볼 28개·간선 25개를 확인했습니다. `.columbus`와 이전 `.repoatlas` 런타임은 fixture에서 제외합니다. 실제 복사 파일과 엔진 파일의 해시는 [delivery.json](delivery.json)에 있습니다.

지도 전체 비교에는 충분한 예산을 주고, 문맥 질의에는 매번 `--budget-tokens 2000`을 적용했습니다. 여기서 토큰 예산은 바이트 기반 추정치입니다. 동일 질의를 3회 반복했으며, receipt가 있는 조건과 없는 조건을 각각 측정했습니다. Receipt는 앞선 호출이 예산으로 생략한 소스를 다음 호출에 추가로 보여줄 수 있습니다. 세 번째 호출의 소스는 0바이트지만 메타데이터를 포함한 응답은 333바이트 남습니다. 정답률이나 모델 청구량은 이 실험에서 측정하지 않았습니다.

## 바뀐 파일만 다시 파싱

![1,001개 Python 파일에서 최초 색인 중앙값은 0.969초, 변경 없는 재탐색은 0.354초, 파일 하나를 수정한 뒤 재탐색은 0.522초다. 파싱한 파일 수는 각각 1,001개, 0개, 1개다.](../../assets/benchmark-incremental.svg)

| 색인 상태 | 파싱한 파일 | 해시를 계산한 파일 | 시간 중앙값 | 최솟값–최댓값 |
| --- | ---: | ---: | ---: | ---: |
| 빈 SQLite 색인 | 1,001 | 1,001 | 0.969214 s | 0.944158–1.022713 s |
| 변경 없음 | 0 | 0 | 0.354021 s | 0.344211–0.360925 s |
| 소스 파일 하나 수정 | 1 | 1 | 0.522079 s | 0.473352–0.672526 s |

[재현 가능한 생성기](observe_incremental.py)가 Python 파일 1,001개, 총 1,101,260바이트를 만듭니다. 색인에는 심볼 9,002개와 간선 8,001개가 생깁니다. 각 반복은 빈 SQLite 색인에서 시작하며, 같은 fixture에서 변경 없음과 파일 하나 수정 단계를 차례로 실행합니다. 위 결과는 macOS arm64·Python 3.14.7에서 단계별로 3회 측정했습니다. [incremental.json](incremental.json)에 9개 실행의 원시 측정값, 엔진 해시, 생성한 파일의 해시 목록을 요약한 해시를 담았습니다.

시간은 `RepositoryIndex.refresh` 호출 직전부터 반환 직후까지 측정했습니다. Python 시작과 fixture 생성 비용은 제외합니다. OS 캐시는 지우지 않았고, 전용 벤치마크 장비도 사용하지 않았습니다. 그래프의 오차 막대는 3회 측정의 최솟값과 최댓값이며 신뢰구간이 아닙니다. 변경 없는 탐색도 파일 메타데이터를 확인하므로 실행 비용이 0이 되지는 않습니다. 이 합성 fixture의 시간을 실제 대규모 저장소나 다른 장비의 보장 성능으로 해석하면 안 됩니다.

## 실제 모델 관측: 과거 결과를 그대로 공개

![RepoAtlas 0.4.0의 과거 모델 실험 6개. 두 조건의 인용 검사에 모두 통과한 export safety에서는 입력 토큰이 79,358개에서 106,334개로 34.0% 증가했다. 나머지 두 사례는 baseline의 인용 검사 실패를 표시하며 동등 품질의 절감 비교에서 제외한다.](../../assets/benchmark-agent-tokens.svg)

| 과거 실험 과제 | Baseline 입력 토큰 | RepoAtlas 0.4.0 입력 토큰 | 변화 | 인용 검사 |
| --- | ---: | ---: | ---: | --- |
| Export safety | 79,358 | 106,334 | +34.0% | 통과 → 통과 |
| Config invalidation | 157,482 | 138,864 | −11.8% | 실패 → 통과 |
| Managed installation | 70,775 | 88,411 | +24.9% | 실패 → 통과 |

이는 고정한 실제 소스 스냅샷에서 `gpt-5.6-sol`, `xhigh`를 요청한 Codex 0.153.4의 실행 기록입니다. 과제 3개에서 조건별 1회씩, 총 6회 실행했습니다. Baseline은 `rg`와 범위를 제한한 소스 읽기를 사용합니다. RepoAtlas 조건에는 사전 생성한 색인을 제공했으며, 당시 초기 색인 시간 1.105초는 별도로 기록했습니다. 모델 별칭은 요청한 설정이지 제공자 내부 모델에 대한 증명이 아닙니다.

입력 토큰은 실행 중 누적한 실제 usage 값이며 시작 문맥과 도구 왕복 비용을 포함합니다. 캐시 입력 토큰은 전체 입력의 부분집합이므로 다시 더하지 않습니다. 그래프의 `FAIL`은 소스 인용에 줄임표가 들어가 연속된 원문 인용 계약을 지키지 못했다는 뜻입니다. 설명한 메커니즘 전체를 이해하지 못했다는 뜻은 아닙니다.

두 조건 모두 인용 검사를 통과한 유일한 사례에서 입력 토큰이 **34.0% 증가**했습니다. 나머지 두 사례를 동등 품질의 토큰 절감 근거로 사용하지 않습니다. 단일 저장소·소수 과제·1회 관측이므로 일반적인 토큰 절감이나 요금 절감을 주장하지 않습니다. 원래의 실패한 초기 색인 실험도 기존 결과 디렉터리에 남아 있습니다.

[전체 관측 JSON](../../../evals/exploration/results/2026-09-07/controlled.json), [당시 관측 설명](../../token-efficiency.md), [기존 평가 하네스](../../../evals/exploration/README.md)를 함께 확인할 수 있습니다. 이번 릴리스 작업에서 새 모델 A/B 호출은 실행하지 않았습니다.

## 측정과 그래프 재현

저장소 루트에서 실행합니다. 아래는 POSIX 명령이며 측정용 Python 환경에는 프로젝트의 기존 파서 의존성이 필요합니다.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r skills/columbus/scripts/requirements.txt
.venv/bin/python scripts/observe_delivery.py > docs/benchmarks/1.0.0/delivery.json
.venv/bin/python docs/benchmarks/1.0.0/observe_incremental.py > docs/benchmarks/1.0.0/incremental.json
```

그래프 생성에는 별도 개발 환경에서 Matplotlib 3.11.0을 사용했습니다. Columbus 실행에는 Matplotlib이 필요하지 않습니다. 공개한 그래프의 실제 렌더링 환경은 Python 3.14.7이며, [렌더링 의존성 목록](requirements-render.txt)에 버전을 고정했습니다.

```bash
python3.14 -m venv .venv-charts
.venv-charts/bin/python -m pip install -r docs/benchmarks/1.0.0/requirements-render.txt
.venv-charts/bin/python scripts/plot_benchmarks.py
python3 -m unittest discover -s tests -p test_benchmark_charts.py -v
```

[plot_benchmarks.py](../../../scripts/plot_benchmarks.py)는 숫자를 JSON에서 읽어 SVG와 PNG를 생성합니다. 동일 지도 항목·측정 누락·중복 실험·음수 수치·비교 요약 불일치·인용 상태를 검사한 뒤 그립니다. SVG는 글꼴을 경로로 포함하고, 접근성을 위한 제목과 전체 수치 설명을 제공합니다. 축은 0에서 시작합니다. [Matplotlib의 저장 API](https://matplotlib.org/3.11.0/api/_as_gen/matplotlib.pyplot.savefig.html)로 두 형식을 생성하며, SVG의 임의 ID와 날짜 메타데이터를 고정해 같은 환경에서 같은 JSON을 다시 렌더링할 수 있습니다.

[charts.json](charts.json)은 데이터·스크립트·이미지 해시와 실제 렌더러 버전을 연결합니다. [capture.json](capture.json)은 CLI 측정 명령과 실행 환경, 관측 스크립트 해시를 기록합니다. [qa.json](qa.json)에는 PNG 검수, CairoSVG 2.9.0으로 SVG를 따로 렌더링한 검수, 결과물 6개의 바이트 단위 재현 검증을 남겼습니다. CLI 수치는 소스와 옵션이 같으면 재현할 수 있지만 색인 실행 시간은 환경에 따라 달라집니다. 그래프를 수정할 때는 JSON과 스크립트를 고친 뒤 다시 생성하고, SVG와 PNG를 렌더링해 잘림·겹침·글자·단위를 확인해야 합니다.
