# 🤖 streamlit-dashboard-agent.md - AI 개발 가이드

이 문서는 Streamlit 프론트엔드(`logmon-ui`) 애플리케이션의 화면 레이아웃, Modern White Glassmorphism 스타일링 적용, 스코어 카드 메트릭 및 3D 커스텀 아이콘 연동 구현을 위한 AI 에이전트용 설계 지침입니다.

---

## 📝 1. 연동 기획 명세 ([Logmon-ui-specification.md](file:///Users/shkim/Desktop/Project/Logmon/project_docs/Logmon/human_docs/frontend/Logmon-ui-specification.md))
* **디자인 테마**: 아주 화사하고 깨끗한 쿨톤 화이트(`#F8FAFC`) 배경 기반의 Modern Glassmorphism.
* **레이아웃**: 사이드바가 완전히 제거된 1920x1080 단일 메인 대시보드 구조 (Single-Track).
* **에셋 정책**: 텍스트 이모지 절대 금지. 모든 아이콘 위치는 귀엽고 깔끔한 2D 플랫 커스텀 아이콘 플레이스홀더(2D 로켓, 2D 시계, 2D 데이터베이스 박스, 2D 동기화 화살표, 2D 로봇 헤드)로 배치.
* **아이콘 투명도 규칙**: 모든 2D 아이콘 에셋은 배경이 없어야 합니다(투명 배경). `mix-blend-mode: multiply`를 활용해 흰 배경 찌꺼기를 날려 투명도를 확보합니다.

---

## 🤖 2. AI 개발 지침 및 설계 구조

### 🎯 목적
Streamlit 프레임워크 상에서 HTML/CSS 주입을 통해 Glassmorphism UI(`rgba(255, 255, 255, 0.4)` & `blur(12px)`)를 렌더링하고, 투명 배경의 3D 커스텀 아이콘 에셋을 완벽하게 연동합니다.

### 📦 패키지 구조
```plaintext
frontend/
├── app.py                     # 메인 진입점 (이모지 렌더링 금지, <img> 태그 활용)
├── assets/
│   ├── style.css              # Glassmorphism CSS 토큰 및 애니메이션 정의
│   └── icons/                 # 3D 커스텀 아이콘 PNG 파일 모음
└── utils/
    ├── api_client.py          
    └── chart_renderer.py      
```

### 🛠️ 개발 단계 (Step-by-Step 상세 로직)

#### 1단계: CSS Stylesheet 주입 및 백그라운드 설정
* Streamlit의 기본 테마를 무력화하고 Glassmorphism 스타일을 주입하기 위해 `app.py` 최상단에서 `style.css` 파일을 읽어 적용합니다.
* `.stApp`에 화사한 쿨톤 화이트(`#F8FAFC`) 배경을 적용하고, `glass-card` 클래스에 `backdrop-filter: blur(12px)`을 구현합니다.

#### 2단계: 메인 타이틀 및 3D 아이콘 렌더링 (이모지 대체)
* 기본 이모지 아이콘을 사용하지 않고, Base64 인코딩 또는 경로 바인딩을 통해 커스텀 아이콘을 렌더링합니다.
* 예시: `<img src="app/assets/icons/icon_logo.png" width="40" style="vertical-align: middle;">` 형태로 타이틀 옆에 아이콘을 배치.
* 우측 상단의 '에이전트 설치하기' 버튼은 아이콘 없이 푸른색 계열의 그라데이션 스타일과 상시 스스로 흔들리며 발광하는 애니메이션 효과(`.install-btn`)가 적용된 HTML 버튼을 사용합니다. 호버 시에는 발광 효과를 다소 차분하게 감소시키고 펄스를 멈춥니다.
* 페이지 로드/새로고침 시 `st.chat_input`에 의한 전체 페이지 하단 스크롤 강제 현상을 원천 차단하기 위해, `st.chat_input` 대신 `st.form` 내부의 `st.text_input`과 `st.form_submit_button` 조합을 활용하여 커스텀 챗봇 입력창을 구현합니다. 이 방식을 통해 의도치 않은 자동 스크롤과 높이 레이아웃 왜곡을 방지합니다.

#### 3단계: 대시보드 글래스모피즘 메트릭
1. **상단 요약 (에이전트 가동 상태 메트릭)**:
   * 백엔드에서 반환한 통계를 `glass-card` CSS 클래스가 적용된 HTML div 블록으로 커스텀 렌더링합니다.
   * 각 카드 제목 옆에 `icon_uptime.png`, `icon_data.png`, `icon_sync.png`를 렌더링합니다.
2. **시각화 차트**: 투명한 배경과 모던하고 직관적인 인디고 블루 색상의 라인점(Scatter, lines+markers) 차트를 Plotly로 렌더링합니다. 라인에는 부드러운 곡선 효과(spline)와 투명도 높은 채우기 색상(rgba)을 입혀 시인성을 제공하며, 차트 내 드래그, 줌, 툴바 등 불필요한 마우스 이벤트를 완전히 차단하기 위해 `config={'staticPlot': True}` 옵션을 부여하여 오직 읽기 전용(Read-Only)으로 작동하도록 제약을 겁니다.

#### 4단계: 챗 인터페이스 커스텀
* `st.chat_message` 사용 시 커스텀 아바타 이미지(챗봇: `icon_logo.png`, 사용자: `icon_user.png`)를 `avatar` 속성에 지정하여 렌더링합니다. 아바타 프로필 아이콘을 강제로 숨기는 CSS는 제거하며, 사용자 아바타는 대시보드 테마와 통일감을 주는 블루/바이올렛 그라데이션 아이콘을 사용합니다.
* 챗봇 입력창(`st.form`)에 새 메시지를 전송했을 때 대화 내용이 입력창 아래에 렌더링되는 현상을 방지하고 입력창이 항상 맨 아래에 위치하도록, 대화 역사 및 신규 답변 렌더링을 감싸는 `st.container()`를 사전에 정의하여 그 내부에서 메시지 렌더링을 처리합니다.


---

## 🚨 3. 철벽 코드 컨벤션 및 제약 조건
* **[이모지 사용 절대 금지]**: 코드 리뷰 및 스타일링 과정에서 어떠한 형태의 유니코드 이모지도 허용하지 마세요. 모두 `icons/` 디렉터리의 이미지 에셋으로 교체합니다.
* **[300줄 분리 규칙]**: 코드가 복잡해질 경우 `utils/` 내부 모듈로 확실히 격리하여 파일당 **300줄**을 통제하세요.
* **[로딩 가속화]**: `st.cache_data`나 `st.cache_resource` 데코레이터를 데이터 조회 및 로컬 에셋(이미지 Base64 인코딩 등) 로딩 함수에 알맞게 적용하세요.
