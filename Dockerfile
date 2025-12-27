# --- 阶段 1：构建阶段 ---
FROM python:3.11-slim AS builder

WORKDIR /build

# 安装构建依赖（如果某些 Python 包需要编译，可以在这里安装 gcc 等）
# 这里只安装基本的编译工具以防万一
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
# 将依赖安装到本地目录以供拷贝
RUN pip install --upgrade pip && \
    pip install --no-cache-dir --prefix=/install -r requirements.txt

# --- 阶段 2：运行阶段 ---
FROM python:3.11-slim

WORKDIR /app

# 设置环境变量
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

# 从构建阶段拷贝已安装的包
COPY --from=builder /install /usr/local

# 安装运行时依赖：ffmpeg (视频处理) 和 curl (健康检查)
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg curl && \
    rm -rf /var/lib/apt/lists/*

# 拷贝源代码
COPY . .

# 健康检查
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -f http://localhost:8000/ || exit 1

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]