# FlowShock Web Production Guide

이 문서는 기존 웹 디자인이 마음에 들지 않을 때, 별도의 웹/앱 화면을 새로 제작하면서도 FlowShock 프로젝트의 핵심 기획, 데이터, 모델 성과, 공모전 설명 방향을 유지하기 위한 제작 가이드입니다.

## 1. 웹의 역할

최종 웹은 단순 시각화 페이지가 아니라, 심사위원이 FlowShock의 문제의식과 모델 결과를 빠르게 이해하도록 돕는 데모여야 합니다.

핵심 메시지는 다음과 같습니다.

> FlowShock는 상권의 기후 스트레스 반응을 Shock Pulse, Recovery Clock, Climate Scar, Loss Priority, Triage Score로 읽고, 취약 상권/업종을 선제적으로 지원하기 위한 의사결정 보조 시스템이다.

웹에서 반드시 전달해야 하는 흐름은 다음 순서입니다.

1. 기후 충격이 상권 매출에 영향을 줄 수 있다는 문제 제기
2. 상권을 하나의 생체 신호처럼 읽는 Climate ECG 컨셉 소개
3. Shock Pulse 모델 성능 제시
4. Recovery Clock과 Climate Scar로 취약성 해석 보강
5. Loss Priority로 지원 우선순위 제시
6. Triage Score로 최종 후보군 요약
7. 비인과, 회고적 분석, 정책 보조 도구라는 한계 명시

## 2. 반드시 유지할 프로젝트 프레임

웹을 새로 제작하더라도 아래 용어와 의미는 유지하는 것이 좋습니다.

| 용어 | 의미 |
| --- | --- |
| Shock Pulse | 기상/캘린더/상권 조건에서 큰 음의 매출 편차가 발생했는지 감지하는 핵심 예측 모델 |
| Recovery Clock | 충격 이후 회복 지연 가능성을 보는 보조 신호 |
| Climate Scar | 반복적으로 취약하게 나타나는 지역/업종의 누적 취약성 해석 |
| Loss Priority | 지원 우선순위를 정하기 위한 baseline-relative loss ranking layer |
| Triage Score | Shock risk, Recovery risk, Climate Scar를 결합한 최종 후보군 점수 |

추천 한국어 표현은 다음과 같습니다.

- Shock Pulse: `기후 충격 맥박`
- Recovery Clock: `회복 시계`
- Climate Scar: `기후 흉터`
- Loss Priority: `손실 우선순위`
- Triage Score: `지원 진단 점수`

## 3. 사용할 데이터 파일

웹은 raw CSV를 직접 읽지 않고, 이미 정리된 aggregate JSON bundle만 사용해야 합니다.

사용할 파일은 다음 2개입니다.

```text
web/public/data/flowshock_analysis_bundle.json
web/public/data/flowshock_modeling_bundle.json
```

외부에 보여줄 웹에서는 다음을 피해야 합니다.

- 원천 CSV 파일 직접 노출
- 로컬 절대경로 표시
- 개인 PC 경로 표시
- 모델을 실시간으로 새로 학습하는 것처럼 보이는 표현
- 실제 정책 결정을 자동화하는 것처럼 보이는 표현

## 4. 웹에 반드시 들어갈 주요 숫자

아래 숫자는 현재 모델링 결과 기준으로 웹/발표에서 강조할 수 있습니다.

| 항목 | 값 | 설명 |
| --- | ---: | --- |
| Shock Pulse Test F1 | 0.501 | 핵심 충격 감지 모델 성능 |
| Shock Pulse ROC-AUC | 0.784 | 양/음성 구분 순위 성능 |
| Shock Pulse PR-AUC | 0.497 | 불균형 타깃 기준 성능 |
| Shock Pulse Recall | 0.743 | 충격 사례 포착률 |
| Weather-conditioned Shock F1 | 0.449 | 기상 조건부 충격 모델 |
| Weather-conditioned Shock Top10 Recall | 0.929 | 상위 10% 후보군의 충격 포착력 |
| Loss Priority Top5 Capture | 26.6% | 상위 5% 후보군이 잡는 modeled loss 비중 |
| Loss Priority Top5 Lift | 5.30x | 무작위 대비 집중도 |
| Loss Priority Top10 Capture | 36.6% | 상위 10% 후보군이 잡는 modeled loss 비중 |
| Loss Priority Top10 Lift | 3.65x | 무작위 대비 집중도 |
| Loss Priority Top20 Capture | 44.3% | 상위 20% 후보군이 잡는 modeled loss 비중 |
| Loss Priority Top20 Lift | 2.21x | 무작위 대비 집중도 |

## 5. 추천 화면 구성

## 5-1. ECG 감성 디자인 방향

웹을 새로 만들더라도 FlowShock의 상징성은 `ECG`, 즉 심전도 느낌에서 가져가는 것이 좋습니다. 단순히 예쁜 대시보드가 아니라, 상권을 하나의 살아있는 유기체처럼 보고 기후 스트레스에 반응하는 신호를 읽는 콘셉트가 핵심입니다.

