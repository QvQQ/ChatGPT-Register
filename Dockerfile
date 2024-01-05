
# 使用较新的Python基础镜像
FROM python:3.11-slim

# 作者信息
LABEL author="QvQQ"
LABEL github="https://github.com/QvQQ"
LABEL version="1.0"

# 定义一个用于接收构建平台的 ARG
ARG TARGETPLATFORM

# 设置工作目录
WORKDIR /app

# 检查目标平台是否为 amd64，如果不是，则退出
# 创建并写入新的 sources.list，安装 Chrome 浏览器
RUN if [ "${TARGETPLATFORM}" != "linux/amd64" ]; then \
        echo "此 Dockerfile 仅支持 amd64 架构的构建。(Chrome 未提供 arm64 版本)"; \
        exit 1; \
    fi \
    && echo "\
deb https://mirrors.tuna.tsinghua.edu.cn/debian/ bookworm main contrib\n\
deb https://mirrors.tuna.tsinghua.edu.cn/debian/ bookworm-updates main contrib\n\
deb https://mirrors.tuna.tsinghua.edu.cn/debian/ bookworm-backports main contrib\n\
deb https://security.debian.org/debian-security bookworm-security main contrib\n" > /etc/apt/sources.list \
    && apt-get update \
    && apt-get install -y wget gnupg \
    && wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /etc/apt/trusted.gpg.d/google.gpg \
    && echo "deb [arch={${TARGETPLATFORM#*/}}] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update \
    && apt-get install -y chromium \
    || (wget "https://dl.google.com/linux/direct/google-chrome-stable_current_${TARGETPLATFORM#*/}.deb" \
    && dpkg -i "google-chrome-stable_current_${TARGETPLATFORM#*/}.deb" \
    && rm "google-chrome-stable_current_${TARGETPLATFORM#*/}.deb") \
    && rm -rf /var/lib/apt/lists/*

# 复制程序文件到工作目录
COPY ./main.py ./database.py ./models.py /app/

# 安装Python依赖
RUN pip install --no-cache-dir undetected_chromedriver requests rich sqlalchemy petname retry pyyaml sshtunnel

# 运行 undetected_chromedriver 的 Patcher 自动下载 Chromedriver
RUN python -c "from undetected_chromedriver import Patcher; import logging; logging.basicConfig(level='DEBUG'); Patcher().auto()"

# 运行 Python 脚本
CMD ["python", "main.py"]

