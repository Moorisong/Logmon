# backend/llm/utils.py
import re
import logging
import datetime
from typing import Dict, Any, List
from backend.llm.stats_db import upsert_daily_statistics

logger = logging.getLogger(__name__)

def format_log_message(log_id: int, timestamp: str, source: str, log_level: str, target: str, raw_message: str) -> str:
    """
    로그 입력을 Key-Value 구조화된 단일 청크 템플릿으로 변환합니다.
    """
    source_mapped = source
    if "vscode" in source.lower():
        source_mapped = "VSCode"
    elif "intellij" in source.lower():
        source_mapped = "IntelliJ"
    elif "git" in source.lower():
        source_mapped = "Git"
        
    level_mapped = log_level
    if "error" in log_level.lower() or "critical" in log_level.lower():
        level_mapped = "ERROR"
    elif "warn" in log_level.lower():
        level_mapped = "WARN"
    elif "info" in log_level.lower():
        level_mapped = "INFO"

    return f"""---
ID: {log_id}
DateTime: {timestamp} (KST)
Source: {source_mapped}
LogLevel: {level_mapped}
Target: {target}
RawMessage: {raw_message}
---"""

def estimate_tokens(text: str) -> float:
    """
    tiktoken이나 transformers 임포트 없이 글자 수 기반으로
    빠르고 오버헤드 없는 토큰 수 예측을 수행합니다.
    """
    if not text:
        return 0.0
    return len(text) / 2.5

def postprocess_noun_ending(text: str) -> str:
    """
    Gemma의 대화형 종결 어미(~합니다, ~하세요 등)를 
    명사형 종결(~함., ~요망., ~필요., ~발생.)으로 강제 치환하는 경량 필터입니다.
    """
    if not text:
        return ""
        
    rules = [
        (r"되었습니다\.?", "됨."),
        (r"되었습니다", "됨"),
        (r"하겠습니다\.?", "하겠음."),
        (r"완료하였습니다\.?", "완료함."),
        (r"완료했습니다\.?", "완료함."),
        (r"발생하였습니다\.?", "발생함."),
        (r"발생했습니다\.?", "발생함."),
        (r"발생되었습니다\.?", "발생함."),
        (r"확인되었습니다\.?", "확인됨."),
        (r"권장합니다\.?", "권장함."),
        (r"권장드립니다\.?", "권장함."),
        (r"해결했습니다\.?", "해결함."),
        (r"해결하였습니다\.?", "해결함."),
        (r"대답합니다\.?", "대답함."),
        (r"답변드립니다\.?", "답변함."),
        (r"합니다\.?", "함."),
        (r"입니다\.?", "임."),
        (r"했습니다\.?", "했음."),
        (r"하십시오\.?", "요망."),
        (r"해주세요\.?", "요망."),
        (r"하세요\.?", "요망."),
        (r"주세요\.?", "요망."),
        (r"바랍니다\.?", "요망."),
        (r"드립니다\.?", "드림."),
        (r"요\.?$", ""), 
    ]
    
    processed = text
    for pattern, repl in rules:
        processed = re.sub(pattern, repl, processed)
    return processed

def parse_relative_datetime(question: str) -> tuple:
    """
    유저 질문에서 '지난 N일', '이틀 동안', '일주일 동안' 등의 상대적인 기간 키워드를 파싱하여
    현재 KST(Asia/Seoul) 시간 기준으로 (start_time, end_time) 문자열 범위를 반환합니다.
    실패 시 기본적으로 (None, None)을 안전하게 반환합니다.
    """
    try:
        timezone_kst = datetime.timezone(datetime.timedelta(hours=9))
        now = datetime.datetime.now(timezone_kst)
        
        days = None
        q_clean = question.replace(" ", "")
        
        if "이틀" in question:
            days = 2
        elif "하루" in question:
            days = 1
        elif "일주일" in question:
            days = 7
        else:
            match = re.search(r"(?:지난|최근)?\s*(\d+)\s*일\s*(?:동안)?", question)
            if match:
                days = int(match.group(1))
        
        if days is not None:
            start_date = now - datetime.timedelta(days=days)
            start_time = f"{start_date.strftime('%Y-%m-%d')} 00:00:00"
            end_time = now.strftime("%Y-%m-%d %H:%M:%S")
            return start_time, end_time
            
    except Exception as e:
        logger.error(f"상대 기간 날짜 파싱 중 예외 발생: {e}")
        
    return None, None

def manage_context_token_limit(docs: List[str], question: str, final_question: str, selected_template: str, current_date_str: str) -> str:
    """
    총 토큰수가 1,800을 초과할 때, 청크를 리스트에서 통째로 날리지 않고,
    각 청크의 RawMessage 길이를 점진적으로 슬라이싱하여 1,800 토큰 이하로 맞춘 context_str을 반환합니다.
    """
    from backend.llm.reranker import rerank_documents

    def _compress(text: str) -> str:
        if not text:
            return ""
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        cleaned = "\n".join(lines)
        cleaned = re.sub(r"[ \t]+", " ", cleaned)
        return cleaned

    max_msg_len = 1000
    step = 150
    
    context_str = rerank_documents(query=question, documents=docs, top_k=3, max_chars=6000)
    context_str = _compress(context_str)
    
    while max_msg_len > 50:
        prompt = selected_template.format(
            current_date=current_date_str,
            context=context_str,
            question=final_question
        )
        approx_tokens = estimate_tokens(prompt)
        if approx_tokens <= 1800:
            break
            
        logger.warning(f"[WARN] Token limit exceeded ({approx_tokens:.1f} tokens). Truncating RawMessage to {max_msg_len} chars...")
        
        new_docs = []
        for doc in docs:
            marker = "RawMessage: "
            idx = doc.find(marker)
            if idx != -1:
                header = doc[:idx + len(marker)]
                body = doc[idx + len(marker):]
                footer = ""
                if body.endswith("---"):
                    body = body[:-3]
                    footer = "---"
                truncated_body = body[:max_msg_len].strip()
                new_docs.append(header + truncated_body + "\n" + footer)
            else:
                new_docs.append(doc)
                
        context_str = rerank_documents(query=question, documents=new_docs, top_k=3, max_chars=6000)
        context_str = _compress(context_str)
        max_msg_len -= step
        
    return context_str