권장 분위기:

- 병원 모니터, 심전도, 진단 차트, 응급 triage board가 섞인 느낌
- 어두운 배경 위에 초록/청록 계열 ECG 라인
- 위험도나 손실 우선순위는 붉은색/주황색 포인트로 강조
- 지표 카드는 의료기기 readout처럼 짧고 강하게 표시
- `정확한 판정`보다 `진단 보조 신호`처럼 보이게 구성

첫 화면에서 바로 보여주면 좋은 시각 요소:

- 중앙을 가로지르는 ECG pulse line
- `Shock Pulse -> Recovery Clock -> Climate Scar -> Loss Priority -> Triage Score` 흐름
- 심장, 맥박, 진단 리포트, 모니터 패널 중 하나를 메인 모티프로 사용
- 핵심 수치 2-3개를 ECG readout처럼 배치

예시 카피:

```text
상권의 맥박을 읽다.
기후 스트레스가 들어온 순간, 어떤 지역과 업종이 흔들리고 늦게 회복되는지 Climate ECG로 진단합니다.
```

```text
FlowShock는 매출 감소의 원인을 단정하지 않습니다.
대신 상권의 이상 신호를 조기에 포착하고, 어디를 먼저 살펴봐야 하는지 알려주는 진단 보조 레이어입니다.
```

ECG 흐름을 화면에 표현하는 방식은 다음 중 하나를 추천합니다.

| 방식 | 설명 |
| --- | --- |
| Horizontal ECG Timeline | 심전도 라인을 따라 Shock, Recovery, Scar, Priority, Triage가 순서대로 등장 |
| Heart Diagnosis Map | 심장 모양 또는 4개 chamber에 Shock/Recovery/Scar/Priority를 배치 |
| Medical Monitor Dashboard | 좌측에는 ECG 그래프, 우측에는 핵심 지표와 위험 후보군 표시 |
| Triage Board | 응급실 우선순위 보드처럼 지역/업종 후보군을 위험도 순으로 정렬 |

디자인에서 피해야 할 방향:

- 일반적인 카드형 BI 대시보드처럼만 보이는 구성
- 지도/표/그래프가 나열되지만 FlowShock만의 상징이 없는 구성
- 실제 의료 진단처럼 오해될 정도로 과한 표현
- 원인 단정, 피해액 확정, 자동 정책 결정처럼 보이는 문구

추천 UI 문구:

- `ECG Signal`
- `Pulse Detected`
- `Recovery Delay`
- `Scar Pattern`
- `Priority Queue`
- `Triage Candidates`
- `Retrospective Diagnosis`
- `Decision Support Only`

### A. Hero

목표는 첫 화면에서 프로젝트의 상징성을 바로 이해시키는 것입니다.

포함 요소:

- 프로젝트명: `FlowShock`
- 한 줄 설명: `기후 스트레스에 흔들리는 상권의 신호를 읽고, 지원 우선순위를 제안하는 Climate ECG`
- 핵심 지표 2-3개
  - Shock Pulse F1 `0.501`
  - Top10 Capture `36.6%`
  - Quality Checks `16 passed / 0 failed`
- 한계 문구
  - `비인과적 예측/순위화 도구입니다.`
  - `현재 결과는 same-day/retrospective evaluation이며, 실제 사전 예측에는 forecast weather와 별도 검증이 필요합니다.`

### B. Problem Section

보여줄 내용:

- 기후 이벤트가 상권 매출 변동성과 결합될 수 있음
- 같은 날씨라도 지역/업종별 반응이 다를 수 있음
- 단순 평균 피해액보다 `어디를 먼저 봐야 하는가`가 정책적으로 중요함

### C. Climate ECG Section

FlowShock의 차별점입니다.

권장 표현:

```text
상권을 하나의 생체 신호처럼 본다.
날씨 충격이 들어왔을 때 즉시 흔들리는지, 회복이 늦어지는지, 반복적인 취약성이 남는지, 그리고 어디를 먼저 지원해야 하는지를 하나의 진단 흐름으로 연결한다.
```

시각화 아이디어:

- 심전도 ECG 라인
- 심장/진단 차트
- 단계형 파이프라인
- 지도 + 위험도 카드
- 병원 triage 보드처럼 우선순위 목록

### D. Model Performance Section

모델 성능을 너무 과장하지 않고, 공모전에서 중요하게 볼 수 있는 모델링 결과를 명확히 보여줍니다.

강조 포인트:

- Shock Pulse는 핵심 예측 모델
- Recovery Clock은 exploratory 보조 모델
- Loss Priority는 금액 예측이 아니라 지원 우선순위 ranking layer
- Top-k capture와 lift가 정책 활용성에 중요함

### E. Priority Ranking Section

