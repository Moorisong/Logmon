import logging
import re
from typing import List

from backend.db.chroma_handler import query_vectors
from backend.llm.client import generate_completion
from backend.llm.prompt_templates import RAG_PROMPT_TEMPLATE
from backend.llm.guardrail import check_guardrail
from backend.llm.reranker import rerank_documents
from backend.llm.memory import get_conversation_context, add_conversation

logger = logging.getLogger(__name__)

def extract_event_type(question: str) -> str:
    """사용자 질문에서 에러나 경고 관련 키워드를 추출하여 프리필터링에 활용합니다."""
    q_lower = question.lower()
    if any(w in q_lower for w in ["error", "에러", "오류", "실패", "fail"]):
        return "ERROR"
    if any(w in q_lower for w in ["warning", "경고", "warn"]):
        return "WARNING"
    return ""

async def ask_rag_agent(question: str, user_key: str, top_k: int = 10) -> str:
    """
    사용자의 질문을 기반으로 Chroma DB에서 1차 검색 후,
    CrossEncoder 리랭커로 재정렬하고 Ollama에 프롬프트를 주입하여 답변을 생성하는 고도화된 RAG 파이프라인.
    """
    logger.info(f"RAG 질의 시작: {question}")
    
    # 1. 인풋 가드레일 검사
    guardrail_msg = check_guardrail(question)
    if guardrail_msg:
        return guardrail_msg
        
    # 2. 스마트 프리필터링 (키워드 추출)
    event_type = extract_event_type(question)
    
    # 3. Chroma DB 1차 검색
    try:
        results = query_vectors(query_text=question, n_results=top_k, user_key=user_key, event_type=event_type)
    except Exception as e:
        logger.error(f"Chroma 검색 중 에러: {e}")
        results = []
        
    # 4. 2-Stage Retrieval (리랭킹) 및 컨텍스트 부재 방어
    docs = results[0] if results and len(results) > 0 and len(results[0]) > 0 else []
    
    if not docs:
        return "최근 기록된 작업 로그가 존재하지 않습니다."
        
    # 리랭커를 통한 정렬 및 길이 조절 (Top-3, Max 2000자)
    context_str = rerank_documents(query=question, documents=docs, top_k=3, max_chars=2000)
    
    if not context_str.strip():
        return "최근 기록된 작업 로그가 존재하지 않습니다."
        
    # 5. Window Memory 적용
    history_context = get_conversation_context(user_key)
    final_question = f"[이전 대화 내역]\n{history_context}\n\n[현재 질문]\n{question}" if history_context else question
        
    # 6. 프롬프트 바인딩 및 추론
    prompt = RAG_PROMPT_TEMPLATE.format(context=context_str, question=final_question)
    answer = await generate_completion(prompt)
    
    # 7. 대화 히스토리 저장
    add_conversation(user_key, question, answer)
    
    return answer
