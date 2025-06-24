# --- 阶段 1: 构建阶段 ---
    FROM python:3.11-slim AS builder

    WORKDIR /app
    
    # 直接复制当前目录下的 requirements.txt
    COPY requirements.txt .
    RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir -r requirements.txt
    
    
    # --- 阶段 2: 最终运行阶段 ---
    FROM python:3.11-slim
    
    WORKDIR /app
    
    COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
    COPY --from=builder /usr/local/bin /usr/local/bin
    
    # 将当前目录（.）的所有内容复制到镜像的 /app 目录下
    COPY . .
    
    # 暴露主应用的端口
    EXPOSE 8000
    
    # 启动命令
    CMD ["uvicorn", "menu_planner.main:app", "--host", "0.0.0.0", "--port", "8000"]