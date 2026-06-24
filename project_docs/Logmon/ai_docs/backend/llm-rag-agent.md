# 🤖 llm-rag-agent.md - AI 개발 가이드

이 문서는 Ollama 기반 로컬 LLM(Llama 3.2 1B) 및 초경량 임베딩 모델(nomic-embed-text) 연동, Chroma DB 시맨틱 검색 결합 하이브리드 RAG 챗봇 엔진 구축을 위한 AI 에이전트용 설계 지침입니다.

---

## 📝 1. 연동 기획 명세 ([Logmon-architecture.md](file:///Users/shkim/Desktop/Project/Logmon/project_docs/Logmon/human_docs/system/Logmon-architecture.md), [Logmon-db-specification.md](file:///Users/shkim/Desktop/Project/Logmon/project_docs/Logmon/human_docs/database/Logmon-db-specification.md))
* **로컬 LLM**: Llama 3.2 1B (`qwen2.5:3b`)
* **임베딩**: `nomic-embed-text`
* **엔드포인트**: `http://logmon-ollama:11434` 내부 연동 (외부 노출 불가)
* **목적**: 과거의 사용 로그 및 질문/해결 맥락을 검색하여 개발자의 과거 컨텍스트 질의에 정확하게 응답.

---

## 🤖 2. AI 개발 지침 및 설계 구조

### 🎯 목적
* N95 CPU 저전력 서버 환경에서 Context Window 부하를 방지하면서도 과거 로그 및 SQLite 통계 자료를 활용해 자연어 질문에 스마트하게 대답하는 RAG 엔진을 제공합니다.

### 📦 패키지 및 타깃 클래스 경로 구조
```plaintext
backend/
└── llm/
    ├── client.py              # Ollama API 비동기 HTTP 요청 클라이언트 및 Fallback 라우터
    ├── stats_db.py            # SQLite 통계 정보 Upsert & 최신 통계 조회 위임 모듈 (300줄 한도 분리)
    ├── rag_engine.py          # Chroma DB 검색 결과 가공 및 컨텍스트 주입 엔진
    ├── utils.py               # 상대 날짜 파서, 동적 컨텍스트 압축, 어미 치환 필터 모듈
    └── prompt_templates.py    # RAG 질의 전용 최적화 프롬프트 템플릿
```

### 🛠️ 개발 단계 (Step-by-Step 상세 로직)

#### 1단계: Ollama 비동기 통신 구현
* 외부 라이브러리 의존성을 최소화하고 N95 CPU 블로킹을 막기 위해 `httpx` 비동기 라이브러리를 활용해 Ollama API 클라이언트를 제작합니다.
* 임베딩 요청(`/api/embeddings`) 및 대답 생성 요청(`/api/generate` 또는 `/api/chat`)을 비동기로 구현합니다.
* 타겟 모델을 `qwen2.5:3b`로 지정하여 추론 병목을 최소화합니다.
* **[개선] 커넥션 헬스체크 튜닝**: Ollama 모델 Prefill 시 N95 CPU 병목으로 인한 가짜 오프라인(타임아웃 감지 오류) 상태 유입을 원천 차단하기 위해, 연결(Connect) 타임아웃을 3.0초로 연장하고 전체 읽기 타임아웃을 180초로 확보한 `httpx.Timeout(180.0, connect=3.0)` 설정을 기본 제공합니다.

