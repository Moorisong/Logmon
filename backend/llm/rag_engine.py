import logging
import re
from typing import List
import datetime

from backend.db.chroma_handler import query_vectors
from backend.llm.client import generate_completion
from backend.llm.prompt_templates import RAG_PROMPT_TEMPLATE, COUNT_PROMPT_TEMPLATE
from backend.llm.guardrail import check_guardrail, GUARDRAIL_FALLBACK_MSG
from backend.llm.reranker import rerank_documents
from backend.llm.memory import get_conversation_context, add_conversation
from backend.llm.utils import (
    estimate_tokens, 
    postprocess_noun_ending, 
    parse_relative_datetime, 
    manage_context_token_limit
)

logger = logging.getLogger(__name__)

def get_timestamp_from_doc(doc: str) -> datetime.datetime:
    match = re.search(r"\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]", doc)
    if match:
        try:
            return datetime.datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S")
        except ValueError:
            pass
    return datetime.datetime.max

def parse_query_filters(question: str) -> tuple:
    q_lower = question.lower()
    timezone_kst = datetime.timezone(datetime.timedelta(hours=9))
    now = datetime.datetime.now(timezone_kst)
    today = now.date()
    yesterday = today - datetime.timedelta(days=1)
    start_time, end_time = None, None
    try:
        start_time, end_time = parse_relative_datetime(question)
    except Exception as parse_err:
        logger.error(f"[날짜 파서 오류] {parse_err}")
    if not start_time or not end_time:
        if "5분" in q_lower:
            start_time = (now - datetime.timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S")
            end_time = now.strftime("%Y-%m-%d %H:%M:%S")
        elif "30분" in q_lower:
            start_time = (now - datetime.timedelta(minutes=30)).strftime("%Y-%m-%d %H:%M:%S")
            end_time = now.strftime("%Y-%m-%d %H:%M:%S")
        elif "오전 10시" in q_lower:
            start_time = f"{today.strftime('%Y-%m-%d')} 10:00:00"
            end_time = f"{today.strftime('%Y-%m-%d')} 10:59:59"
        elif "새벽" in q_lower:
            target_day = yesterday if "어제" in q_lower else today
            start_time = f"{target_day.strftime('%Y-%m-%d')} 00:00:00"
            end_time = f"{target_day.strftime('%Y-%m-%d')} 06:00:00"
        elif "어제" in q_lower:
            start_time = f"{yesterday.strftime('%Y-%m-%d')} 00:00:00"
            end_time = f"{yesterday.strftime('%Y-%m-%d')} 23:59:59"
        elif "일주일" in q_lower:
            start_time = (now - datetime.timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
            end_time = now.strftime("%Y-%m-%d %H:%M:%S")
        elif any(w in q_lower for w in ["오늘", "투데이", "today"]):
            start_time = f"{today.strftime('%Y-%m-%d')} 00:00:00"
            end_time = f"{today.strftime('%Y-%m-%d')} 23:59:59"
        elif "2030년" in q_lower:
            start_time = "2030-01-01 00:00:00"
            end_time = "2030-01-01 23:59:59"
    logger.info(f"[시간 맥락 파싱] 질문: '{question}', 기준 날짜 범위: {start_time} ~ {end_time}")
    event_type = ""
    if any(w in q_lower for w in ["critical", "크리티컬", "error", "에러", "오류", "실패", "fail"]):
        event_type = "ERROR"
    elif any(w in q_lower for w in ["warning", "경고", "warn"]):
        event_type = "WARNING"
    keywords = []
    kw_map = {
        "git": ["git", "깃"], "connection": ["connection", "커넥션", "connect"],
        "database": ["database", "데이터베이스", "db", "sqlite"], "build": ["build", "빌드"],
        "host": ["host", "호스트"], "port": ["port", "포트"], "chicken": ["chicken", "치킨"],
        "2030": ["2030", "2030년"], "error": ["error", "에러", "오류", "실패", "fail"],
        "critical": ["critical", "크리티컬"], "warning": ["warning", "경고", "warn"]
    }
    for key, synonyms in kw_map.items():
        if any(syn in q_lower for syn in synonyms):
            keywords.append(key); keywords.extend(synonyms)
    return start_time, end_time, event_type, keywords

def compress_context(text: str) -> str:
    if not text: return ""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    cleaned = "\n".join(lines)
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    return cleaned

async def ask_rag_agent(question: str, user_key: str, top_k: int = 10) -> str:
    logger.info(f"RAG 질의 시작: {question}")
    if not check_guardrail(question): return GUARDRAIL_FALLBACK_MSG
    try:
        start_time, end_time, event_type, keywords = parse_query_filters(question)
        results = query_vectors(query_text=question, n_results=top_k, user_key=user_key, event_type=event_type, start_time=start_time, end_time=end_time, keywords=keywords)
        docs = results[0] if results and len(results) > 0 and len(results[0]) > 0 else []
        timezone_kst = datetime.timezone(datetime.timedelta(hours=9))
        current_date_str = datetime.datetime.now(timezone_kst).strftime('%Y-%m-%d')
        if any(k in question.lower() for k in ["오늘", "today", "투데이"]):
            docs = [doc for doc in docs if current_date_str in doc]
        if not docs: return "최근 기록된 작업 로그가 존재하지 않습니다."
        docs = docs[:3]
        context_str = rerank_documents(query=question, documents=docs, top_k=3, max_chars=2000)
        if not context_str.strip(): return "최근 기록된 작업 로그가 존재하지 않습니다."
        context_str = compress_context(context_str)
        history_context = get_conversation_context(user_key)
        final_question = f"[이전 대화 내역]\n{history_context}\n\n[현재 질문]\n{question}" if history_context else question
        final_question = compress_context(final_question)
        is_count_query = any(k in question.lower() for k in ["몇 개", "몇개", "몇건", "몇 건", "count", "how many"])
        selected_template = COUNT_PROMPT_TEMPLATE if is_count_query else RAG_PROMPT_TEMPLATE
        stats_hint = ""
        if is_count_query:
            try:
                stat_match = re.search(r"Total_Log_Count:\s*(\d+)\s*Cases\s*\(INFO:\s*(\d+),\s*WARN:\s*(\d+),\s*ERROR:\s*(\d+)\)", context_str)
                if stat_match:
                    stats_hint = f"\n[Calculated Statistics]\n- INFO: {stat_match.group(2)}개\n- WARN: {stat_match.group(3)}개\n- ERROR: {stat_match.group(4)}개\n- Total: {stat_match.group(1)}개\n"
            except: pass
        if stats_hint: final_question = f"{final_question}\n{stats_hint}"
        context_str = manage_context_token_limit(docs=docs, question=question, final_question=final_question, selected_template=selected_template, current_date_str=current_date_str)
        prompt = selected_template.format(current_date=current_date_str, context=context_str, question=final_question)
        answer = await generate_completion(prompt)
        answer = postprocess_noun_ending(answer)
        add_conversation(user_key, question, answer)
        return answer
    except Exception as pipeline_err:
        logger.error(f"RAG 파이프라인 수행 실패: {pipeline_err}")
        from backend.llm.client import query_sqlite_logs, generate_simulated_response
        return postprocess_noun_ending(generate_simulated_response(question, query_sqlite_logs(question)))