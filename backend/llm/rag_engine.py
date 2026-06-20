import logging
from typing import List

from backend.db.chroma_handler import query_vectors
from backend.llm.client import generate_completion
from backend.llm.prompt_templates import RAG_PROMPT_TEMPLATE

logger = logging.getLogger(__name__)

async def ask_rag_agent(question: str, user_key: str, top_k: int = 3) -> str:
    """
    사용자의 질문을 기반으로 Chroma DB에서 가장 유사한 과거 로그 청크를 검색하고,
    Ollama(로컬 LLM)에 프롬프트를 주입하여 답변을 생성하는 RAG 핵심 파이프라인.
    """
    logger.info(f"RAG 질의 시작: {question}")
    
    # 1. Chroma DB 시맨틱 검색 (보안을 위해 user_key로 격리)
    try:
        # chroma_handler.query_vectors는 동기 함수이므로 바로 호출
        # 만약 DB 병목이 심하면 asyncio.to_thread로 감쌀 수 있으나, Chroma의 응답은 비교적 빠름.
        results = query_vectors(query_text=question, n_results=top_k, user_key=user_key)
    except Exception as e:
        logger.error(f"Chroma 검색 중 에러: {e}")
        results = []
        
    # 2. 컨텍스트 텍스트 병합 
    # 토큰 폭발 방지를 위해 컨텍스트 문자열 길이를 단순 제어 (약 2000자 내외)
    context_str = ""
    if results and len(results) > 0 and len(results[0]) > 0:
        # 반환 구조: [[doc1, doc2, ...]]
        docs = results[0]
        context_str = "\n---\n".join(docs)
        
        # 길이 안전장치 (N95 Context Window 오버플로우 방지)
        if len(context_str) > 2000:
            context_str = context_str[:2000] + "\n... (생략됨)"
    else:
        context_str = "관련된 과거 로그 컨텍스트가 없습니다."
        
    # 3. 프롬프트 바인딩
    prompt = RAG_PROMPT_TEMPLATE.format(context=context_str, question=question)
    
    # 4. Ollama LLM 추론
    logger.debug("Ollama 추론 엔진 호출...")
    answer = await generate_completion(prompt)
    
    return answer
