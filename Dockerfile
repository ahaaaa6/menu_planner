# 构建阶段 
FROM dockerproxy.com/library/python:3.11-slim AS builder

# 设置工作目录
WORKDIR /app

# 关键修改 1: 先只复制依赖文件到工作目录 /app
COPY requirements.txt .
# 安装依赖
RUN pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt

# 关键修改 2: 将所有代码复制到 /app/menu_planner/ 子目录中
COPY . /app/menu_planner/

# 暴露端口
EXPOSE 8000

# 关键修改 3: 使用原始的、需要 menu_planner 路径的启动命令
CMD ["uvicorn", "menu_planner.main:app", "--host", "0.0.0.0", "--port", "8000"]