#### 2단계: RAG Retrieval 파이프라인
1. 사용자의 자연어 입력("저번에 도커 컨테이너 포트 바인딩 에러 어떻게 해결했었지?")이 들어옵니다.
2. 입력값을 `nomic-embed-text`를 통해 벡터화한 뒤, Chroma DB에서 코사인 유사도가 높은 상위 3~5개의 텍스트 청크를 쿼리합니다.
3. 메타데이터(`user_key`)를 적용하여 타인의 로그 데이터가 조회되는 보안 누수를 철저히 차단합니다.
4. **[개선] 메타데이터 프리필터링 고도화**:
   - **이벤트 타입 분류**: 로그 덤프(`LOG_DUMP`) 적재 시, 각 청크의 본문 텍스트 내 키워드를 분석하여 `[error]` 등의 키워드가 있으면 `event_type` 메타데이터를 `ERROR` 또는 `WARNING`으로 분류하여 저장합니다.
   - **상대 날짜 및 기간 파싱 고도화**: "지난 N일 동안", "이틀 동안", "일주일 동안" 등의 상대적 표현을 `utils.py`에 격리 구현된 `parse_relative_datetime`을 통해 정밀하게 파싱하여 KST 기준 과거 시작 시각과 종료 시각을 안전하게 추론해 결합합니다.
   - **날짜 필터링**: 사용자 질문에 오늘 날짜 관련 검색 의도가 발견되면, KST 로컬 타임존 기준으로 오늘 00:00:00 이후에 등록된 로그만 검색할 수 있도록 `timestamp` 메타데이터 조건을 필터링 쿼리에 복합(`$and`)으로 결합하여 쿼리합니다.
   - **[추가] 쿼리 파서(Query Parser) 및 후처리 필터링**: 질문 텍스트에서 시간대 범위('5분', '30분', '오전 10시', '새벽', '어제', '일주일'), 로그 레벨('Error', 'Warning', 'Critical'), 그리고 기술 키워드('Git', 'Connection', 'DB', 'Build' 등)를 정교하게 추출하여 `query_vectors` API의 후처리(Post-filtering) 필터링에 결합해 RAG 컨텍스트 무결성을 확보합니다.
   - **[추가] Pre-stage 가드레일 필터링**: Chroma DB 쿼리를 돌리기 전(Pre-stage) 단계에서, 질문 텍스트 내에 개발/로그 관련 핵심 기술 키워드(한글/영문)가 아예 포함되어 있지 않은 경우, 즉시 `"죄송합니다. 저는 Logmon 시스템 로그 및 장애 분석 전용 AI 에이전트입니다. 개발 및 로그 관련 질문에만 답변할 수 있습니다."`를 반환하도록 설계하여 엉뚱한 로그가 유입되어 발생하는 프롬프트 오류(안티그래비티 현상)를 선제 방어합니다.
   - **가드레일 화이트리스트 확장**: 시스템 및 아키텍처 질의(예: `ollama`, `sqlite`, `db`, `로그`, `engine`, `ai`)가 비기술적 일반 대화로 오인되어 거부되는 오작동을 차단하기 위해 `DEV_KEYWORDS`에 해당 단어들을 화이트리스트로 탑재하여 상시 허용합니다.
   - **[격리] 검색 결과 없음 메시지 분리**: 가드레일은 기술 질문에만 동작하며, RAG 쿼리 및 파이썬 날짜 필터링을 거쳤으나 실제 검색 결과가 0건일 때는 `"최근 기록된 작업 로그가 존재하지 않습니다."`를 출력하도록 철저하게 격리하여 반환합니다.


#### 3단계: 프롬프트 주입 및 답변 생성
* 추출된 청크 컨텍스트와 사용자의 원본 질문을 결합하여 프롬프트를 구성합니다.
* N95 CPU 자원 보호를 위해 프롬프트 템플릿에 들어갈 Context 길이를 최대 2,000 토큰 이하로 강제 통제하며, N95 로컬 환경의 체감 속도 향상을 위해 출력 토큰을 최소화하는 숏폼 규칙을 적용합니다.
* **Window Memory**: 이전 대화 히스토리를 유지하기 위해 `backend/llm/memory.py`에서 `deque(maxlen=3)` 구조를 채택하여, 각 유저별(`user_key`)로 최대 3회 분량의 최근 대화(질문-답변 쌍)를 프롬프트에 동적으로 바인딩합니다.
* **[개선] 초경량 리랭커 도입**: 저전력 CPU(N95) 환경에서 sentence-transformers 모델 추론 시 30초 이상 지연되는 타임아웃 문제를 해결하기 위해, 환경변수 `RERANKER_TYPE` (기본값: `light`)를 지원합니다. `light` 상태에서는 단어 매칭 점수제 기반의 **초경량 룰 베이스 리랭커**를 활용하여 CPU 부하를 방지하고 연산 속도를 1ms 내외로 최적화합니다.

```python
RAG_PROMPT_TEMPLATE = """<start_of_turn>user
[System Information]
- Current Server Time (KST): {current_date}
- Target Model: Llama 3.2 1B (Strict Short-form Output)

[Identity & Restrictions]
- Role: Machine Log Summarizer.
- Strict Rule 1: NO greetings, NO explanations, NO polite endings (e.g., '~입니다', '~보입니다', '~하십시오'), NO conversation. 
- Strict Rule 2: All sentences must end in a noun or noun phrase (명사형 종결: '~함', '~발생', '~요망', '~원본]').
- Strict Rule 3: Output ONLY the defined Markdown formats based ONLY on the provided [Context].
- Strict Rule 4: If [Context] is empty, contains no logs, or the user query is unrelated to system logs (e.g., weather, food, general chat), output EXACTLY this phrase and STOP immediately: "최근 기록된 작업 로그가 존재하지 않습니다."

[Context]
{context}

[User Query]
{question}
<end_of_turn>
<start_of_turn>model
"""

COUNT_PROMPT_TEMPLATE = """<start_of_turn>user
[System Information]
- Current Server Time (KST): {current_date}

[Restrictions]
- Role: Machine Log Counter.
- Restrictions: STRICTLY NO greetings, NO explanations, NO polite endings. Output ONLY the defined Markdown format below based ONLY on the [Context].
- Ending: All sentences must end in a noun or noun phrase (명사형 종결).

[Task]
Count the relevant logs in [Context] and list them EXACTLY in the format below.

[Format]
### 📊 분석 결과
- 통계: 에러 총 [X]개 발생
- 내역:
  * [YYYY-MM-DD HH:MM:SS] [로그 메시지 원본]

[Context]
{context}

[User Query]
{question}
<end_of_turn>
<start_of_turn>model
"""
```

---

