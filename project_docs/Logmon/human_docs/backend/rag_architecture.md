# Logmon Backend RAG 아키텍처 가이드 (Human Docs)

## 🎯 목적
Logmon 백엔드의 로그 분석 챗봇 기능(RAG 파이프라인)의 구조, 데이터 흐름, 및 예외 처리 정책을 정의합니다.

## 🧱 구조 (Architecture)
RAG 파이프라인은 다음과 같은 단계(Stage)로 구성됩니다:

1. **Intent Routing (가드레일)**:
   - 사용자의 입력이 단순 인사, 욕설, 시비 등 비정상적인 입력인 경우 LLM을 호출하지 않고 백엔드에서 사전 차단합니다.
   - 라우팅 모듈(`guardrail.py`)이 정규식 또는 간단한 키워드 기반으로 1차 필터링을 수행합니다.

2. **Smart Pre-filtering**:
   - `Chroma DB` 조회 시, 사용자의 질의에서 시간(`timestamp`), `project_id`, `log_level` 등의 조건을 추출하여 메타데이터 `where` 조건문으로 활용합니다.
   - 이를 통해 전체 DB를 검색하는 대신 관련된 로그 풀(Pool)로 1차 검색 범위를 좁힙니다.

3. **2-Stage Retrieval (Chroma DB + Re-ranker)**:
   - `Chroma DB`: 코사인 유사도로 Top-K(예: 10개) 청크를 1차 검색합니다.
   - `Re-ranker`: 로컬 CPU에 최적화된 경량 `CrossEncoder` 모델을 사용해 1차 검색된 청크들의 관련성 점수를 재계산(Re-ranking)하고, 2000자 제한 내에서 알짜 컨텍스트만 추출합니다.

4. **Window Memory (대화 히스토리)**:
   - 이전 대화 문맥(최근 3회 내외)을 메모리에 임시 저장하여, 후속 질문(예: "아까 그 에러")에 대한 문맥을 유지합니다.

## 🌊 데이터 흐름 및 예외 정책 (Data Flow & Fallback)

- **정상 흐름**:
  사용자 질문 ➡️ 가드레일 통과 ➡️ 프리필터링 메타데이터 추출 ➡️ Chroma 1차 검색 ➡️ Re-ranker 2차 정렬 ➡️ Window Memory 결합 ➡️ Ollama(Gemma2) 프롬프트 전송 ➡️ 응답 반환

- **Empty Context 예외**:
  Chroma 검색 결과나 Re-ranker 추출 결과가 없을 경우, LLM을 호출하지 않고 `"최근 기록된 작업 로그가 존재하지 않습니다."` 메시지를 즉시 반환하여 환각(Hallucination)을 방지합니다.

- **Ollama API 장애 예외 (Fallback)**:
  Ollama API에서 Timeout 또는 Connection Error가 발생하면, 즉시 SQLite DB(`ide_activity_logs`)에서 쿼리 문맥에 맞는 최근 로그를 조회합니다. 이 데이터는 LLM을 거치지 않고 패턴 매칭 기반 요약기(`generate_simulated_response`)를 통해 분석 리포트로 포맷팅되어 반환됩니다.
