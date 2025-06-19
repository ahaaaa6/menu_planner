# Dockerfile

# --- 阶段 1: 构建一个包含所有依赖的 "builder" 环境 ---
# 使用官方的Python 3.11 slim版本作为基础
FROM python:3.11-slim as builder

# 设置工作目录
WORKDIR /app

# 更新pip并安装项目依赖
# 先只复制requirements.txt，这样可以利用Docker的层缓存机制
# 只有当requirements.txt变化时，才会重新执行pip install，大大加快后续构建速度
COPY menu_planner/requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir -r requirements.txt


# --- 阶段 2: 构建最终的、轻量级的生产环境镜像 ---
FROM python:3.11-slim

# 设置工作目录
WORKDIR /app

# 从 "builder" 阶段复制已经安装好的Python依赖库
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages

# 复制您项目的所有代码到工作目录中
COPY ./menu_planner /app/menu_planner

# 暴露端口，声明此容器在8000端口上提供服务
EXPOSE 8000

# 设置默认的启动命令
# 当容器启动时，会默认执行这个命令来启动主应用
CMD ["uvicorn", "menu_planner.main:app", "--host", "0.0.0.0", "--port", "8000"]