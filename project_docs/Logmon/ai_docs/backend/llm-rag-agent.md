# 🤖 llm-rag-agent.md - AI 개발 가이드

이 문서는 Ollama 기반 로컬 LLM(Gemma 2 2B) 및 초경량 임베딩 모델(bge-small-en-v1.5) 연동, Chroma DB 시맨틱 검색 결합 하이브리드 RAG 챗봇 엔진 구축을 위한 AI 에이전트용 설계 지침입니다.

---

## 📝 1. 연동 기획 명세 ([Logmon-architecture.md](file:///Users/shkim/Desktop/Project/Logmon/project_docs/Logmon/human_docs/system/Logmon-architecture.md), [Logmon-db-specification.md](file:///Users/shkim/Desktop/Project/Logmon/project_docs/Logmon/human_docs/database/Logmon-db-specification.md))
* **로컬 LLM**: Gemma 2 2B (`gemma2:2b`)
* **임베딩**: `bge-small-en-v1.5`
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
2. 입력값을 `bge-small-en-v1.5`를 통해 벡터화한 뒤, Chroma DB에서 코사인 유사도가 높은 상위 3~5개의 텍스트 청크를 쿼리합니다.
3. 메타데이터(`user_key`)를 적용하여 타인의 로그 데이터가 조회되는 보안 누수를 철저히 차단합니다.

#### 3단계: 프롬프트 주입 및 답변 생성
* 추출된 청크 컨텍스트와 사용자의 원본 질문을 결합하여 프롬프트를 구성합니다.
* N95 CPU 자원 보호를 위해 프롬프트 템플릿에 들어갈 Context 길이를 최대 2,000 토큰 이하로 강제 통제합니다.

```python
RAG_PROMPT_TEMPLATE = """당신은 개발자의 작업 로그와 과거 해결 내역을 분석하는 AI 어시스턴트 '로그몬'입니다.
제시된 과거 로그 컨텍스트를 바탕으로 사용자의 질문에 친절하고 명확하게 답변해 주세요.
만약 과거 로그 컨텍스트에서 답변을 찾을 수 없다면 억지로 꾸며내지 말고 솔직하게 모른다고 대답하세요.

[과거 로그 컨텍스트]
{context}

[사용자 질문]
{question}

[답변] (한국어로 친절하고 정확하게 기술):"""
```

---

## 🚨 3. 철벽 코드 컨벤션 및 제약 조건
* **[300줄 분리 규칙]**: 프롬프트 문자열은 별도의 `prompt_templates.py`로 완벽 격리하여 소스 코드 로직과 섞여 300줄을 넘어가지 않도록 관리하세요.
* **[CPU 부하 조절]**: Ollama 호출 시 `options` 파라미터에 `num_thread: 3` 등의 제한 값을 전달하여 N95의 4개 코어 중 1개 코어를 OS와 웹 UI용으로 양보할 수 있도록 세팅을 최적화하세요.
* **[안전 장치 (Fallback)]**: Ollama 서비스가 다운되어 있거나 로딩 지연 등으로 응답하지 않을 때 예외를 캐치하여 단순히 고정된 에러 메시지를 주는 대신, SQLite 로컬 DB의 실제 활동 로그들을 분석(키워드 검색 및 에러/경고 분류)하여 동적 모의 답변(Simulated Response)을 생성해 줍니다. 테스트 환경(`LOGMON_ENV=test`)에서는 기존 안전망 메시지(`ERROR_FALLBACK_MESSAGE`)를 반환합니다.

