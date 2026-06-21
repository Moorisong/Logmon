import base64

def get_base64_image(image_path: str) -> str:
    """
    이미지 파일을 로드하여 Base64로 인코딩한 문자열을 반환합니다.
    """
    with open(image_path, "rb") as f:
        data = f.read()
    return base64.b64encode(data).decode()
