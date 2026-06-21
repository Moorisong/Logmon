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

def test_install_page_ui_components():
    # 에이전트 설치 페이지 파일 존재 여부
    install_page_path = "frontend/pages/install.py"
    assert os.path.exists(install_page_path), "install.py 파일이 존재하지 않습니다."
    
    with open(install_page_path, "r", encoding="utf-8") as f:
        content = f.read()
        
    # UI 회귀 방지를 위한 요소 포함 여부 검증
    # 1. 뒤로가기 버튼이 back-btn 클래스를 활용하는지 확인
    assert "class=\"back-btn\"" in content or "class='back-btn'" in content
    
    # 2. 안내 텍스트 및 로고몬 이미지 정렬 배치 여부
    assert "터미널 환경에 맞게 아래 스크립트를 복사하여 실행하시면 LogMon 에이전트가 자동 설치됩니다." in content
    assert "logo_b64" in content
    
    # 3. 영역 구분을 위한 st.container(border=True) 사용 확인
    assert "st.container(border=True)" in content
    
    # 4. 이전 마스킹 가이드(BACKEND_URL: ********)가 확실히 제거되었는지 확인
    assert "BACKEND_URL: ********" not in content

