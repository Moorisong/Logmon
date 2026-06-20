# 📊 로그몬 (LogMon) 데이터베이스 설계 정의서 (Logmon-db-specification.md)

이 문서는 로그몬(LogMon) 시스템에서 정형/비정형 데이터를 안전하게 처리하기 위한 SQLite 3 데이터베이스 스키마 및 Chroma DB 임베딩 설계서입니다.

---

## 💾 1. 정형 데이터베이스: SQLite 3

* **파일명**: `logmon.db`
* **인코딩**: UTF-8 (한글 대화 내용 및 에러 로그 원문 보존용)
* **보안/접근 제어**: 백엔드 컨테이너(`logmon-backend`)만 파일 시스템 직접 접근 및 SQL 쿼리를 수행하며, UI는 REST API를 통해서만 데이터를 수집합니다.

### 📊 테이블 명세: `ide_activity_logs`

이 테이블은 Cursor, Antigravity 등 멀티 IDE에서 수집된 개발 활동 통계 및 RAG용 로그 원문 백업 데이터를 저장합니다.

| **컬럼명 (Physical Name)** | **데이터 타입** | **제약 조건** | **기본값** | **설명** |
| :--- | :--- | :--- | :--- | :--- |
| **id** | INTEGER | PRIMARY KEY, AUTOINCREMENT | - | 고유 식별자 (자동 증가) |
| **user_key** | TEXT | NOT NULL | - | 에이전트 인증 및 유저 식별용 API Key |
| **source_tool** | TEXT | NOT NULL | - | 로그를 생성한 AI 도구 이름 (Cursor, Antigravity 등) |
| **timestamp** | TEXT | NOT NULL | - | 로그 발생 시각 (YYYY-MM-DD HH:MM:SS) |
| **event_type** | TEXT | NOT NULL | - | 활동 분류 (CHAT: 챗봇, COMPLETION: 자동완성) |
| **task_name** | TEXT | NOT NULL | 'UNKNOWN' | 개발자가 지정한 작업 태그 (추출 실패 시 UNKNOWN) |
| **duration_seconds** | INTEGER | NOT NULL | 0 | 해당 작업에 소모된 시간 (초 단위) |
| **input_tokens** | INTEGER | NOT NULL | 0 | LLM 프롬프트에 사용된 입력 토큰 수 |
| **output_tokens** | INTEGER | NOT NULL | 0 | LLM이 답변한 출력 토큰 수 |
| **raw_message** | TEXT | NULL ALLOWED | NULL | 대화 내용 원본 또는 에러 로그 텍스트 (RAG 탐색 보조용) |
| **has_code_block** | INTEGER | NOT NULL | 0 | 대화/로그 내 코드 블록 포함 여부 (0: 거짓, 1: 참) |

### 📈 인덱스 설계

통계 조회 속도 향상을 위해 다음 인덱스를 생성합니다.
```sql
CREATE INDEX idx_activity_user_time ON ide_activity_logs(user_key, timestamp);
CREATE INDEX idx_activity_event_type ON ide_activity_logs(event_type);
```

---

## 🧠 2. 비정형 벡터 데이터베이스: Chroma DB

* **임베딩 모델**: `bge-small-en-v1.5` (Ollama 기반 초경량·고성능 모델)
* **목적**: 과거 개발 로그, 질문 및 해결 과정 텍스트에 대한 시맨틱 검색(Semantic Search) 지원.
* **저장 영속성**: 호스트 경로 `/home/ksh/logmon_data/chroma` 마운트를 통해 보존.

### ⚙️ 데이터 쪼개기 및 임베딩 처리 파이프라인

저전력 N95 환경의 컨텍스트 윈도우 부하 방지 및 검색 정확도 향상을 위해 청킹 규칙을 준수합니다.

1. **텍스트 분할 규칙 (Text Chunking)**:
   * **Chunk Size**: 800 자
   * **Chunk Overlap**: 100 자
   * LangChain의 `RecursiveCharacterTextSplitter` 구조를 벤치마킹하여 백엔드 파이프라인 단에서 쪼갠 후 Chroma DB 컬렉션에 적재합니다.

2. **메타데이터 저장 구조**:
   Chroma DB에 임베딩 벡터를 저장할 때 다음 메타데이터를 함께 기록하여 필터링 및 SQLite 원본 조회를 결합(Hybrid RAG)합니다.
   * `id`: SQLite의 로그 레코드 ID (`ide_activity_logs.id`)
   * `user_key`: 유저 식별용 API Key
   * `timestamp`: 로그 발생 시각
   * `source_tool`: 도구 구분 (Cursor, Antigravity 등)
