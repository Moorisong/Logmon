# Logmon Data Schema & Traceability Matrix

## 1. 개요
Logmon 서비스는 IDE 로컬 로그 데이터를 수집하여, 분석 가능한 형태로 구조화(Structuring) 및 정규화(Normalization)하여 저장합니다. 본 문서는 시스템에 저장되는 데이터의 항목과 파생 메타데이터 정보를 기술합니다.

## 2. 기본 로그 스키마 (SQLite 저장 항목)
`ide_activity_logs` 테이블에 저장되는 데이터의 핵심 필드입니다.

| 필드명 | 데이터 타입 | 설명 |
| :--- | :--- | :--- |
| `id` | Integer | 로그 고유 식별자 (PK) |
| `user_key` | String | 사용자 API Key |
| `source_tool` | String | 원본 IDE/도구 명칭 |
| `timestamp` | String | 발생 시각 ('YYYY-MM-DD HH:MM:SS') |
| `event_type` | String | 로그 수준 (INFO, ERROR, WARN 등) |
| `task_name` | String | 수행 작업 단위 |
| `duration_seconds` | Float | 소요 시간 |
| `input/output_tokens` | Integer | LLM 토큰 사용량 |
| `raw_message` | String | 구조화된 로그 본문 |
| `has_code_block` | Integer | 코드 블록 포함 여부 |

## 3. 지능형 메타데이터 (RAG 활용)
분석 품질을 높이기 위해 원본에서 파생된 메타데이터입니다.

* **Source IDE**: `Antigravity`, `Cursor`, `VSCode`, `JetBrains`, `Windsurf`, `Zed` 등 분류
* **Log Level**: ERROR, WARN, DEBUG, INFO 정규화
* **Action Type**: `network`, `build`, `git`, `system` 카테고리 분류



[Image of data pipeline process]


## 4. 데이터 가공 파이프라인 흐름
1. **수집(Agent)**: IDE 환경에서 `raw_message` 및 메타데이터 수집.
2. **구조화(SQL Backend)**: `insert_activity_log`를 통해 로그 삽입 및 `format_log_message`로 템플릿화.
3. **분석(LLM RAG)**: 가공된 데이터를 `ChromaDB` 메타데이터로 적재하여 RAG 엔진이 활용.

---

## 5. 유저 질문 가이드

### 💡 [질문 가이드: 이렇게 물어보세요!]
> * 🖥 **환경**: "내가 주로 사용하는 IDE가 뭐야?"
> * ⏳ **활동**: "오늘 내가 가장 오래 작업한 게 뭐야?"
> * ⚠️ **에러**: "최근 발생한 ERROR 로그 원인이 뭐야?"
> * 🚀 **Git**: "어제 git push 몇 번 했어?"
> 
> *Tip: "오늘", "어제", "최근 3일"처럼 시간 범위를 함께 말해주면 더 정확합니다.*

### 5.1. 질문 유형 예시
1. **작업 생산성 분석**: "이번 주에 내가 수행한 작업 중 소요 시간이 가장 길었던 것은 무엇이야?"
2. **기술 환경 분석**: "최근 일주일 동안 Cursor와 VSCode 중 어디서 더 많은 로그가 발생했어?"
3. **장애/이슈 분석**: "최근 3일 동안 네트워크 관련해서 발생한 에러가 몇 건이야?"
4. **Git 작업 추적**: "최근 7일 동안 내가 git commit을 몇 번 했어?"

---

## 6. 시스템 운영 팁
* **로그 검색**: `action_type` 필터를 활용하면 네트워크, 빌드 이슈를 즉시 타격 가능합니다.
* **데이터 관리**: 7일이 지난 로그는 자동으로 클리닝(TTL)되므로 장기 보관이 필요한 로그는 별도 아카이브가 필요합니다.