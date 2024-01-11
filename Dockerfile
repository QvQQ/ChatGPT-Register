
# 使用 Selenium 的官方基础镜像
FROM selenium/standalone-chrome

# 作者信息
LABEL author="QvQQ"
LABEL github="https://github.com/QvQQ"
LABEL version="1.0"

# 定义一个用于接收构建平台的 ARG
ARG TARGETPLATFORM

# 设置工作目录
WORKDIR /home/seluser/

# 切换到 root
USER seluser

# 更换镜像源并安装语言包、设置 locale 为中文
RUN echo "\
deb https://mirrors.tuna.tsinghua.edu.cn/ubuntu/ jammy main restricted universe multiverse\n\
deb https://mirrors.tuna.tsinghua.edu.cn/ubuntu/ jammy-updates main restricted universe multiverse\n\
deb https://mirrors.tuna.tsinghua.edu.cn/ubuntu/ jammy-backports main restricted universe multiverse\n\
deb http://security.ubuntu.com/ubuntu/ jammy-security main restricted universe multiverse" | sudo tee /etc/apt/sources.list \
    && sudo apt-get update \
    && sudo apt-get install -y locales \
    && sudo rm -rf /var/lib/apt/lists/* \
    && sudo locale-gen zh_CN.UTF-8

RUN sudo apt update && sudo apt install -y expect

ENV LANG zh_CN.UTF-8
ENV LANGUAGE zh_CN:zh
ENV LC_ALL zh_CN.UTF-8
ENV PATH="${PATH}:/home/seluser/.local/bin"

# 复制程序文件到工作目录
COPY ./main.py ./database.py ./models.py ./configurer.py ./requirements.txt ./alembic.ini ./alembic_scripts /home/seluser/

# 安装 pip 并安装 python 依赖
RUN sudo chown -R seluser:seluser /home/seluser/.local \
    && curl https://bootstrap.pypa.io/get-pip.py -o get-pip.py \
    && python3 get-pip.py \
    && rm get-pip.py \
    && pip config set global.index-url 'https://pypi.tuna.tsinghua.edu.cn/simple' \
    && pip install --no-cache-dir -r /home/seluser/requirements.txt

# 更改 superviosr 的运行命令
RUN sudo sed -i \
    -e '\|command=bash -c "/opt/bin/start-selenium-standalone.sh;|a environment=DISPLAY=":99.0",TERM="xterm-256color"' \
    -e 's|command=bash -c "/opt/bin/start-selenium-standalone.sh;|command=bash -c "cd /home/seluser/; sudo -E unbuffer python3 main.py;|' \
    /etc/supervisor/conf.d/selenium.conf

# 运行 undetected_chromedriver 的 Patcher 自动下载 Chromedriver
RUN python3 -c "from undetected_chromedriver import Patcher; import logging; logging.basicConfig(level='DEBUG'); Patcher().auto()"

# 运行 Python 脚本
CMD ["/opt/bin/entry_point.sh"]

