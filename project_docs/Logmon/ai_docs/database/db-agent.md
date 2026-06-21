# 🤖 db-agent.md - AI 개발 가이드

이 문서는 SQLite 3 데이터베이스 테이블 정의, 데이터 적재 로직 및 Chroma DB 벡터 데이터 저장소 구축을 전담하는 AI 에이전트용 설계 지침입니다.

---

## 📝 1. 연동 기획 명세 ([Logmon-database.md](file:///Users/shkim/Desktop/Project/Logmon/project_docs/Logmon/human_docs/database/Logmon-database.md))
* **SQLite 3**: `ide_activity_logs` 테이블 구조 및 인덱스 정합성 사수.
* **Chroma DB**: `nomic-embed-text` 임베딩에 적합한 데이터 분할(Chunking) 및 적재 파이프라인.
* **청킹 제약**: Chunk Size 800 자, Chunk Overlap 100 자 준수.

---

## 🤖 2. AI 개발 지침 및 설계 구조

### 🎯 목적
* 로그몬 시스템의 데이터 레이어 전반(정형 SQLite 및 비정형 Chroma DB)을 안전하게 관리하며, 멱등성이 보장되고 데이터 락이 발생하지 않는 영속성 환경을 제공합니다.

### 📦 패키지 및 타깃 클래스 경로 구조
```plaintext
backend/
└── db/
    ├── connection.py          # SQLite 3 비동기/동기 커넥션 관리
    ├── sqlite_handler.py      # SQLite CRUD (Insert, Select, Checkpoint)
    └── chroma_handler.py      # Chroma DB 컬렉션 초기화, 임베딩 적재 및 Query
```

### 🛠️ 개발 단계 (Step-by-Step 상세 로직)

#### 1단계: SQLite 3 테이블 초기화 및 스키마 검증
* `connection.py` 기동 시 데이터 디렉터리(`/app/data/`) 및 SQLite 파일인 `logmon.db`가 누락된 경우 생성하며, `ide_activity_logs` 테이블을 초기 마이그레이션합니다.
* 다음 DDL 구조를 철저히 따르세요.
```sql
CREATE TABLE IF NOT EXISTS ide_activity_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_key TEXT NOT NULL,
    source_tool TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    event_type TEXT NOT NULL,
    task_name TEXT NOT NULL DEFAULT 'UNKNOWN',
    duration_seconds INTEGER NOT NULL DEFAULT 0,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    raw_message TEXT,
    has_code_block INTEGER NOT NULL DEFAULT 0
);
```
* 효율적인 쿼리를 위해 인덱스(`idx_activity_user_time`, `idx_activity_event_type`)가 정상 등록되어 있는지 교차 확인 및 생성합니다.

#### 2단계: SQLite 데이터 핸들러 구현 (`sqlite_handler.py`)
* 에이전트 인증 성공 후, 중복 로그 적재를 방지하기 위해 `user_key`와 `timestamp` 조합으로 사전 존재 여부를 확인(Idempotency Check)하는 `check_duplicate_log` 함수를 구현합니다.
* 데이터 적재 시 SQL Injection을 차단하기 위해 매개변수화된 바인딩 쿼리(`?` placeholder)만을 사용하세요.

#### 3단계: Chroma DB 데이터 분할 및 적재 (`chroma_handler.py`)
* `raw_message` 등의 텍스트를 청킹하기 위해 Chunk Size 800 / Chunk Overlap 100 자 구조의 문자열 분할 유틸리티를 적용합니다.
* 쪼개진 텍스트 청크를 `logmon-ollama` 서비스의 임베딩 엔드포인트를 호출하여 벡터로 수신하고, 이를 Chroma DB 컬렉션에 적재합니다.
* **메타데이터**: 쿼리 최적화를 위해 `id`(SQLite의 레코드 ID)와 `user_key`를 반드시 메타데이터 객체에 임베딩하여 보존하세요.

---

## 🚨 3. 철벽 코드 컨벤션 및 제약 조건
* **[300줄 분리 규칙]**: SQLite 연산과 Chroma DB 연산 로직은 반드시 독립된 파일(`sqlite_handler.py`, `chroma_handler.py`)로 쪼개어 단일 파일 300줄을 넘지 않도록 격리 제어하십시오.
* **[커넥션 누수 방어]**: SQLite 트랜잭션 수행 시 예외 상황에서 자원이 고립되지 않도록 `try-finally` 절이나 컨텍스트 매니저(`with`)를 이용하여 연결을 확실하게 반환 처리하십시오.
* **[보안 락]**: 멀티테넌시(Multi-tenancy) 구조 보안을 위해, Chroma DB에서 코사인 유사도 검색을 할 때 `user_key` 필터링 조건을 절대 누락하지 마십시오.
