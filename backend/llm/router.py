"""
Hybrid Query Router
모든 질문을 LLM Fallback으로 보내 RAG가 로그를 분석하도록 유도합니다.
"""

import re
import logging
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)

@dataclass
class RouteResult:
    route: str                            
    fast_track_key: Optional[str] = None  
    keywords: List[str] = field(default_factory=list)
    log_level: str = ""
    source_ide: str = ""
    action_type: str = ""

ROUTE_FAST_TRACK = "fast_track"
ROUTE_LLM_FALLBACK = "llm_fallback"

def detect_fast_track(question: str) -> Optional[RouteResult]:
    """
    모든 질문에 대해 일단 LLM Fallback을 호출하도록 하여 
    RAG 엔진이 충분한 컨텍스트를 확보하게 함.
    """
    logger.info(f"[Router] RAG 분석을 위해 LLM Fallback으로 라우팅: '{question}'")
    return RouteResult(route=ROUTE_LLM_FALLBACK)

def parse_llm_filter_response(llm_response: str) -> Dict[str, Any]:
    return {"keywords": [], "log_level": "", "source_ide": "", "action_type": ""}

def build_llm_fallback_prompt(question: str) -> str:
    return "당신은 로그 검색 전문 파서입니다. 질문에서 핵심 키워드와 필터를 추출하세요."