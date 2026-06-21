# Logmon Backend RAG Agent Reference

## 📝 Planning 문서명 (implementation_plan.md)
* 1단계 리팩토링 계획: Logmon 파이프라인 버그 수정 및 RAG 고도화
* 참조 스펙: SQLite Fallback, Smart Pre-filtering, 2-Stage Retrieval, Guardrail, Empty Context Handling, Window Memory

---

## 🤖 AI 작업 지침

### 🎯 목적
Logmon 백엔드 파이프라인을 유지보수하는 AI 에이전트는 본 지침을 준수하여, 기능 구현 및 리팩토링 시 시스템 안정성과 성능(특히 로컬 CPU 자원)을 최우선으로 고려해야 합니다.

### 🛠 작업 단계 및 모듈 분리 원칙 (Step-by-Step)
1. **모듈 독립성 보장**: RAG의 각 단계(라우터, 리랭커, 메모리, 클라이언트)는 반드시 개별 모듈(파일)로 분리되어야 합니다. 파일당 300줄 상한선을 절대 초과하지 마십시오.
2. **동기화 확인**: 기능을 수정할 때는 `tests/test_llm.py` 등의 테스트 케이스도 함께 업데이트하는 '3-Way 동기화'를 필수적으로 수행합니다.
3. **가벼운 자원 사용**: `sentence-transformers` 등 무거운 라이브러리를 추가할 때는 로컬 PC(N95 CPU 등)에서 메모리 오버플로우가 나지 않도록 가벼운 모델(`cross-encoder/ms-marco-MiniLM-L-6-v2` 등)을 채택하고 `device='cpu'`를 명시적으로 설정합니다.

### ⚠️ 주의사항 및 예외 분기
- **SQLite Fallback 누수 방지**: LLM 요청 실패(Timeout, 서버 다운) 시, `client.py`의 예외 블록에서 어설프게 "엔진이 쉬고 있어요" 등의 안내로 끝내지 마십시오. 반드시 `sqlite_logs.py`를 통해 데이터를 긁어와 `generate_simulated_response` 로직에 완벽히 전달해야 합니다.
- **가드레일 방어선 유지**: 악의적인 입력이나 무의미한 프롬프트는 LLM의 컴퓨팅 자원을 낭비합니다. `guardrail.py`를 통한 사전 차단 로직을 절대 무력화해서는 안 됩니다.
- **환각 방지**: 검색된 `Context` 문자열이 실질적으로 비어있다면, LLM 호출을 즉각 생략하는 분기를 유지해야 합니다.
