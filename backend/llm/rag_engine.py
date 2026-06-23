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
    
    if not check_guardrail(question):
        return GUARDRAIL_FALLBACK_MSG

    try:
        # 1. 시간 범위 파싱
        start_time, end_time = parse_relative_datetime(question)
        
        # 2. 벡터 DB 쿼리 (필터 최소화로 데이터 누락 방지)
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

        # 3. 데이터 구조화 (메타데이터 + 본문 결합)
        docs = [f"[IDE: {meta.get('source_ide', 'Unknown')}]\n{doc}" for doc, meta in zip(raw_docs, raw_metadatas)]
        
        # 4. 리랭킹 및 Context 구성
        context_str = rerank_documents(query=question, documents=docs, top_k=5)
        if not context_str.strip():
            context_str = "\n\n".join(docs[:5])

        # 5. 이전 대화 맥락 포함 (XML 태그 격리 방식 적용)
        history = get_conversation_context(user_key)
        
        if history:
            # 1B 모델이 헷갈리지 않도록 이전 대화를 철저히 격리하고, 현재 질문을 강하게 부각합니다.
            final_question = (
                "아래 <Past_Context>는 과거 대화 기록이니 맥락 파악용으로만 참고하고, "
                "절대 현재 질문에 대한 답변으로 복사해서 사용하지 마시오.\n"
                f"<Past_Context>\n{history}\n</Past_Context>\n\n"
                f"[Current Task (반드시 아래 질문에만 대답할 것)]\n{question}"
            )
        else:
            final_question = question
        
        # 6. 추론용 프롬프트 생성
        current_date = datetime.datetime.now(_TZ_KST).strftime("%Y-%m-%d")
        prompt = RAG_PROMPT_TEMPLATE.format(
            current_date=current_date,
            context=context_str,
            question=final_question
        )

        # 7. LLM 추론 및 대화 기록
        answer = await generate_completion(prompt)
        answer = postprocess_noun_ending(answer)
        
        # (주의) memory.py의 add_conversation 내부에서 대화 세트가 3개를 초과하지 않도록 
        # pop() 또는 슬라이싱 처리가 되어 있는지 확인이 필요합니다.
        add_conversation(user_key, question, answer)
        
        return answer

    except Exception as e:
        logger.error(f"RAG 추론 오류: {e}", exc_info=True)
        return "데이터 분석 중 기술적 오류가 발생했습니다."