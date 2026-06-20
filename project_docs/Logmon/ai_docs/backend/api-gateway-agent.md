# 🤖 api-gateway-agent.md - AI 개발 가이드

이 문서는 FastAPI 기반의 백엔드(`logmon-backend`) API 게이트웨이, 보안 인증 필터 및 크로스 플랫폼 에이전트 바이너리의 정적 서빙 구현을 위한 AI 에이전트용 설계 지침입니다.

---

## 📝 1. 연동 기획 명세 ([Logmon-architecture.md](file:///Users/shkim/Desktop/Project/Logmon/project_docs/Logmon/human_docs/system/Logmon-architecture.md), [Logmon-agent-specification.md](file:///Users/shkim/Desktop/Project/Logmon/project_docs/Logmon/human_docs/agent/Logmon-agent-specification.md))
* **FastAPI 엔드포인트**: 에이전트로부터 로그를 전송받는 `/api/logmon/upload` 및 설치 스크립트/바이너리 다운로드를 제공하는 정적 경로 제공.
* **보안 필터**: 모든 요청 헤더에서 `X-LogMon-API-Key`를 추출하여 SQLite 검증 수행.
* **정적 서빙**: PyInstaller로 컴파일된 에이전트 바이너리 및 설치 스크립트를 Nginx가 바인딩하는 경로인 `/api/logmon/static`을 통해 노출.

---

## 🤖 2. AI 개발 지침 및 설계 구조

### 🎯 목적
* 로그몬 백엔드에 안전한 REST API 통로를 열고, 에이전트용 자원을 웹에 안전하게 제공합니다.

### 📦 패키지 및 타깃 클래스 경로 구조
```plaintext
backend/
├── main.py                    # FastAPI 애플리케이션 진입점 및 static mount
├── api/
│   ├── dependencies.py        # API Key 검증 종속성 (get_api_key)
│   └── routes.py              # upload, stats, chat 엔드포인트 라우팅
└── static/                    # PyInstaller 바이너리 및 쉘 스크립트 서빙용 디렉터리
    ├── install-agent.sh
    ├── uninstall-agent.sh
    ├── install-agent.ps1
    └── uninstall-agent.ps1
```

### 🛠️ 개발 단계 (Step-by-Step 상세 로직)

#### 1단계: 정적 디렉터리 바인딩
* `main.py` 파일 내부에 FastAPI 내장 `StaticFiles` 모듈을 연동하여 `/api/logmon/static` 경로로 디렉터리를 노출시킵니다.
```python
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

app = FastAPI(docs_url="/api/logmon/docs", openapi_url="/api/logmon/openapi.json")

# 정적 파일 서빙 등록
app.mount("/api/logmon/static", StaticFiles(directory="static"), name="static")
```

#### 2단계: API Key 보안 헤더 필터 추가
* `api/dependencies.py` 파일 내에서 API Key 검증 데코레이터를 구현합니다.
```python
from fastapi import Header, HTTPException, status

async def verify_api_key(x_logmon_api_key: str = Header(..., alias="X-LogMon-API-Key")):
    # TODO: SQLite DB를 조회하여 해당 API Key가 유효한지 확인하는 로직 수행
    is_valid = check_db_valid_key(x_logmon_api_key) 
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-LogMon-API-Key"
        )
    return x_logmon_api_key
```

#### 3단계: 로그 업로드 API 설계
* 에이전트가 5분 주기로 발송하는 데이터를 수집하여 검증된 키에 매핑하는 라우트를 만듭니다.
```python
from fastapi import APIRouter, Depends
from api.dependencies import verify_api_key

router = APIRouter(prefix="/api/logmon")

@router.post("/upload")
async def upload_log(payload: dict, api_key: str = Depends(verify_api_key)):
    # payload: { "source_tool": "Cursor", "logs": [...] }
    # DB 적재 및 Chroma DB RAG 벡터 파이프라인 연동 트리거
    return {"status": "success", "processed_records": len(payload.get("logs", []))}
```

#### 4단계: 대시보드 통계 API (Stats API) 설계
* 프론트엔드 대시보드의 에이전트 가동 상태 메트릭을 지원하기 위해 `GET /api/logmon/stats` 엔드포인트를 라우터에 추가합니다.
* 응답(Response)에 반드시 다음 항목을 포함해야 합니다:
  1. `uptime_days`: 최초 수집일 이후 경과일 (가동 며칠 차)
  2. `total_lines` 및 `total_bytes`: 에이전트를 통해 수집된 누적 로그 라인 수 및 바이트 크기
  3. `last_sync_time`: 가장 마지막으로 로그가 들어온 시각 (ISO 포맷 또는 경과 시간)

---

## 🚨 3. 철벽 코드 컨벤션 및 제약 조건
* **[300줄 분리 규칙]**: `main.py`나 `routes.py`에 모든 로직을 쏟아넣지 말고, 라우터 분할(`APIRouter`)을 통해 파일당 **300줄**을 엄격히 방어하세요.
* **[CORS 제한]**: 외부 도메인에서 API를 직접 치는 것을 막기 위해 `CORSMiddleware` 설정을 로컬 및 허용된 Streamlit 컨테이너(`logmon-ui`) 주소로 제한하세요.
* **[예외 처리]**: 클라이언트가 전송한 JSON 페이로드 구조가 망가져 있을 때 500 내부 서버 에러를 내지 말고, 422 Unprocessable Entity 혹은 커스텀 에러 Response를 제공하여 우아하게 대응하세요.
