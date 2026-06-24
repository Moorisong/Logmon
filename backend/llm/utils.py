import re
import logging
import datetime
from typing import List, Tuple, Optional

logger = logging.getLogger(__name__)

def format_log_message(log_id: int, timestamp: str, source: str, log_level: str, target: str, raw_message: str) -> str:
    """LLM 추론을 위해 로그를 Key-Value 템플릿으로 구조화합니다."""
    source_lower = source.lower()
    if any(x in source_lower for x in ["vscode", "code"]): source_mapped = "VSCode"
    elif any(x in source_lower for x in ["intellij", "jetbrains", "idea"]): source_mapped = "JetBrains"
    elif "cursor" in source_lower: source_mapped = "Cursor"
    elif "git" in source_lower: source_mapped = "Git"
    else: source_mapped = source

    return f"""[LOG_ENTRY]
ID: {log_id}
DateTime: {timestamp}
Source: {source_mapped}
LogLevel: {log_level.upper()}
Action: {target}
Message: {raw_message}
[END_LOG]"""

def estimate_tokens(text: str) -> float:
    return len(text) / 3.0

def postprocess_noun_ending(text: str) -> str:
    if not text: return ""
    rules = [
        (r"되었습니다\.?", "됨."), (r"되었습니다", "됨"),
        (r"하였습니다\.?", "함."), (r"했습니다\.?", "했음."),
        (r"합니다\.?", "함."), (r"입니다\.?", "임."),
        (r"바랍니다\.?", "요망.")
    ]
    processed = text
    for pattern, repl in rules:
        processed = re.sub(pattern, repl, processed)
    return processed

def parse_relative_datetime(question: str) -> Tuple[str, str]:
    """
    유저 질문에서 기간을 파싱하여 (start_time, end_time)을 반환합니다.
    매칭되는 기간이 없으면 최근 10일을 기본값으로 반환합니다.
    """
    timezone_kst = datetime.timezone(datetime.timedelta(hours=9))
    now = datetime.datetime.now(timezone_kst)
    
    # 1. "이번 달" / "이번달" 파싱
    if "이번달" in question or "이번 달" in question:
        start_date = datetime.datetime(now.year, now.month, 1, 0, 0, 0)
        return start_date.strftime('%Y-%m-%d %H:%M:%S'), now.strftime('%Y-%m-%d %H:%M:%S')

    # 2. 월(Month) 파싱 ("6월", "6월달")
    month_match = re.search(r"(\d+)월", question)
    if month_match:
        target_month = int(month_match.group(1))
        start_date = datetime.datetime(now.year, target_month, 1, 0, 0, 0)
        # 다음 달 1일에서 1초를 빼서 해당 월의 마지막 순간 확보
        next_month = (target_month % 12) + 1
        next_year = now.year + (1 if target_month == 12 else 0)
        end_date = datetime.datetime(next_year, next_month, 1) - datetime.timedelta(seconds=1)
        return start_date.strftime('%Y-%m-%d %H:%M:%S'), end_date.strftime('%Y-%m-%d %H:%M:%S')

    # 3. 시간 파싱
    if "3시간" in question:
        start_time = (now - datetime.timedelta(hours=3))
        return start_time.strftime('%Y-%m-%d %H:%M:%S'), now.strftime('%Y-%m-%d %H:%M:%S')
    if "1시간" in question:
        start_time = (now - datetime.timedelta(hours=1))
        return start_time.strftime('%Y-%m-%d %H:%M:%S'), now.strftime('%Y-%m-%d %H:%M:%S')

    # 4. 일수 파싱
    days = 10  # 기본값: 10일
    if "이틀" in question: days = 2
    elif "하루" in question or "어제" in question: days = 1
    elif "일주일" in question: days = 7
    elif "5일" in question: days = 5
    elif "3일" in question: days = 3
    else:
        match = re.search(r"(\d+)일", question)
        if match: 
            days = int(match.group(1))

    start_date = now - datetime.timedelta(days=days)
    return start_date.strftime('%Y-%m-%d 00:00:00'), now.strftime('%Y-%m-%d %H:%M:%S')

def manage_context_token_limit(docs: List[str], question: str, final_question: str, selected_template: str, current_date_str: str) -> str:
    """전달되는 로그 텍스트의 총량을 조절합니다."""
    combined = "\n\n".join(docs)
    if estimate_tokens(combined) > 1500:
        return combined[:4500] 
    return combined