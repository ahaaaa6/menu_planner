# --- 阶段 1: 构建阶段 ---
FROM dockerproxy.com/library/python:3.11-slim AS builder

WORKDIR /app

# 复制依赖文件
COPY requirements.txt .

# 使用中国镜像源安装依赖
RUN pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple/ -r requirements.txt

# --- 阶段 2: 最终运行阶段 ---
FROM dockerproxy.com/library/python:3.11-slim

WORKDIR /app

# 从构建阶段复制安装的包
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin/ /usr/local/bin/

# 复制应用代码
COPY . .

# 暴露端口
EXPOSE 8000

# 启动命令
CMD ["uvicorn", "menu_planner.main:app", "--host", "0.0.0.0", "--port", "8000"]