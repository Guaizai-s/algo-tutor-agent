# 沙箱镜像：用于 execute_code 工具隔离执行用户代码
# 该镜像自身不挂载 docker.sock；后端容器通过 docker SDK spawn 兄弟容器。
FROM python:3.12-slim

# 安装 C++ 与 Java 工具链
# python:3.12-slim 基于 Debian Trixie，源中默认 JDK 为 openjdk-21
RUN apt-get -o Acquire::Retries=5 update && \
    apt-get -o Acquire::Retries=5 install -y --no-install-recommends \
    gcc g++ openjdk-21-jdk-headless ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# 非 root 用户
RUN useradd -m -u 1000 sandbox && \
    mkdir -p /sandbox && chown sandbox:sandbox /sandbox

WORKDIR /sandbox
USER sandbox

# 无 ENTRYPOINT —— 由后端 docker SDK 通过 command 启动
