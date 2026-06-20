# 🎨 로그몬 (LogMon) UI/UX 디자인 명세서 (Logmon-ui-specification.md)

이 문서는 Streamlit 기반 프론트엔드의 Pastel CSS 테마, 뉴모피즘 엠보싱 비주얼 컨셉, 레이아웃 및 컴포넌트 명세를 규정합니다.

---

## 🎨 1. 컬러 팔레트 (Pastel Tone CSS)

전체 테마는 눈이 피로하지 않으면서도 안정감을 주는 소프트 파스텔 톤을 적용합니다.

* **메인 배경색 (Main Background)**: `#F4F5F7` (아주 연한 파스텔 그레이 - 엠보싱 입체 효과를 내기에 가장 최적화된 배경색)
* **사이드바 배경색 (Sidebar Background)**: `#EAF0F6` (차분하고 맑은 파스텔 블루 그레이)
* **포인트 컬러 1 (Primary)**: `#A3C1AD` (마일드한 파스텔 세이지 그린 - 안정감을 주는 톤)
* **포인트 컬러 2 (Secondary)**: `#FAD0C4` (부드러운 파스텔 피치 핑크)
* **텍스트 컬러 (Text)**: `#3A4146` (눈이 피로하지 않은 소프트 차콜)

---

## 🔲 2. 비주얼 컨셉: 소프트 레트로 엠보싱 (뉴모피즘 & 반듯함)

둥근 형태를 남발하는 대신, 반듯한 사각형 구조를 유지하면서 입체감을 주는 디자인을 지향합니다.

### 1) 엠보싱 효과 (Soft Shadow CSS)
컴포넌트(카드, 버튼 등)의 테두리를 날카롭지 않고 반듯한 수준(`border-radius: 4px ~ 6px`)으로 유지하고, 밝은 그림자와 어두운 그림자를 대각선 방향으로 양방향 적용하여 소프트한 입체감을 연출합니다.

```css
/* 튀어나온 입체감 (Embossed / Raised Card) */
.embossed-card {
    background: #F4F5F7;
    border-radius: 6px;
    box-shadow: 5px 5px 10px #e0e1e3,
                -5px -5px 10px #ffffff;
    border: none;
    padding: 15px;
}

/* 들어간 입체감 (Debossed / Sunken Input) */
.debossed-input {
    background: #F4F5F7;
    border-radius: 6px;
    box-shadow: inset 3px 3px 6px #e0e1e3,
                inset -3px -3px 6px #ffffff;
    border: none;
}
```

### 2) 타이포그래피 (Typography)
* 기본 폰트로는 가독성이 우수한 고딕 계열(`Noto Sans KR`, `Inter`)을 메인으로 사용합니다.
* 메인 로고나 최상단 헤더 타이틀 등 주요 포인트 텍스트에만 미세한 레트로 감성의 픽셀/모노스페이스 폰트(`Monospace`, `Courier New`)를 부분 적용합니다.

---

## 🗂️ 3. 레이아웃 및 컴포넌트 구성

화면은 **좌측 제어판(영역 A)**과 **우측 메인 대시보드(영역 B) 및 RAG 챗봇(영역 C)**의 투 트랙(Two-Track)으로 나누어 배치합니다.

### 📁 영역 A: 좌측 제어판 (Sidebar Console)
* **서비스 로고**: 👾 `LogMon` 타이틀을 파스텔 피치 핑크 배경의 엠보싱 상자 안에 표시.
* **수동 업로드 위젯 (경로 A)**: `st.file_uploader`를 커스텀 스타일링하여 점선 테두리를 제거하고, 연한 파스텔 블루 톤의 반듯하고 널찍한 드래그 앤 드롭 영역 구현.
* **크로스 플랫폼 에이전트 설정 가이드 (경로 B)**: `st.tabs`를 이용해 [🍏 macOS / Linux]와 [🪟 Windows]용 원클릭 수집 스크립트 복사 기능 제공 (`st.code`).

### 📊 영역 B: 우측 메인 대시보드 (Main Dashboard)
* **요약 스코어 카드 (에이전트 가동 상태 메트릭)**: 가로형으로 배치되는 3개의 반듯한 엠보싱 카드(`st.metric`).
  * **설치 후 경과일 (가동 시간)**: 📅 "에이전트 가동: X일째" (최초 로그 수집일로부터 지난 날짜)
  * **누적 수집 데이터량**: 📦 "에이전트 자동 수집: 총 X라인 (또는 X MB)"
  * **가장 최신 동기화 시간 (가장 중요! ⭐)**: 🔄 "최근 동기화: X분 전 (정상)"
* **시각화 트렌드 차트**: Plotly / Altair를 이용해 부드러운 파스텔 세이지 그린 컬러 중심의 막대/선 그래프 렌더링.

### 💬 영역 C: 하단 RAG 맥락 챗봇 (RAG Chat Interface)
* **대화창 레이아웃**: ChatGPT의 둥근 말풍선 대신 반듯한 파스텔톤 사각형 카드로 구성.
  * **유저 질문**: 오른쪽 정렬, 연한 파스텔 피치 배경 (`#FAD0C4`).
  * **로그몬 답변**: 왼쪽 정렬, 연한 파스텔 세이지 그린 배경 (`#A3C1AD`).
* **고정형 입력창**: 화면 맨 하단에 엠보싱 처리가 되어 가라앉은 텍스트 입력 바(`st.chat_input`) 배치.
