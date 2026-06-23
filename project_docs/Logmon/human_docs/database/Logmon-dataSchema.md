# Logmon Data Schema & Traceability Matrix

## 1. 개요
Logmon 서비스는 개발자의 IDE 로컬 환경에서 발생하는 로그 데이터를 수집하여, 분석 가능한 형태로 구조화(Structuring) 및 정규화(Normalization)하여 저장합니다. 
본 시스템은 외부 요인(예: GUI 기반 Git 활동)의 불확실성을 배제하고, 오직 **IDE 내부에서만 확보할 수 있는 3대 핵심 가치(코딩 몰입 시간, AI 도구 활용도, 에러/디버깅 패턴)**를 정밀하게 추적하는 데 최적화되어 있습니다.

## 2. 기본 로그 스키마 (SQLite 저장 항목)
`ide_activity_logs` 테이블에 저장되는 데이터의 핵심 필드입니다.

| 필드명 | 데이터 타입 | 설명 | 핵심 활용처 |
| :--- | :--- | :--- | :--- |
| `id` | Integer | 로그 고유 식별자 (PK) | 시스템 관리 |
| `user_key` | String | 사용자 API Key | 식별 및 필터링 |
| `source_tool` | String | 원본 IDE/도구 명칭 | 작업 환경 분석 |
| `timestamp` | String | 발생 시각 ('YYYY-MM-DD HH:MM:SS') | 타임라인 및 소요 시간 추적 |
| `event_type` | String | 로그 수준 (INFO, ERROR, WARN 등) | 에러/디버깅 세션 감지 |
| `task_name` | String | 수행 작업 단위 (Auto-Discovery 적용) | 주요 행동 패턴 분류 |
| `duration_seconds` | Float | 작업 소요 시간 | **코딩 몰입도/에러 해결 시간 계산** |
| `input/output_tokens` | Integer | LLM 토큰 사용량 | **AI 의존도 및 비용 분석** |
| `raw_message` | String | 구조화된 로그 본문 | LLM RAG 심층 추론 |
| `has_code_block` | Integer | 코드 블록 포함 여부 | 소스코드 복붙/참조 추적 |

## 3. 지능형 메타데이터 (RAG 활용)
Vector DB(Chroma) 적재 시, 검색 품질을 높이기 위해 원본에서 파생/가공되는 지능형 메타데이터입니다.

* **Source IDE**: `Cursor`, `VSCode`, `Antigravity`, `JetBrains` 등 IDE 환경 세분화
* **Log Level**: `ERROR`, `WARN`, `DEBUG`, `INFO` 규격화
* **Action Type (3대 핵심 지표 분류)**:
  * ⏱ `workspace_active`: 파일 이동, 타이핑 활성화 등 순수 코딩 세션
  * 🤖 `ai_assisted`: `loadCodeAssist`(자동완성), `fetchAvailableModels`(채팅) 등 AI 개입
  * 🚨 `debugging`: `Exception`, `Traceback`, 빌드 실패 등 에러 발생 및 해결 세션

## 4. 데이터 가공 파이프라인 흐름
1. **수집(Agent)**: IDE 환경에서 5분 주기로 `raw_message` 및 원시 메타데이터를 백엔드로 전송.
2. **자동 식별(Auto-Discovery)**: 백엔드에서 로그 본문을 분석하여 누락된 `task_name`을 복원하고 의미를 부여.
3. **구조화(SQL Backend)**: `insert_activity_log`를 통해 로그를 삽입하고 명확한 텍스트 템플릿으로 구조화.
4. **분석(LLM RAG)**: 가공된 데이터를 Vector DB 메타데이터로 적재하여, RAG 엔진이 사용자 질의에 맞춰 심층 분석 수행.

---

## 5. 유저 질문 가이드 (Use Cases)

Logmon의 AI 분석가에게는 **"시간 범위"**와 **"특정 행동"**을 조합하여 질문할수록 가장 정확한 인사이트를 얻을 수 있습니다. 아래의 예시들을 활용해 보세요!

### 💡 [질문 가이드: 이렇게 물어보세요!]

#### ⏱ 1. 순수 코딩 몰입도 & 작업 패턴 분석 (Active Coding Time)
개발자의 순수 작업 시간과 언어/파일별 점유율을 확인합니다.
> * "오늘 내가 코딩에 가장 집중했던 시간대는 언제야?"
> * "이번 주에 파이썬(.py) 파일과 타입스크립트(.tsx) 파일 중 어디에 더 많은 시간을 썼어?"
> * "어제 하루 동안 내가 가장 자주 열어본(수정한) 파일 이름이 뭐야?"
> * "최근 3일 동안 내 작업 흐름이 가장 자주 끊긴(Context Switching) 때는 언제였어?"

#### 🤖 2. AI 어시스턴트 활용 효율 및 비용 (AI & Token Metrics)
최신 AI 도구에 얼마나 의존하고 있는지, 토큰 소모량은 어떠한지 진단합니다.
> * "오늘 하루 동안 AI가 코드 자동완성(loadCodeAssist)을 해준 횟수가 총 몇 번이야?"
> * "이번 주에 내가 소모한 총 LLM 토큰(input/output 합산) 수가 얼마나 돼?"
> * "최근 24시간 동안 AI 채팅 창에 직접 질문한 횟수와, 코드를 자동완성 시킨 횟수를 비교해 줘."
> * "오늘 토큰 소모량이 가장 급증했던 시간대와 그 이유(작업 내용)를 유추해 볼 수 있어?"

#### 🚨 3. 에러 발생 지점 및 디버깅 흐름 (Error & Debugging Patterns)
가장 오랜 시간이 지연되는 디버깅 병목 구간을 시각화합니다.
> * "최근 발생한 가장 치명적인 ERROR 로그의 핵심 원인이 무엇인지 요약해 줘."
> * "오늘 하루 동안 `TypeError`가 총 몇 번 발생했어?"
> * "어제 특정 에러가 발생한 시점부터 다음 정상 로그가 찍힐 때까지, 디버깅에 대략 몇 분이나 쓴 것 같아?"
> * "최근 3일 동안 에러 로그가 가장 많이 쏟아진 파일이나 모듈이 어디야?"

#### 🖥 4. 기본 환경 및 기타 지표 (Environment)
> * "이번 주에 내가 주로 사용한 IDE는 Cursor와 VSCode 중 뭐야?"
> * "오늘 남겨진 전체 로그 건수는 총 몇 개야?"
> * *(부가 기능)* "오늘 IDE 내장 터미널을 통해서 직접 타이핑한 git commit 횟수는 몇 번이야?"

---

## 6. 시스템 운영 팁
* **정밀 필터링 추론**: 챗봇에게 *"ERROR 로그만 모아서 원인을 분석해 줘"* 라고 명시하면, LLM이 내부적으로 `event_type: ERROR` 메타데이터를 우선 검색하여 답변의 정확도를 극대화합니다.
* **데이터 클리닝 정책**: 시스템 퍼포먼스를 위해 생성된 지 7일이 지난 로그는 자동 삭제(TTL)됩니다. 주간/월간 통계가 필요할 경우, 금요일마다 *"이번 주 나의 코딩 패턴을 요약해 줘"* 라고 질문하여 별도의 문서로 기록을 남기는 것을 권장합니다.