심사위원이 가장 직관적으로 이해할 수 있는 화면입니다.

권장 테이블 컬럼:

| Rank | Region | Industry | Predicted Priority | Observed Estimated Loss | Shock Risk |
| --- | --- | --- | ---: | ---: | ---: |

가능하면 상위 5-10개만 보여주고, 상세 설명은 접거나 별도 섹션으로 분리합니다.

### F. Guardrails Section

이 섹션은 반드시 눈에 보이게 넣어야 합니다.

포함할 문구:

- `이 결과는 인과 추정이 아닙니다.`
- `기상 때문에 매출이 감소했다고 단정하지 않습니다.`
- `현재 웹은 회고적 분석 결과를 보여주는 정적 MVP입니다.`
- `실제 사전 예측에는 예보 기상 데이터와 별도 운영 검증이 필요합니다.`
- `Loss Priority의 손실은 감사된 실제 피해액이 아니라 모델링된 baseline-relative loss입니다.`
- `최종 정책 결정은 현장 맥락과 사람의 검토가 필요합니다.`

## 6. 데이터 연결 방식 예시

웹 프레임워크를 쓰지 않는다면 다음처럼 불러오면 됩니다.

```js
const DATA_PATHS = {
  analysis: './public/data/flowshock_analysis_bundle.json',
  modeling: './public/data/flowshock_modeling_bundle.json'
};

async function loadFlowShockBundles() {
  const [analysisResponse, modelingResponse] = await Promise.all([
    fetch(DATA_PATHS.analysis),
    fetch(DATA_PATHS.modeling)
  ]);

  if (!analysisResponse.ok || !modelingResponse.ok) {
    throw new Error('Failed to load FlowShock aggregate bundles');
  }

  return {
    analysis: await analysisResponse.json(),
    modeling: await modelingResponse.json()
  };
}
```

React, Next.js, Vue 등으로 새로 만들더라도 원칙은 동일합니다.

- public data bundle 2개만 fetch
- raw data import 금지
- 표시 전 숫자 포맷팅
- 없는 값은 `Not available` 또는 `N/A` 처리
- 사용자 입력을 받아 HTML에 직접 넣지 않기

## 7. 필수 검증 체크리스트

웹을 새로 만든 뒤 최소한 아래는 확인해야 합니다.

### 데이터/콘텐츠

- [ ] 두 JSON bundle만 불러온다.
- [ ] raw CSV를 직접 요청하지 않는다.
- [ ] 로컬 절대경로가 화면이나 JSON 응답에 노출되지 않는다.
- [ ] Shock Pulse F1 `0.501`이 정상 표시된다.
- [ ] Loss Priority Top10 Capture `36.6%`가 정상 표시된다.
- [ ] Quality `16 passed / 0 failed`가 정상 표시된다.
- [ ] 비인과/회고적 분석/사전 예측 별도 검증 문구가 보인다.

### UI

- [ ] 첫 화면에서 FlowShock의 목적이 5초 안에 이해된다.
- [ ] Climate ECG의 5단계가 한눈에 보인다.
- [ ] 우선지원 후보 테이블이 직관적이다.
- [ ] 모바일 화면에서 가로 스크롤이 없다.
- [ ] 표가 너무 길면 상위 5-10개만 먼저 보여준다.

### 기술

- [ ] 브라우저 console error/warning이 없다.
- [ ] 정적 서버에서 `/`, CSS, JS, 두 JSON 파일이 200으로 응답한다.
- [ ] path traversal 요청이 차단된다.
- [ ] 새로고침해도 화면이 정상 로드된다.

## 8. 발표/심사용 권장 톤

피해야 할 표현:

- `기후가 매출 감소의 원인이다`
- `피해액을 정확히 예측한다`
- `자동으로 지원 대상을 결정한다`
- `실시간 예측 시스템이다`

권장 표현:

- `기후 스트레스와 매출 반응의 aggregate association을 모델링했다`
- `취약 후보군을 조기에 선별하는 decision-support layer다`
- `지원 우선순위를 정하기 위한 ranking signal이다`
- `사전 운영에는 예보 데이터와 별도 검증이 필요하다`

## 9. 새 웹 제작 시 추천 산출물

최종적으로 아래 파일이나 자료가 있으면 제출/발표 준비가 편합니다.

- 웹 MVP 실행 파일 또는 배포 URL
- 메인 화면 스크린샷
- Climate ECG 흐름도 이미지
- 우선지원 후보 화면 스크린샷
- 모델 성능 요약 화면 스크린샷
- 한계/guardrail 화면 스크린샷
- 실행 방법 README

## 10. 한 줄 요약

새 웹은 예쁘게 보이는 것보다, `기후 스트레스 -> 상권 반응 -> 취약성 해석 -> 지원 우선순위`라는 FlowShock의 판단 흐름을 짧고 강하게 이해시키는 것이 가장 중요합니다.
