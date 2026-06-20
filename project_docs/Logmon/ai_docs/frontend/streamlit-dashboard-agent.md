# 🤖 streamlit-dashboard-agent.md - AI 개발 가이드

이 문서는 Streamlit 프론트엔드(`logmon-ui`) 애플리케이션의 화면 레이아웃, Pastel CSS 스타일링 적용, 스코어 카드 메트릭, 트렌드 차트 및 하단 RAG 챗 인터페이스 구현을 위한 AI 에이전트용 설계 지침입니다.

---

## 📝 1. 연동 기획 명세 ([Logmon-ui-specification.md](file:///Users/shkim/Desktop/Project/Logmon/project_docs/Logmon/human_docs/frontend/Logmon-ui-specification.md))
* **디자인 테마**: Trendy Pastel Tone, 뉴모피즘(레트로 엠보싱) 스타일 구현. 너무 촌스럽지 않은 세련된 입체감 강조.
* **레이아웃**: 단일 메인 대시보드 구조 (Single-Track). 사이드바 완전 제거. 상단 타이틀 옆에 설치하기 버튼 배치. 하단에 RAG 챗 인터페이스 구성.
* **데이터 교환**: SQLite 직접 마운트를 금지하며, 오직 REST API (`BACKEND_URL`)를 통해서만 수행.

---

## 🤖 2. AI 개발 지침 및 설계 구조

### 🎯 목적
* 가볍고 직관적인 Streamlit 프레임워크 상에서 HTML/CSS 주입을 통해 뉴모피즘의 깊이감 있는 엠보싱 UI를 렌더링하고, 차트 시각화 및 대화 인터페이스를 매끄럽게 연동합니다.

### 📦 패키지 및 타깃 클래스 경로 구조
```plaintext
frontend/
├── app.py                     # Streamlit 애플리케이션 메인 진입점
├── assets/
│   └── style.css              # 엠보싱 효과 및 컬러 CSS 토큰 정의 파일
└── utils/
    ├── api_client.py          # 백엔드 REST API 요청 헬퍼
    └── chart_renderer.py      # Plotly 또는 Altair 기반 파스텔 세이지 차트 생성 모듈
```

### 🛠️ 개발 단계 (Step-by-Step 상세 로직)

#### 1단계: CSS Stylesheet 주입
* Streamlit의 기본 테마를 무력화하고 엠보싱 스타일을 주입하기 위해 `app.py` 최상단에서 `style.css` 파일을 읽어 `st.markdown(..., unsafe_allow_html=True)` 형태로 강제 바인딩합니다.
* 사이드바 배경색, 메인 컨테이너 패딩, 엠보싱 카드 효과 클래스 등을 스타일 시트에 정의합니다.

#### 2단계: 메인 타이틀 및 상단 컨트롤 영역 구현
* `st.sidebar`는 완전히 배제하고 사용하지 않습니다. (사이드바 숨김 처리)
* 화면 최상단에 `st.columns`를 활용하여 좌측에는 👾 `LogMon` 메인 타이틀과 소개를 배치하고, 우측에는 세련된 **'🚀 에이전트 설치하기'** 버튼(`st.page_link("pages/install.py")` 활용)을 배치하여 클릭 시 설치 전용 페이지로 이동하도록 합니다.

#### 3단계: 대시보드 메트릭 및 챗봇 인터페이스
1. **상단 요약 (에이전트 가동 상태 메트릭)**: 타이틀 하단에 `st.columns(3)`를 생성한 후 메트릭 컴포넌트를 호출합니다. 백엔드(`GET /api/logmon/stats`)에서 가공하여 반환한 통계 정보를 엠보싱 효과 카드 내에 표현합니다.
   * **가동 시간**: 최초 수집일 이후 경과일 (예: "📅 에이전트 가동: 12일째")
   * **누적 데이터**: 에이전트를 통해 수집된 누적 로그 라인 수/바이트 크기 (예: "📦 에이전트 자동 수집: 총 14,500라인 (2.4 MB)")
   * **동기화 상태**: 가장 마지막으로 로그가 들어온 시각 (예: "🔄 최근 동기화: 3분 전 (정상)")
2. **시각화 차트**: Altair 또는 Plotly를 활용하여 부드러운 파스텔 세이지 그린 `#A3C1AD` 컬러를 메인으로 채택한 트렌드 그래프를 렌더링합니다.
3. **챗 인터페이스**: `st.chat_message` 구조를 래핑하여 둥근 형태가 아닌 각진 사각형 모양과 파스텔 피치/세이지 그린 배경색 CSS를 결합해 대화 내역을 표기하고, 맨 하단에 `st.chat_input`을 단단하게 고정합니다.

#### 4단계: 설치 가이드 페이지 연동 (pages/install.py)
* `frontend/pages/install.py` 파일을 생성하고 메인 앱과 동일한 뉴모피즘 `style.css`를 주입합니다.
* `st.page_link("app.py", label="⬅️ 메인 대시보드로 돌아가기")`를 통해 뒤로가기 동선을 확보합니다.
* 엠보싱 카드 내부에 `st.tabs(["🍏 macOS / Linux", "🪟 Windows"])`를 선언하고, 각 탭 내부에 `st.code` 위젯으로 설치용 Curl 및 PowerShell 스크립트를 세련되게 노출합니다.

---

## 🚨 3. 철벽 코드 컨벤션 및 제약 조건
* **[300줄 분리 규칙]**: HTML 주입, 스타일시트 파싱, Plotly 차트 선언 등의 자질구레한 로직은 `app.py`에 전부 우겨넣지 말고, `utils/` 내부 모듈로 확실히 격격 분리하여 파일당 **300줄**을 통제하세요.
* **[API URL 환경변수화]**: 백엔드 통신 주소는 소스 코드에 절대 하드코딩하지 말고 환경변수 `BACKEND_URL`을 조회하고 없을 경우의 기본 폴백값(`http://localhost:8000`)을 구성하도록 설계하세요.
* **[로딩 가속화]**: Streamlit 특유의 재실행(Rerun) 시 발생하는 깜빡임 및 API 과부하를 예방하기 위해 `st.cache_data`나 `st.cache_resource` 데코레이터를 데이터 조회 함수에 알맞게 적용하세요.
