# Stage 1: builder — install all dependencies into /install
FROM python:3.11 AS builder

WORKDIR /build

COPY requirements.txt .

# Install fastapi + uvicorn + redis (needed for web dashboard and Redis support)
# alongside the project requirements, all into a prefix we can copy cleanly
RUN pip install --no-cache-dir --prefix=/install \
        fastapi>=0.110.0 \
        uvicorn>=0.29.0 \
        redis>=5.0.0 \
        -r requirements.txt

# Stage 2: runner — slim image, copy only what is needed
FROM python:3.11-slim

# Prevents Python from writing .pyc files and enables unbuffered stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application source
COPY . .

EXPOSE 8765

CMD ["uvicorn", "ai_team.web.app:create_app", "--factory", \
     "--host", "0.0.0.0", "--port", "8765", "--log-level", "info"]
