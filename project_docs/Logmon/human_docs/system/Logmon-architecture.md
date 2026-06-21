# 🏛️ 로그몬 (LogMon) 시스템 아키텍처 명세서 (Logmon-architecture.md)

이 문서는 N95 저전력 홈서버 환경에 최적화된 로그몬(LogMon) 시스템의 인프라 아키텍처 및 Docker 배포 설계를 다룹니다.

---

## 🎯 1. 아키텍처 설계 목적

1. **N95 저전력 자원 최적화**: 4코어 CPU / RAM 16GB / GPU가 없는 환경에서 AI 로컬 모델 구동 시 CPU 자원 고갈을 방지합니다.
2. **독립 컴포넌트 격리**: UI, FastAPI 백엔드, Ollama 컨테이너를 완벽 분리하여 상호 간섭을 최소화합니다.
3. **데이터 흐름의 단일 통로화**: Streamlit UI가 데이터베이스에 직접 접근하지 않고, 모든 통신을 FastAPI REST API로 일원화하여 SQLite Lock 현상 및 동시 쓰기 문제를 방지합니다.
4. **보안 필터 적용**: 외부 리버스 프록시(Nginx)를 통해 포트 노출을 최소화하고, 모든 에이전트 데이터 수집 요청 시 API Key를 필수로 검증합니다.

---

## 📦 2. 컨테이너 구성 및 네트워크 설계

```
                                  [ 로컬 개발 PC 에이전트 ]
                                             │ (5분 주기 API + API Key 헤더)
                                             ▼
[ 외부 브라우저 ] ──> [ Nginx 리버스 프록시 ] ─────────────────────────┐
                             │ (Path 기반 라우팅)                       │
                             ▼                                         ▼
                     [ logmon-ui (Streamlit) ] ──> [ logmon-backend (FastAPI) ]
                                                            │
                                                            ├──> [ SQLite / Chroma DB ]
                                                            ▼
                                                   [ logmon-ollama (Gemma2) ]
```

### 1) logmon-ui
* **역할**: Streamlit 기반 대시보드 시각화 및 RAG 대화형 웹 인터페이스 제공.
* **포트**: 호스트 `3007` (컨테이너 내부 `8501`).
* **네트워크**: `logmon-network` 내부에서 `logmon-backend`와 통신하며, 호스트 포트는 Nginx 프록시 패스를 거쳐 외부에 노출됩니다.

### 2) logmon-backend
* **역할**: 에이전트 수집 API 핸들링, PyInstaller 바이너리 배포용 스태틱 라우팅, SQLite 및 Chroma DB 관리, Ollama 제어.
* **포트**: 호스트 `3008` (컨테이너 내부 `8000`).
* **네트워크**: SQLite, Chroma DB 볼륨을 마운트하고, 동일 네트워크 내의 `logmon-ollama:11434` 엔드포인트를 호출합니다.

### 3) logmon-ollama
* **역할**: Gemma 2 2B 모델 및 bge-small-en-v1.5 임베딩 모델을 로컬로 로드하여 임베딩 및 LLM 챗 추론 제공.
* **포트**: 외부 개방 없음 (컨테이너 내부 `11434` 전용).
* **네트워크**: 보안 유지를 위해 호스트 포트 바인딩을 완전 제거하고 백엔드 컨테이너만 접근을 허용합니다.

---

## 💾 3. 데이터 영속성 및 볼륨 마운트 구조

서버 재부팅 또는 컨테이너 리프레시 시 데이터가 유실되지 않도록 홈서버 호스트의 고정 경로 `/home/ksh/logmon/data` 폴더를 완벽히 바인딩합니다.

| 호스트 경로 | 컨테이너 내부 경로 | 매핑 컨테이너 | 설명 |
| :--- | :--- | :--- | :--- |
| `/home/ksh/logmon/data/db` | `/app/data` | `logmon-backend` | SQLite 3 (`logmon.db`) DB 파일 저장 폴더 |
| `/home/ksh/logmon/data/chroma` | `/app/chroma_data` | `logmon-backend` | Chroma DB 벡터 데이터 영속화 폴더 |
| `/home/ksh/logmon/data/ollama` | `/root/.ollama` | `logmon-ollama` | Gemma2 및 bge 임베딩 모델 가중치 파일 보존 폴더 |

---

## 🎛️ 4. Nginx 역방향 프록시 설정 (Reverse Proxy)

Nginx 설정 파일을 통해 서브패스 기반 라우팅을 수행하여 깔끔한 포트 독립형 접근을 지원합니다.

```nginx
# /etc/nginx/sites-available/logmon
server {
    listen 80;
    server_name localhost;

    # 1) Streamlit 프론트엔드 라우팅
    location /logmon/ {
        proxy_pass http://127.0.0.1:3007/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # 2) FastAPI 백엔드 API & 정적 파일 라우팅
    location /api/logmon/ {
        proxy_pass http://127.0.0.1:3008/api/logmon/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

---

## ⚙️ 5. 시스템 자원 방어 전략

1. **CPU Limit 설정**: N95 CPU(4코어)의 독점을 막기 위해 docker-compose의 `deploy.resources.limits.cpus`를 `3.0`으로 제한하여 1개 코어의 여유를 상시 확보합니다.
2. **Ollama 메모리 및 대기 전략**: GPU가 없으므로 동시 요청 시 큐에 대기하도록 Ollama 스레드 제한을 두고 컨텍스트 윈도우 부하를 제어합니다.