## 🚨 3. 철벽 코드 컨벤션 및 제약 조건
* **[프론트엔드 API 타임아웃 3분 정책]**: AI 백엔드와 로컬 LLM(Llama 3.2 1B)의 연산 지연 상황에서 유저가 정상적으로 대기할 수 있도록, 프론트엔드 API 클라이언트(`api_client.py`)의 챗 질의 타임아웃 제한을 **3분(180초)**으로 설정하여 유지합니다.
* **[300줄 분리 규칙]**: 프롬프트 문자열은 별도의 `prompt_templates.py`로 완벽 격리하며, 일일 통계 적재 로직은 `stats_db.py`로 분리하여 모듈의 최대 줄 수가 300줄을 넘어가지 않도록 관리합니다.
* **[CPU 부하 조절]**: Ollama 호출 시 `options` 파라미터에 `num_thread: 3` 등의 제한 값을 전달하여 N95의 4개 코어 중 1개 코어를 OS와 웹 UI용으로 양보할 수 있도록 세팅을 최적화하세요.
* **[안전 장치 (Fallback)]**: 
  - Ollama 서비스 다운, 리랭커 연산 실패, Chroma DB 장애 등 RAG 파이프라인 중 어떠한 예외 상황이 발생하더라도 SQLite fallback 메커니즘을 구동합니다.
* **[디버깅 및 파이프라인 튜닝]**:
  - **컨텍스트 다이어트**: N95 CPU 타임아웃 방지를 위해 주입되는 로그 청크 리스트 최대 개수를 3개로 제약합니다.
  - **디버깅 로그 강화**: 날짜 추출 시 파싱된 기준 시간대 범위와 필터링 후 잔여 청크 개수를 로그에 명확히 남깁니다.
  - **동적 토큰 조율 (Sliding Window)**: 최종 조립 프롬프트가 1,800 토큰 초과 위험이 있을 시 청크를 리스트에서 통째로 드롭(drop)하지 않고, 각 청크의 `RawMessage` 문자열 길이를 뒤에서부터 자르는 슬라이딩 윈도우 방식(`manage_context_token_limit`)을 구동해 토큰 한계를 맞춥니다.
  - **[신규] 데이터 전처리 Key-Value 구조화**: Chroma DB 및 SQLite에 적재 전, Key-Value 구조로 원본 메시지를 무조건 구조화하여 단일 청크 무결성을 확보합니다.
  - **[신규] Pre-computed Summary 적재 및 통계 질의 복합 카운트 바인딩**: 당일 통계를 미리 계산한 `[STATISTICS]` 성격의 요약 로그 데이터를 파이썬 단에서 별도로 생성 및 적재(`stats_db.py`)하며, 질의 시 정규식 파싱을 통해 `Llama 3.2 1B` 모델이 레벨별 수치를 명확하게 대답에 바인딩할 수 있도록 유도 힌트를 프롬프트에 주입하고, 파싱 실패 시 기본값(INFO: 0, WARN: 0, ERROR: 0)으로 치환해 주는 방어 코드를 적용합니다.
  - **[신규] SQLite Fallback 의도 기반 실제 데이터 바인딩**: Ollama 오프라인 시, 유저의 질문 의도에 맞춰 SQLite에서 실시간 통계를 추출해 반환합니다.
    * **[시간/토큰 질의 분기]** ("시간", "토큰", "사용량"): 지정 기간 동안의 사용 시간 및 토큰 누적 수치를 집계해 반환.
    * **[로그 개수/통계 질의 분기]** ("로그", "에러", "개수", "몇개"): 지정 기간 내의 에러 로그 개수를 계산하여 `"백업 장부(SQLite) 분석 결과, 지정 기간 내 발생한 에러 로그는 총 {X}개임."` 형태로 반환.
  - **[신규] Fallback 동적 날짜 조건 매핑**: Fallback 쿼리 수행 시에도 `parse_relative_datetime` 파서를 거쳐 도출된 기간 범위를 SQLite 쿼리의 `WHERE timestamp BETWEEN ? AND ?`에 바인딩하여 유저 질문의 시간대 의도에 완벽히 매칭된 결과를 반환합니다.
  - **[신규] 어미 치환 필터 고도화 및 예외 처리**: `postprocess_noun_ending` 정규식 치환에 룩비하인드 패턴을 도입하여 `안녕하세요`와 같은 일상 인사말이나 `필요`, `중요`, `보세요` 등 어미에 포함된 명사형 종결이 안녕요망 및 끊김 현상 없이 정상 보존되도록 구현합니다.
  - **[신규] Ollama 11434 포트 헬스체크 및 자동 복구**: `deploy.sh` 원격 SSH 배포 단계에 포트 11434 및 `/api/tags` REST API 헬스체크 기능을 신설하여, 응답 불능 좀비 상태 감지 시 강제 프로세스 킬(`kill -9`) 후 시스템 서비스 또는 백그라운드 구동을 자동 복구하며, 복구 후 200 OK 응답이 수신될 때까지 대기(Polling)하는 견고한 인프라 안전망을 탑재합니다.
