import os
from typing import List
from fastapi import Header, HTTPException, status

def get_allowed_api_keys() -> List[str]:
    """
    환경변수(또는 .env)에서 허용된 API Key 목록을 가져와 리스트로 파싱합니다.
    구분자는 쉼표(,)를 기본으로 사용합니다.
    """
    raw_keys = os.getenv("ALLOWED_API_KEYS", "")
    if not raw_keys:
        return []
    
    # 공백 제거 후 리스트로 파싱
    return [key.strip() for key in raw_keys.split(",") if key.strip()]

async def verify_api_key(x_logmon_api_key: str = Header(..., alias="X-LogMon-API-Key")) -> str:
    """
    들어온 요청의 헤더에서 X-LogMon-API-Key를 추출하고, 
    환경 변수의 ALLOWED_API_KEYS 목록에 존재하는지 1차 비교 체크합니다.
    통과 시 유효한 API Key를 반환하고, 실패 시 401 예외를 반환합니다.
    """
    allowed_keys = get_allowed_api_keys()
    
    # 런타임에 키 설정이 전혀 없다면, 보안상 모든 요청을 거부하거나 
    # 혹은 테스트 목적으로 통과시킬 수 있습니다. 여기서는 보안 원칙에 따라 거부합니다.
    if not allowed_keys:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Server configuration error: ALLOWED_API_KEYS not set."
        )
        
    if x_logmon_api_key not in allowed_keys:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid X-LogMon-API-Key"
        )
        
    return x_logmon_api_key
