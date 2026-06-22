# 🤖 llm-rag-agent.md - AI 개발 가이드

이 문서는 Ollama 기반 로컬 LLM(Gemma 2 2B) 및 초경량 임베딩 모델(nomic-embed-text) 연동, Chroma DB 시맨틱 검색 결합 하이브리드 RAG 챗봇 엔진 구축을 위한 AI 에이전트용 설계 지침입니다.

---

## 📝 1. 연동 기획 명세 ([Logmon-architecture.md](file:///Users/shkim/Desktop/Project/Logmon/project_docs/Logmon/human_docs/system/Logmon-architecture.md), [Logmon-db-specification.md](file:///Users/shkim/Desktop/Project/Logmon/project_docs/Logmon/human_docs/database/Logmon-db-specification.md))
* **로컬 LLM**: Gemma 2 2B (`gemma2:2b`)
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
    ├── client.py              # Ollama API 비동기 HTTP 요청 클라이언트
    ├── rag_engine.py          # Chroma DB 검색 결과 가공 및 컨텍스트 주입 엔진
    └── prompt_templates.py    # RAG 질의 전용 최적화 프롬프트 템플릿
```

### 🛠️ 개발 단계 (Step-by-Step 상세 로직)

#### 1단계: Ollama 비동기 통신 구현
* 외부 라이브러리 의존성을 최소화하고 N95 CPU 블로킹을 막기 위해 `httpx` 비동기 라이브러리를 활용해 Ollama API 클라이언트를 제작합니다.
* 임베딩 요청(`/api/embeddings`) 및 대답 생성 요청(`/api/generate` 또는 `/api/chat`)을 비동기로 구현합니다.

#### 2단계: RAG Retrieval 파이프라인
1. 사용자의 자연어 입력("저번에 도커 컨테이너 포트 바인딩 에러 어떻게 해결했었지?")이 들어옵니다.
2. 입력값을 `nomic-embed-text`를 통해 벡터화한 뒤, Chroma DB에서 코사인 유사도가 높은 상위 3~5개의 텍스트 청크를 쿼리합니다.
3. 메타데이터(`user_key`)를 적용하여 타인의 로그 데이터가 조회되는 보안 누수를 철저히 차단합니다.
4. **[개선] 메타데이터 프리필터링 고도화**:
   - **이벤트 타입 분류**: 로그 덤프(`LOG_DUMP`) 적재 시, 각 청크의 본문 텍스트 내 키워드를 분석하여 `[error]` 등의 키워드가 있으면 `event_type` 메타데이터를 `ERROR` 또는 `WARNING`으로 분류하여 저장합니다.
   - **날짜 필터링**: 사용자 질문에 '오늘', 'today', '투데이' 등의 오늘 날짜 관련 검색 의도가 발견되면, KST 로컬 타임존 기준으로 오늘 00:00:00 이후에 등록된 로그만 검색할 수 있도록 `timestamp` 메타데이터 조건(`$gte`)을 필터링 쿼리에 복합(`$and`)으로 결합하여 쿼리합니다.
   - **[추가] 쿼리 파서(Query Parser) 및 후처리 필터링**: 질문 텍스트에서 시간대 범위('5분', '30분', '오전 10시', '새벽', '어제', '일주일'), 로그 레벨('Error', 'Warning', 'Critical'), 그리고 기술 키워드('Git', 'Connection', 'DB', 'Build' 등)를 정교하게 추출하여 `query_vectors` API의 후처리(Post-filtering) 필터링에 결합해 RAG 컨텍스트 무결성을 확보합니다.


#### 3단계: 프롬프트 주입 및 답변 생성
* 추출된 청크 컨텍스트와 사용자의 원본 질문을 결합하여 프롬프트를 구성합니다.
* N95 CPU 자원 보호를 위해 프롬프트 템플릿에 들어갈 Context 길이를 최대 2,000 토큰 이하로 강제 통제하며, N95 로컬 환경의 체감 속도 향상을 위해 출력 토큰을 최소화하는 숏폼 규칙을 적용합니다.
* **Window Memory**: 이전 대화 히스토리를 유지하기 위해 `backend/llm/memory.py`에서 `deque(maxlen=3)` 구조를 채택하여, 각 유저별(`user_key`)로 최대 3회 분량의 최근 대화(질문-답변 쌍)를 프롬프트에 동적으로 바인딩합니다.
* **[개선] 초경량 리랭커 도입**: 저전력 CPU(N95) 환경에서 sentence-transformers 모델 추론 시 30초 이상 지연되는 타임아웃 문제를 해결하기 위해, 환경변수 `RERANKER_TYPE` (기본값: `light`)를 지원합니다. `light` 상태에서는 단어 매칭 점수제 기반의 **초경량 룰 베이스 리랭커**를 활용하여 CPU 부하를 방지하고 연산 속도를 1ms 내외로 최적화합니다.

```python
RAG_PROMPT_TEMPLATE = """[Identity]
Role: Machine Log Summarizer.
Restrictions: STRICTLY NO greetings, NO explanations, NO polite endings (e.g., '~입니다', '~보입니다', '~하십시오'), NO conversation. Output ONLY the defined Markdown formats using Key-Value or Bullet structure.
Ending: All sentences must end in a noun or noun phrase (명사형 종결).

[Task]
Identify the User Query Intent and output EXACTLY in the corresponding format below based ONLY on the [Context] provided. If context is empty or has no logs, output "최근 기록된 작업 로그가 존재하지 않습니다." and stop immediately.

[Formats]
1. Intent 1: Count / List request (e.g., "how many?", "list logs", "로그 몇개야?")
### 📊 분석 결과
- 통계: 에러 총 [X]개 발생
- 내역:
  * [YYYY-MM-DD HH:MM:SS] [로그 메시지 원본]

2. Intent 2: Cause / Troubleshooting / Type analysis (e.g., "what is the cause?", "how to fix?")
### 🔍 에러 원인 분석
- 내역:
  * [YYYY-MM-DD HH:MM:SS] [로그 메시지 원본]
- 유형: [카테고리] ([핵심 장애 원인 요약 1문장])
- 조치: [해결을 위해 필요한 액션 1문장]

[Context]
{context}

[User Query]
{question}

[Answer] (Output only matching Intent Markdown format):"""
```

---

## 🚨 3. 철벽 코드 컨벤션 및 제약 조건
* **[300줄 분리 규칙]**: 프롬프트 문자열은 별도의 `prompt_templates.py`로 완벽 격리하여 소스 코드 로직과 섞여 300줄을 넘어가지 않도록 관리하세요.
* **[CPU 부하 조절]**: Ollama 호출 시 `options` 파라미터에 `num_thread: 3` 등의 제한 값을 전달하여 N95의 4개 코어 중 1개 코어를 OS와 웹 UI용으로 양보할 수 있도록 세팅을 최적화하세요.
* **[안전 장치 (Fallback)]**: 
  - Ollama 서비스 다운, 리랭커 연산 실패, Chroma DB 장애 등 RAG 파이프라인 중 어떠한 예외 상황이 발생하더라도 "서비스가 쉬고 있어요"와 같은 고정 에러 메시지를 노출하여 크래시를 유발하는 대신, SQLite `get_connection` 시 Python `re` 모듈과 연동된 `REGEXP` 함수를 동적 등록하여 정규식 패턴 기반으로 로그를 긁어옵니다.
  - 검색된 실제 로그들을 바탕으로 자연어 질문에 어울리는 동적 모의 답변(Simulated Response)을 무조건 출력하도록 구성하여 서비스 신뢰도를 보장합니다. 단, 테스트 환경(`LOGMON_ENV=test`)에서는 기존 안전망 메시지(`ERROR_FALLBACK_MESSAGE`)를 반환합니다.
* **[Chroma DB 쿼리 방어]**: `where` 메타데이터 필터 포맷 등의 문제로 쿼리 크래시가 발생할 확률을 차단하기 위해, 쿼리 예외 발생 시 필터를 무시하고 전체 검색(Full search)을 실행한 후 파이썬 단에서 `user_key`와 `event_type`을 직접 솎아내는 Fallback 메커니즘을 적용합니다.

