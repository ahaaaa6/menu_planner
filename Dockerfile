# 使用官方的 Python 镜像作为基础
FROM python:3.10-slim

# 将工作目录设置为 /app
WORKDIR /app

# 先复制依赖文件并安装，这样可以利用Docker的层缓存，后续代码修改时无需重复安装
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 关键修改：将您本地的所有代码复制到容器内的 /app/menu_planner 这个子目录中
COPY . ./menu_planner/