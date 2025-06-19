# 使用官方的 Python 镜像作为基础
FROM python:3.10-slim

# 设置工作目录为 /app
WORKDIR /app

# 将 requirements.txt 预先复制进来并安装，以利用Docker的层缓存机制
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 将您本地的所有代码复制到容器内 /app/menu_planner 这个子目录中
# 这一步是创建包结构的关键
COPY . ./menu_planner/