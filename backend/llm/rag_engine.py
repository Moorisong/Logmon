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
    """로그 청크 문자열에서 타임스탬프를 파싱하여 반환합니다. 파싱 불가 시 최대 시간값을 반환합니다."""
    match = re.search(r"\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]", doc)
    if match:
        try:
            return datetime.datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S")
        except ValueError:
            pass
    return datetime.datetime.max

def parse_query_filters(question: str) -> tuple:
    """
    사용자 질문에서 시간대 범위(start_time, end_time), 로그 레벨(event_type), 
    그리고 핵심 기술 키워드 리스트(keywords)를 추출합니다.
    """
    q_lower = question.lower()
    
    # KST 기준 타임존 세팅
    timezone_kst = datetime.timezone(datetime.timedelta(hours=9))
    now = datetime.datetime.now(timezone_kst)
    today = now.date()
    yesterday = today - datetime.timedelta(days=1)
    
    start_time = None
    end_time = None
    
    # 1. 상대 기간 날짜 파싱 시도 (예외 예방 안전장치)
    try:
        start_time, end_time = parse_relative_datetime(question)
    except Exception as parse_err:
        logger.error(f"[날짜 파서 오류] {parse_err}")
        start_time, end_time = None, None
        
    # 상대 기간 파싱 결과가 없는 경우 기존 키워드 기반 매칭으로 Fallback
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
        
    # 2. 에러 레벨 파싱
    event_type = ""
    if any(w in q_lower for w in ["critical", "크리티컬", "error", "에러", "오류", "실패", "fail"]):
        event_type = "ERROR"
    elif any(w in q_lower for w in ["warning", "경고", "warn"]):
        event_type = "WARNING"
        
    # 3. 키워드 필터 추출
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
        "warning": ["warning", "경고", "warn"]
    }
    
    for key, synonyms in kw_map.items():
        if any(syn in q_lower for syn in synonyms):
            keywords.append(key)
            keywords.extend(synonyms)
            
    return start_time, end_time, event_type, keywords

def compress_context(text: str) -> str:
    """
    컨텍스트 내부의 불필요한 공백을 정규식으로 압축하여 토큰 수를 절약합니다.
    단, 타임스탬프와 로그 메시지 내용의 구분 및 가독성은 유지합니다.
    """
    if not text:
        return ""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    cleaned = "\n".join(lines)
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    return cleaned

async def ask_rag_agent(question: str, user_key: str, top_k: int = 10) -> str:
    """
    사용자의 질문을 기반으로 Chroma DB에서 1차 검색 후,
    CrossEncoder 리랭커로 재정렬하고 Ollama에 프롬프트를 주입하여 답변을 생성하는 고도화된 RAG 파이프라인.
    """
    logger.info(f"RAG 질의 시작: {question}")
    
    if not check_guardrail(question):
        return GUARDRAIL_FALLBACK_MSG
        
    try:
        # 2. 스마트 프리필터링 (시간, 레벨, 키워드 쿼리 파서 작동)
        start_time, end_time, event_type, keywords = parse_query_filters(question)
        
        # 3. Chroma DB 1차 검색
        results = query_vectors(
            query_text=question,
            n_results=top_k,
            user_key=user_key,
            event_type=event_type,
            start_time=start_time,
            end_time=end_time,
            keywords=keywords
        )
            
        # 4. 2-Stage Retrieval (리랭킹) 및 컨텍스트 부재 방어
        docs = results[0] if results and len(results) > 0 and len(results[0]) > 0 else []
        logger.info(f"Retrieved docs count: {len(docs)} for user_key: {user_key}, event_type: {event_type}, docs: {docs}")
        
        timezone_kst = datetime.timezone(datetime.timedelta(hours=9))
        current_date_str = datetime.datetime.now(timezone_kst).strftime('%Y-%m-%d')
        
        # 4.1. '오늘' 의도가 있다면 파이썬 단에서 엄격하게 Drop
        if any(k in question.lower() for k in ["오늘", "today", "투데이"]):
            docs = [doc for doc in docs if current_date_str in doc]
            
        logger.info(f"[날짜 후처리 필터 결과] 필터링 후 남은 청크 개수: {len(docs)}")
        
        # 4.2. 필터링 후 알맹이가 진짜 0건이면 여기서 튕김
        if not docs:
            return "최근 기록된 작업 로그가 존재하지 않습니다."
            
        # 4.3. 최종 주입할 청크 리스트 최대 개수 3개로 제한
        docs = docs[:3]
            
        # 리랭커를 통한 정렬 및 길이 조절 (Top-3, Max 2000자)
        context_str = rerank_documents(query=question, documents=docs, top_k=3, max_chars=2000)
        
        if not context_str.strip():
            return "최근 기록된 작업 로그가 존재하지 않습니다."
            
        context_str = compress_context(context_str)
        
        # 5. Window Memory 적용
        history_context = get_conversation_context(user_key)
        final_question = f"[이전 대화 내역]\n{history_context}\n\n[현재 질문]\n{question}" if history_context else question
        final_question = compress_context(final_question)
            
        # 6. 프롬프트 바인딩 및 동적 조율 루프 (지침 C)
        is_count_query = any(k in question.lower() for k in ["몇 개", "몇개", "몇건", "몇 건", "count", "how many"])
        selected_template = COUNT_PROMPT_TEMPLATE if is_count_query else RAG_PROMPT_TEMPLATE
        
        # [STATISTICS] 파싱 및 안전장치 추가
        stats_hint = ""
        if is_count_query:
            try:
                # context_str에서 [STATISTICS] 정보를 정규식으로 파싱
                # Total_Log_Count: 42 Cases (INFO: 30, WARN: 8, ERROR: 4)
                stat_match = re.search(
                    r"Total_Log_Count:\s*(\d+)\s*Cases\s*\(INFO:\s*(\d+),\s*WARN:\s*(\d+),\s*ERROR:\s*(\d+)\)",
                    context_str
                )
                if stat_match:
                    total_c = stat_match.group(1)
                    info_c = stat_match.group(2)
                    warn_c = stat_match.group(3)
                    err_c = stat_match.group(4)
                    stats_hint = f"\n[Calculated Statistics]\n- INFO: {info_c}개\n- WARN: {warn_c}개\n- ERROR: {err_c}개\n- Total: {total_c}개\n"
            except Exception as stat_err:
                logger.error(f"[STATISTICS 파싱 에러] {stat_err}")
        
        if stats_hint:
            final_question = f"{final_question}\n{stats_hint}"

        # 동적 토큰 조율 (Hard Ceiling) - utils.py에 위임
        context_str = manage_context_token_limit(
            docs=docs,
            question=question,
            final_question=final_question,
            selected_template=selected_template,
            current_date_str=current_date_str
        )
        
        prompt = selected_template.format(
            current_date=current_date_str,
            context=context_str,
            question=final_question
        )
        
        answer = await generate_completion(prompt)
        answer = postprocess_noun_ending(answer)
        
        # 7. 대화 히스토리 저장
        add_conversation(user_key, question, answer)
        
        return answer
    except Exception as pipeline_err:
        logger.error(f"RAG 파이프라인 수행 실패 (SQLite Fallback 구동): {pipeline_err}")
        from backend.llm.client import query_sqlite_logs, generate_simulated_response
        rows = query_sqlite_logs(question)
        simulated_ans = generate_simulated_response(question, rows)
        return postprocess_noun_ending(simulated_ans)
