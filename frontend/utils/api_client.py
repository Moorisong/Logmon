import os
import requests
import streamlit as st
from typing import Dict, Any

# 백엔드 URL 환경변수 처리 (기본값 하드코딩 탈피)
# Docker-compose 등 외부에서 넘겨주지 않으면 https://logmon.haroo.site 폴백
BACKEND_URL = os.getenv("BACKEND_URL", "https://logmon.haroo.site").rstrip('/')
LOGMON_API_KEY = os.getenv("LOGMON_API_KEY", "default_dev_key")

def get_headers() -> Dict[str, str]:
    return {"X-LogMon-API-Key": LOGMON_API_KEY}


def fetch_stats() -> Dict[str, Any]:
    """
    백엔드에서 통계 데이터를 긁어옵니다. 
    TTL 60초 캐싱을 통해 Streamlit의 고질적인 Rerun 시 깜빡임/API 과부하 방지
    """
    url = f"{BACKEND_URL}/api/logmon/stats"
    try:
        response = requests.get(url, headers=get_headers(), timeout=5.0)
        response.raise_for_status()
        data = response.json()
        data["is_online"] = True
        return data
    except requests.exceptions.RequestException as e:
        return {
            "total_logs": 0,
            "today_tokens": 0,
            "has_code_ratio": 0.0,
            "trend_7d": [],
            "uptime_days": 0,
            "total_lines": 0,
            "total_bytes": 0,
            "last_sync_time": None,
            "is_online": False,
            "is_agent_installed": False
        }

def send_chat(question: str) -> str:
    """
    RAG 챗 엔진에 질의합니다. (비동기 체감이 나도록 앱에서 spinner와 함께 사용)
    """
    url = f"{BACKEND_URL}/api/logmon/chat"
    payload = {"question": question}
    try:
        response = requests.post(url, json=payload, headers=get_headers(), timeout=40.0)
        response.raise_for_status()
        return response.json().get("answer", "응답 포맷 에러")
    except requests.exceptions.Timeout:
        return "현재 AI 엔진 서비스가 일시 정지 중이거나 과부하 상태입니다."
    except requests.exceptions.RequestException as e:
        return "서버 통신에 실패했습니다."

def upload_log(file_content: bytes, filename: str) -> bool:
    """
    수동 파일 업로드를 백엔드에 전송합니다. (현재는 raw text 로 가정)
    실무에선 multipart/form-data 또는 raw_message 분해 후 POST 전송.
    여기서는 MVP로 텍스트 파일을 읽어 그대로 쏜다고 가정합니다.
    """
    url = f"{BACKEND_URL}/api/logmon/upload"
    
    try:
        text_data = file_content.decode("utf-8")
        payload = {
            "source_tool": "Manual Upload UI",
            "event_type": "MANUAL",
            "raw_message": text_data,
            "task_name": filename
        }
        res = requests.post(url, json=payload, headers=get_headers(), timeout=10.0)
        res.raise_for_status()
        return True
    except Exception as e:
        st.error(f"파일 업로드 실패: {e}")
        return False
