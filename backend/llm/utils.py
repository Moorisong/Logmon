import re
import logging
import datetime
from typing import List, Tuple, Optional
from backend.llm.stats_db import upsert_daily_statistics

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

def parse_relative_datetime(question: str) -> Tuple[Optional[str], Optional[str]]:
    """유저 질문에서 기간을 파싱하여 (start_time, end_time)을 반환합니다."""
    timezone_kst = datetime.timezone(datetime.timedelta(hours=9))
    now = datetime.datetime.now(timezone_kst)
    
    days = 0
    if "이틀" in question: days = 2
    elif "하루" in question or "어제" in question: days = 1
    elif "일주일" in question: days = 7
    elif "3시간" in question:
        start_time = (now - datetime.timedelta(hours=3)).strftime('%Y-%m-%d %H:%M:%S')
        return start_time, now.strftime('%Y-%m-%d %H:%M:%S')
    elif "1시간" in question:
        start_time = (now - datetime.timedelta(hours=1)).strftime('%Y-%m-%d %H:%M:%S')
        return start_time, now.strftime('%Y-%m-%d %H:%M:%S')
    else:
        match = re.search(r"(\d+)일", question)
        if match: days = int(match.group(1))

    if days > 0:
        start_date = now - datetime.timedelta(days=days)
        return start_date.strftime('%Y-%m-%d 00:00:00'), now.strftime('%Y-%m-%d %H:%M:%S')
    
    return None, None

def manage_context_token_limit(docs: List[str], question: str, final_question: str, selected_template: str, current_date_str: str) -> str:
    """전달되는 로그 텍스트의 총량을 조절합니다."""
    combined = "\n\n".join(docs)
    if estimate_tokens(combined) > 1500:
        return combined[:4500] 
    return combined