# 推荐使用 python:3.11-slim，在 Apple Silicon 上性能更佳且兼容性好
FROM python:3.11-slim

WORKDIR /app

# 防止 Python 生成 .pyc 文件和缓冲输出（利于 Docker 日志查看）
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY requirements.txt .
# --no-cache-dir 减小镜像体积
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# 确保数据目录存在
RUN mkdir -p /app/data

# 使用 CMD 启动
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]