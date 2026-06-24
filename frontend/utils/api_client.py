import os
import requests
import streamlit as st
from typing import Dict, Any

# 도커 환경 내부 통신용 URL로 우선순위 변경
BACKEND_URL = "http://logmon-backend:8000"
LOGMON_API_KEY = os.getenv("LOGMON_API_KEY", "default_dev_key")

def get_headers() -> Dict[str, str]:
    return {"X-LogMon-API-Key": LOGMON_API_KEY}

@st.cache_data(ttl=10)
def fetch_stats() -> Dict[str, Any]:
    """
    백엔드에서 통계 데이터를 가져옵니다. 
    에러 발생 시에도 무조건 유효한 딕셔너리를 반환하여 NoneType 에러를 방지합니다.
    """
    url = f"{BACKEND_URL}/api/logmon/stats"
    try:
        response = requests.get(url, headers=get_headers(), timeout=5.0)
        response.raise_for_status()
        data = response.json()
        
        # 데이터가 None일 경우 안전한 기본값을 반환
        if data is None:
            return {"is_online": False, "is_agent_installed": False, "total_logs": 0, "trend_7d": []}
        return data
        
    except Exception:
        # 어떤 예외 상황에서도 None을 반환하지 않음
        return {
            "is_online": False,
            "is_agent_installed": False,
            "total_logs": 0,
            "today_tokens": 0,
            "has_code_ratio": 0.0,
            "trend_7d": [],
            "uptime_days": 0,
            "total_lines": 0,
            "total_bytes": 0,
            "last_sync_time": None
        }

def send_chat(question: str) -> str:
    """
    RAG 챗 엔진에 질의합니다. 
    LLM 추론 시간을 고려하여 타임아웃을 180초(3분)로 설정합니다.
    """
    url = f"{BACKEND_URL}/api/logmon/chat"
    payload = {"question": question}
    try:
        # 타임아웃을 180초로 대폭 상향
        response = requests.post(url, json=payload, headers=get_headers(), timeout=180.0)
        
        # 상태 코드 확인
        if response.status_code != 200:
            return f"서버가 응답하지 않습니다 (상태 코드: {response.status_code})"
            
        data = response.json()
        
        # 'answer' 키 확인
        if data and isinstance(data, dict):
            return data.get("answer", "엔진이 답변을 생성하지 못했습니다.")
        return "엔진 응답 포맷이 올바르지 않습니다."
            
    except requests.exceptions.Timeout:
        return "AI 엔진이 답변을 생성하는 데 너무 오래 걸렸습니다 (타임아웃 발생). 다시 시도해 주세요."
    except Exception as e:
        # 프론트엔드 터미널에 에러 상세 출력
        print(f"DEBUG: Chat Exception - {e}")
        return "현재 AI 엔진 서비스가 일시 점검 중입니다."