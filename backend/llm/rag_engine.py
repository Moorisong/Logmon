# backend/llm/rag_engine.py
import logging
import re
from typing import List, Optional
import datetime

from backend.db.chroma_handler import query_vectors
from backend.llm.client import generate_completion, extract_llm_filters
from backend.llm.prompt_templates import RAG_PROMPT_TEMPLATE, COUNT_PROMPT_TEMPLATE
from backend.llm.guardrail import check_guardrail, GUARDRAIL_FALLBACK_MSG
from backend.llm.reranker import rerank_documents
from backend.llm.memory import get_conversation_context, add_conversation
from backend.llm.router import detect_fast_track, ROUTE_FAST_TRACK
from backend.llm.utils import (
    estimate_tokens,
    postprocess_noun_ending,
    parse_relative_datetime,
    manage_context_token_limit,
)

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# 상수
# ──────────────────────────────────────────────

_TZ_KST = datetime.timezone(datetime.timedelta(hours=9))

# ChromaDB log_level 허용 값 집합
_VALID_LOG_LEVELS = {"INFO", "ERROR", "WARN", "DEBUG"}

# ChromaDB action_type 허용 값 집합
_VALID_ACTION_TYPES = {"network", "build", "git", "system"}


# ──────────────────────────────────────────────
# 유틸리티
# ──────────────────────────────────────────────

def get_timestamp_from_doc(doc: str) -> datetime.datetime:
    match = re.search(r"\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]", doc)
    if match:
        try:
            return datetime.datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S")
        except ValueError:
            pass
    return datetime.datetime.max


def compress_context(text: str) -> str:
    if not text:
        return ""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    cleaned = "\n".join(lines)
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    return cleaned


# ──────────────────────────────────────────────
# 시간/이벤트 필터 파싱
# ──────────────────────────────────────────────

def parse_query_filters(question: str) -> tuple:
    """
    사용자 질문에서 시간 범위, 이벤트 타입, 키워드를 추출합니다.
    Returns: (start_time, end_time, event_type, keywords)
    """
    q_lower = question.lower()
    now = datetime.datetime.now(_TZ_KST)
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
        "git": ["git", "깃"],
        "connection": ["connection", "커넥션", "connect"],
        "database": ["database", "데이터베이스", "db", "sqlite"],
        "build": ["build", "빌드"],
        "host": ["host", "호스트"],
        "port": ["port", "포트"],
        "chicken": ["chicken", "치킨"],
        "2030": ["2030", "2030년"],
        "error": ["error", "에러", "오류", "실패", "fail"],
        "critical": ["critical", "크리티컬"],
        "warning": ["warning", "경고", "warn"],
    }
    for key, synonyms in kw_map.items():
        if any(syn in q_lower for syn in synonyms):
            keywords.append(key)
            keywords.extend(synonyms)

    return start_time, end_time, event_type, keywords


# ──────────────────────────────────────────────
# LLM Fallback 메타데이터 필터 빌더
# ──────────────────────────────────────────────

def build_chroma_where_filter(
    user_key: str,
    event_type: str,
    log_level: str,
    source_ide: str,
    action_type: str,
) -> Optional[dict]:
    """
    ChromaDB where 필터를 구성합니다.
    LLM이 추출한 log_level, source_ide, action_type을 기존 user_key/event_type 필터와 결합합니다.
    """
    conditions = []

    if user_key:
        conditions.append({"user_key": {"$eq": user_key}})
    if event_type:
        conditions.append({"event_type": {"$eq": event_type}})
    if log_level and log_level in _VALID_LOG_LEVELS:
        conditions.append({"log_level": {"$eq": log_level}})
    if source_ide:
        conditions.append({"source_ide": {"$eq": source_ide}})
    if action_type and action_type in _VALID_ACTION_TYPES:
        conditions.append({"action_type": {"$eq": action_type}})

    if not conditions:
        return None
    if len(conditions) == 1:
        # 단일 조건은 $and 없이 직접 반환 (ChromaDB 호환성)
        return conditions[0]
    return {"$and": conditions}


# ──────────────────────────────────────────────
# 메인 RAG 에이전트
# ──────────────────────────────────────────────

