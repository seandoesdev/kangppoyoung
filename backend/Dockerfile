# 빌드 컨텍스트 = 저장소 루트 (docker-compose 의 backend.build.context: .).
# 토폴로지 A(설계 §16.6): JRE 런타임에 Python+tesseract+pipeline 패키지를 함께 실어
# Spring 이 동일 컨테이너에서 ProcessBuilder 로 `python -m pipeline` 을 호출한다.

# --- build stage (Java 21 + Gradle wrapper) ---
FROM eclipse-temurin:21-jdk AS build
WORKDIR /app
# 컨텍스트가 루트이므로 backend 하위만 복사(frontend/pipeline/.git 등 제외).
COPY backend/ .
# gradlew 가 호스트(Windows)에서 CRLF 로 체크아웃되면 리눅스에서 셔뱅이 깨지므로 CR 제거.
RUN sed -i 's/\r$//' gradlew && chmod +x gradlew && ./gradlew clean bootJar --no-daemon -x test

# --- runtime stage (JRE + Python pipeline) ---
FROM eclipse-temurin:21-jre
WORKDIR /app

# PDF→RAG 파이프라인용 Python 런타임 + OCR 바이너리(설계 §18). pip 설치 불가한 tesseract 는 apt.
RUN apt-get update \
 && apt-get install -y --no-install-recommends python3 python3-venv tesseract-ocr tesseract-ocr-kor \
 && rm -rf /var/lib/apt/lists/*

# 격리 venv(데비안 PEP668 externally-managed 회피). 의존성 레이어 분리로 캐시 활용.
COPY pipeline/requirements.txt /tmp/pipeline-requirements.txt
RUN python3 -m venv /opt/pipeline-venv \
 && /opt/pipeline-venv/bin/pip install --no-cache-dir -U pip \
 && /opt/pipeline-venv/bin/pip install --no-cache-dir -r /tmp/pipeline-requirements.txt

# 파이프라인 패키지(Spring ProcessBuilder 가 WORKDIR /app 에서 `python -m pipeline` 로 호출).
COPY pipeline/ /app/pipeline/

# 한글 인코딩 고정(§16.4) + Spring 이 사용할 인터프리터 절대경로 힌트.
ENV PYTHONUTF8=1 \
    PYTHONIOENCODING=utf-8 \
    PIPELINE_PYTHON=/opt/pipeline-venv/bin/python

COPY --from=build /app/build/libs/*.jar app.jar
EXPOSE 8080
# 시크릿은 ENV/ARG 로 굽지 않는다. 런타임에 env_file 로 주입한다.
ENTRYPOINT ["java", "-jar", "app.jar"]
