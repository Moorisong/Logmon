import logging
from typing import List
import os

logger = logging.getLogger(__name__)

# 전역 모델 캐싱
_cross_encoder = None

import re

RERANKER_TYPE = os.getenv("RERANKER_TYPE", "light")

def get_reranker():
    global _cross_encoder
    if _cross_encoder is None:
        try:
            # sentence-transformers를 임포트하고 가벼운 모델을 cpu에 로드합니다.
            from sentence_transformers import CrossEncoder
            logger.info("리랭커 모델(cross-encoder/ms-marco-MiniLM-L-6-v2)을 CPU로 로딩합니다.")
            _cross_encoder = CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2', device='cpu')
        except ImportError:
            logger.error("sentence-transformers 라이브러리가 없습니다.")
            return None
        except Exception as e:
            logger.error(f"리랭커 모델 로딩 실패: {e}")
            return None
    return _cross_encoder

def rule_based_rerank(query: str, documents: List[str], top_k: int = 3, max_chars: int = 2000) -> str:
    """
    CPU(N95) 환경을 위한 초경량 룰 베이스 리랭커.
    사용자 쿼리의 개별 키워드가 문서에 매칭되는 빈도 및 가중치 점수를 부여해 1ms 내외로 정렬합니다.
    """
    if not documents:
        return ""
        
    q_words = [w.strip().lower() for w in query.split() if len(w.strip()) > 0]
    
    scored_docs = []
    for doc in documents:
        doc_lower = doc.lower()
        score = 0
        
        for word in q_words:
            clean_word = re.sub(r"[^\w]", "", word)
            if not clean_word:
                continue
            if clean_word in doc_lower:
                score += 10
                score += doc_lower.count(clean_word)
                
        scored_docs.append((score, doc))
        
    scored_docs.sort(key=lambda x: x[0], reverse=True)
    
    selected_docs = []
    current_len = 0
    for score, doc in scored_docs[:top_k]:
        if current_len + len(doc) > max_chars and selected_docs:
            break
        selected_docs.append(doc)
        current_len += len(doc)
        
    context_str = "\n---\n".join(selected_docs)
    if len(context_str) > max_chars:
        context_str = context_str[:max_chars] + "\n... (생략됨)"
    return context_str

def rerank_documents(query: str, documents: List[str], top_k: int = 3, max_chars: int = 2000) -> str:
    """
    1차 검색된 청크(documents)를 CrossEncoder로 사용자 질문(query)과 다시 비교하여
    점수순으로 정렬한 뒤, 최대 글자 수(max_chars)를 넘지 않게 조립하여 반환합니다.
    """
    if not documents:
        return ""
        
    if RERANKER_TYPE == "light":
        return rule_based_rerank(query, documents, top_k, max_chars)
        
    reranker = get_reranker()
    if not reranker:
        logger.warning("리랭커 모델 로딩 실패로 초경량 룰 베이스 리랭커로 Fallback합니다.")
        return rule_based_rerank(query, documents, top_k, max_chars)

    try:
        # CrossEncoder는 (query, doc) 쌍을 받아 점수를 계산합니다.
        pairs = [[query, doc] for doc in documents]
        scores = reranker.predict(pairs)
        
        # 점수와 문서를 매핑하여 내림차순 정렬
        scored_docs = list(zip(scores, documents))
        scored_docs.sort(key=lambda x: x[0], reverse=True)
        
        selected_docs = []
        current_len = 0
        
        for score, doc in scored_docs[:top_k]:
            if current_len + len(doc) > max_chars and selected_docs:
                break
            selected_docs.append(doc)
            current_len += len(doc)
            
        context_str = "\n---\n".join(selected_docs)
        if len(context_str) > max_chars:
            context_str = context_str[:max_chars] + "\n... (생략됨)"
            
        return context_str
        
    except Exception as e:
        logger.error(f"리랭킹 처리 중 에러: {e}")
        # 에러 발생 시 룰 베이스로 Fallback
        return rule_based_rerank(query, documents, top_k, max_chars)
