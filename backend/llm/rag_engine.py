# backend/llm/rag_engine.py
import logging
import datetime
from typing import Optional

from backend.db.chroma_handler import query_vectors
from backend.llm.client import generate_completion
from backend.llm.prompt_templates import RAG_PROMPT_TEMPLATE
from backend.llm.guardrail import check_guardrail, GUARDRAIL_FALLBACK_MSG
from backend.llm.reranker import rerank_documents
from backend.llm.memory import get_conversation_context, add_conversation
from backend.llm.utils import (
    postprocess_noun_ending,
    parse_relative_datetime,
)

logger = logging.getLogger(__name__)
_TZ_KST = datetime.timezone(datetime.timedelta(hours=9))

async def ask_rag_agent(question: str, user_key: str, top_k: int = 10) -> str:
    logger.info(f"RAG 질의 시작: {question}")
    
    # 1. 파이썬 단에서의 1차 인프라 가드레일 철벽 방어 (외부 도구 0.1초 컷)
    if not check_guardrail(question):
        return GUARDRAIL_FALLBACK_MSG

    try:
        # 2. 시간 범위 파싱
        start_time, end_time = parse_relative_datetime(question)
        
        # 3. 벡터 DB 쿼리
        results = query_vectors(
            query_text=question,
            n_results=top_k,
            user_key=user_key,
            start_time=start_time,
            end_time=end_time
        )
        
        raw_docs = results[0] if results and len(results) > 0 else []
        raw_metadatas = results[2] if results and len(results) > 2 else []

        if not raw_docs:
            return "최근 기록된 작업 로그가 존재하지 않습니다."

        # 4. 데이터 구조화 (메타데이터 + 본문 결합)
        docs = [f"[IDE: {meta.get('source_ide', 'Unknown')}]\n{doc}" for doc, meta in zip(raw_docs, raw_metadatas)]
        
        # 5. [로그 다이어트] 1B 모델 최적화를 위해 컨텍스트 허용 개수를 5개에서 2개로 전격 축소
        context_str = rerank_documents(query=question, documents=docs, top_k=2)
        if not context_str.strip():
            context_str = "\n\n".join(docs[:2])

        # 6. 이전 대화 맥락 포함 (부정 지시문을 완전히 도려내고 직관적인 긍정형 블록 구조화)
        history = get_conversation_context(user_key)
        
        if history:
            # 과거 답변에 꽂히는 왜곡을 방지하기 위해 XML 컴포넌트 단위로 격리 배치
            final_question = (
                "[참고용 이전 대화 맥락]\n"
                f"<Past_Context>\n{history}\n</Past_Context>\n\n"
                "[분석할 현재 질문]\n"
                f"{question}"
            )
        else:
            final_question = f"[분석할 현재 질문]\n{question}"
        
        # 7. 추론용 최종 시스템 프롬프트 포맷 생성
        current_date = datetime.datetime.now(_TZ_KST).strftime("%Y-%m-%d")
        prompt = RAG_PROMPT_TEMPLATE.format(
            current_date=current_date,
            context=context_str,
            question=final_question
        )

        # 8. LLM 추론 통신 및 결과 정제
        answer = await generate_completion(prompt)
        answer = postprocess_noun_ending(answer)
        
        # 9. memory.py 슬라이딩 윈도우(최대 2세트 고정)에 대화 영구 적재
        add_conversation(user_key, question, answer)
        
        return answer

    except Exception as e:
        logger.error(f"RAG 추론 오류: {e}", exc_info=True)
        return "데이터 분석 중 기술적 오류가 발생함."