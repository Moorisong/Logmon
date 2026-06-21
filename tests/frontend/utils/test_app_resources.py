import os
import base64
import pytest

def test_chat_avatar_resources_exist():
    # 챗봇 및 사용자 아바타 이미지 경로 정의
    user_avatar_path = "frontend/assets/icons/icon_user.png"
    bot_avatar_path = "frontend/assets/icons/icon_logo.png"
    
    # 1. 파일 존재 여부 검증
    assert os.path.exists(user_avatar_path), f"{user_avatar_path} 파일이 존재하지 않습니다."
    assert os.path.exists(bot_avatar_path), f"{bot_avatar_path} 파일이 존재하지 않습니다."
    
    # 2. 이미지 파일 로드 및 Base64 인코딩 검증
    for path in [user_avatar_path, bot_avatar_path]:
        with open(path, "rb") as f:
            data = f.read()
            assert len(data) > 0, f"{path} 파일이 비어 있습니다."
            encoded = base64.b64encode(data).decode()
            assert len(encoded) > 0, f"{path}의 Base64 인코딩 결과가 비어 있습니다."