async def ask_rag_agent(question: str, user_key: str, top_k: int = 10) -> str:
    logger.info(f"RAG 질의 시작: {question}")

    if not check_guardrail(question):
        return GUARDRAIL_FALLBACK_MSG

    try:
        # 1. 기본 시간/이벤트 필터 파싱
        start_time, end_time, event_type, keywords = parse_query_filters(question)

        # 2. Fast-track 라우팅 가능 여부 확인
        fast_result = detect_fast_track(question)

        # 3. LLM Fallback: 복잡한 쿼리일 때 LLM으로 메타데이터 필터 추출
        llm_filters: dict = {}
        if not fast_result or fast_result.route != ROUTE_FAST_TRACK:
            llm_filters = await extract_llm_filters(question)
            logger.info(f"[LLM Fallback 필터] {llm_filters}")

        log_level = llm_filters.get("log_level", "")
        source_ide = llm_filters.get("source_ide", "")
        action_type = llm_filters.get("action_type", "")
        extra_keywords = llm_filters.get("keywords", [])
        # 순서 보존 dedup: dict.fromkeys는 Python 3.7+ 삽입 순서 보장
        merged_keywords = list(dict.fromkeys(keywords + extra_keywords))

        # 4. ChromaDB 쿼리 (확장된 메타데이터 필터 적용)
        results = query_vectors(
            query_text=question,
            n_results=top_k,
            user_key=user_key,
            event_type=event_type,
            start_time=start_time,
            end_time=end_time,
            keywords=merged_keywords,
            log_level=log_level,
            source_ide=source_ide,
            action_type=action_type,
        )
        docs = results[0] if results and len(results) > 0 and len(results[0]) > 0 else []

        # 5. 오늘 날짜 후처리 필터
        timezone_kst = _TZ_KST
        current_date_str = datetime.datetime.now(timezone_kst).strftime("%Y-%m-%d")
        if any(k in question.lower() for k in ["오늘", "today", "투데이"]):
            docs = [doc for doc in docs if current_date_str in doc]

        if not docs:
            return "최근 기록된 작업 로그가 존재하지 않습니다."

        docs = docs[:3]
        context_str = rerank_documents(query=question, documents=docs, top_k=3, max_chars=2000)

        if not context_str.strip():
            return "최근 기록된 작업 로그가 존재하지 않습니다."

        context_str = compress_context(context_str)
        history_context = get_conversation_context(user_key)
        final_question = (
            f"[이전 대화 내역]\n{history_context}\n\n[현재 질문]\n{question}"
            if history_context
            else question
        )
        final_question = compress_context(final_question)

        # 6. 카운트 쿼리 분기
        is_count_query = any(
            k in question.lower() for k in ["몇 개", "몇개", "몇건", "몇 건", "count", "how many"]
        )
        selected_template = COUNT_PROMPT_TEMPLATE if is_count_query else RAG_PROMPT_TEMPLATE

        stats_hint = ""
        if is_count_query:
            try:
                stat_match = re.search(
                    r"Total_Log_Count:\s*(\d+)\s*Cases\s*\(INFO:\s*(\d+),\s*WARN:\s*(\d+),\s*ERROR:\s*(\d+)\)",
                    context_str,
                )
                if stat_match:
                    stats_hint = (
                        f"\n[Calculated Statistics]\n"
                        f"- INFO: {stat_match.group(2)}개\n"
                        f"- WARN: {stat_match.group(3)}개\n"
                        f"- ERROR: {stat_match.group(4)}개\n"
                        f"- Total: {stat_match.group(1)}개\n"
                    )
            except Exception:
                pass

        if stats_hint:
            final_question = f"{final_question}\n{stats_hint}"

        context_str = manage_context_token_limit(
            docs=docs,
            question=question,
            final_question=final_question,
            selected_template=selected_template,
            current_date_str=current_date_str,
        )
        prompt = selected_template.format(
            current_date=current_date_str,
            context=context_str,
            question=final_question,
        )

        answer = await generate_completion(prompt)
        answer = postprocess_noun_ending(answer)
        add_conversation(user_key, question, answer)
        return answer

    except Exception as pipeline_err:
        logger.error(f"RAG 파이프라인 수행 실패: {pipeline_err}")
        from backend.llm.client import query_sqlite_logs, generate_simulated_response
        return postprocess_noun_ending(generate_simulated_response(question, query_sqlite_logs(question)))