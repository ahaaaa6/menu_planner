# 使用官方的 Python 镜像作为基础
FROM python:3.10-slim

# 设置工作目录
WORKDIR /app

# 新增：将工作目录添加到 Python 的模块搜索路径中
ENV PYTHONPATH /app

# 复制依赖文件并安装
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制所有项目代码到工作目录
COPY . .