# 拾物 Backend — Docker 镜像
FROM python:3.11-slim

WORKDIR /app

# 系统依赖（curl 用于 healthcheck）
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Python 依赖（阿里云镜像加速）
COPY requirements.txt .
RUN pip config set global.index-url https://mirrors.aliyun.com/pypi/simple/ && \
    pip install --no-cache-dir -r requirements.txt

# 应用代码
COPY . .

# 加速 HF 下载（使用 Rust 实现的 HF Transfer，断点续传）
# 模型优先从挂载卷 data/models/ 加载，其次 HF cache，最后才下载
ENV HF_HUB_ENABLE_HF_TRANSFER=1

# 预下载 Embedding + Reranker 模型到镜像（首次启动跳过 ~3.5GB 下载）
ARG HF_ENDPOINT=https://hf-mirror.com
ENV HF_ENDPOINT=${HF_ENDPOINT}
RUN python -c "from huggingface_hub import snapshot_download; snapshot_download('BAAI/bge-large-zh-v1.5')" && \
    python -c "from huggingface_hub import snapshot_download; snapshot_download('BAAI/bge-reranker-v2-m3')"

EXPOSE 8080
ENV APP_PORT=8080

HEALTHCHECK --interval=10s --timeout=3s --retries=3 \
    CMD curl -f http://localhost:${APP_PORT}/health || exit 1

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${APP_PORT}"]
