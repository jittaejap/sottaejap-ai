# 소때잡 AI 서버 — Python 3.12 (E-26). requirements.lock으로 버전을 고정한다 (07 §11).
FROM python:3.12-slim

# Windows·macOS 혼용 환경과 같은 인코딩·시간대를 컨테이너에서도 강제한다 (07 §5-3 · 05 §0).
ENV PYTHONUTF8=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=Asia/Seoul

WORKDIR /app

# 소스보다 먼저 복사해서, 소스만 바뀔 때는 의존성 설치 레이어를 재사용한다.
COPY requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock

COPY app ./app
COPY scripts ./scripts

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
