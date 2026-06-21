import logging
from typing import List
import os

logger = logging.getLogger(__name__)

# 전역 모델 캐싱
_cross_encoder = None

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

def rerank_documents(query: str, documents: List[str], top_k: int = 3, max_chars: int = 2000) -> str:
    """
    1차 검색된 청크(documents)를 CrossEncoder로 사용자 질문(query)과 다시 비교하여
    점수순으로 정렬한 뒤, 최대 글자 수(max_chars)를 넘지 않게 조립하여 반환합니다.
    """
    if not documents:
        return ""
        
    reranker = get_reranker()
    if not reranker:
        # 모델 로딩 실패 시 원본 그대로 결합 (Fallback)
        context_str = "\n---\n".join(documents)
        if len(context_str) > max_chars:
            context_str = context_str[:max_chars] + "\n... (생략됨)"
        return context_str

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
        # 에러 발생 시 원본 조립 (Fallback)
        context_str = "\n---\n".join(documents)
        return context_str[:max_chars]
