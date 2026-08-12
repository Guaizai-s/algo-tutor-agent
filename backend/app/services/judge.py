"""判题沙箱 service (Task 8 判题系统)。

核心职责：
- 在 Docker 容器中执行用户代码
- 限制 CPU、内存、输出大小
- 对比输出与预期答案
- 返回 verdict: AC / WA / TLE / RE / CE

依赖：
- docker Python SDK (pip install docker)
- SANDBOX_IMAGE 需要在 Docker 中预先构建
"""

from __future__ import annotations

import io
import logging
import shlex
import tarfile
import tempfile
import time
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from app.core.config import settings

logger = logging.getLogger(__name__)


class Verdict(StrEnum):
    """判题结果。"""

    AC = "AC"  # Accepted
    WA = "WA"  # Wrong Answer
    TLE = "TLE"  # Time Limit Exceeded
    RE = "RE"  # Runtime Error
    CE = "CE"  # Compilation Error
    ERR = "ERR"  # System Error


@dataclass
class JudgeResult:
    """判题结果。"""

    verdict: Verdict
    time_ms: int = 0
    memory_kb: int = 0
    stdout: str = ""
    stderr: str = ""
    message: str = ""


# 语言 → 执行配置
LANGUAGE_CONFIG: dict[str, dict] = {
    "cpp": {
        "compile_cmd": ["g++", "-std=c++17", "-O2", "-Wall", "main.cpp", "-o", "main"],
        "run_cmd": ["./main"],
        "source_file": "main.cpp",
        "compile_timeout_ms": 10000,
    },
    "python": {
        "compile_cmd": None,
        "run_cmd": ["python3", "main.py"],
        "source_file": "main.py",
        "compile_timeout_ms": 0,
    },
    "java": {
        "compile_cmd": ["javac", "Main.java"],
        "run_cmd": ["java", "-Xmx256m", "Main"],
        "source_file": "Main.java",
        "compile_timeout_ms": 10000,
    },
}


async def judge(
    source_code: str,
    language: str,
    test_input: str,
    expected_output: str,
    *,
    timeout_ms: int = 3000,
    memory_mb: int = 256,
) -> JudgeResult:
    """在 Docker 沙箱中执行代码并判题。

    Args:
        source_code: 源代码
        language: 语言 (cpp / python / java)
        test_input: 测试输入
        expected_output: 预期输出
        timeout_ms: 时间限制 (ms)
        memory_mb: 内存限制 (MB)

    Returns:
        JudgeResult: 判题结果
    """
    # 参数校验
    config = LANGUAGE_CONFIG.get(language)
    if config is None:
        return JudgeResult(verdict=Verdict.ERR, message=f"不支持的语言: {language}")

    timeout_ms = min(timeout_ms, settings.SANDBOX_MAX_TIMEOUT_MS)
    memory_mb = min(memory_mb, settings.SANDBOX_MAX_MEMORY_MB)

    # 创建临时目录
    with tempfile.TemporaryDirectory(prefix="algo_judge_") as tmpdir:
        workdir = Path(tmpdir)

        # 写入源代码
        source_path = workdir / config["source_file"]
        source_path.write_text(source_code, encoding="utf-8")

        # 编译 + 运行在同一个容器内完成（编译产物需在同一容器中持久可见）
        stdin_data = test_input or ""
        run_result = await _judge_in_container(
            workdir=str(workdir),
            config=config,
            timeout_ms=timeout_ms,
            memory_mb=memory_mb,
            stdin_data=stdin_data,
        )

        if run_result.verdict != Verdict.AC:
            return run_result

        # 对比输出
        actual = _normalize_output(run_result.stdout)
        expected = _normalize_output(expected_output)
        if actual == expected:
            return JudgeResult(
                verdict=Verdict.AC,
                time_ms=run_result.time_ms,
                memory_kb=run_result.memory_kb,
                stdout=run_result.stdout,
            )
        else:
            return JudgeResult(
                verdict=Verdict.WA,
                time_ms=run_result.time_ms,
                memory_kb=run_result.memory_kb,
                stdout=run_result.stdout,
                message=f"答案错误: expected={expected[:100]}, got={actual[:100]}",
            )


def _build_tar(workdir: Path, extra_files: dict[str, str] | None = None) -> bytes:
    """把工作目录文件打成 tar 流，供 put_archive 注入沙箱容器。

    文件所有权固定为沙箱用户 (uid=1000)，保证容器内非 root 用户可读写。
    """
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        for f in workdir.iterdir():
            if not f.is_file():
                continue
            info = tar.gettarinfo(str(f), arcname=f.name)
            info.uid = 1000
            info.gid = 1000
            info.mtime = int(time.time())
            with f.open("rb") as fh:
                tar.addfile(info, fh)
        for name, content in (extra_files or {}).items():
            data = content.encode("utf-8")
            info = tarfile.TarInfo(name=name)
            info.size = len(data)
            info.mtime = int(time.time())
            info.uid = 1000
            info.gid = 1000
            info.mode = 0o644
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def _create_judge_container(client, memory_mb: int):
    """创建常驻判题容器（匿名卷挂载 /sandbox，根文件系统只读）。

    docker-py 的 Container.run(volumes=...) 仅支持 bind mount，
    而容器内临时路径无法被宿主机 daemon 解析，故用低层 API 建匿名卷。
    """
    host_config = client.api.create_host_config(
        network_mode="none" if settings.SANDBOX_NETWORK_DISABLED else "default",
        mem_limit=f"{memory_mb}m",
        memswap_limit=f"{memory_mb}m",
        cpu_period=100000,
        cpu_quota=int(settings.SANDBOX_CPU_LIMIT * 100000),
        pids_limit=settings.SANDBOX_PIDS_LIMIT,
        read_only=True,
    )
    resp = client.api.create_container(
        image=settings.SANDBOX_IMAGE,
        command=["sh", "-c", "tail -f /dev/null"],
        working_dir="/sandbox",
        user=settings.SANDBOX_USER,
        volumes=["/sandbox"],  # 匿名卷：readonly 根文件系统下 /sandbox 仍可写
        host_config=host_config,
    )
    container = client.containers.get(resp["Id"])
    container.start()
    return container


async def _judge_in_container(
    workdir: str,
    config: dict,
    timeout_ms: int,
    memory_mb: int,
    stdin_data: str,
) -> JudgeResult:
    """在单个沙箱容器中完成「注入源码 → 编译(如需) → 运行」，返回执行 verdict。

    编译产物必须与运行在同一容器中才能持久可见，因此编译和运行
    合并为一次容器生命周期。TLE 由容器内的 GNU timeout 保证（退出码 124）。
    """
    import docker

    try:
        client = docker.from_env()
    except docker.errors.DockerException as exc:
        logger.error("Docker client failed: %s", exc)
        return JudgeResult(verdict=Verdict.ERR, message=f"Docker 环境不可用: {exc}")

    try:
        container = _create_judge_container(client, memory_mb)
    except docker.errors.ImageNotFound:
        return JudgeResult(
            verdict=Verdict.ERR,
            message=f"沙箱镜像 {settings.SANDBOX_IMAGE} 未找到，请先执行 docker build -t algo-sandbox sandbox/",
        )
    except docker.errors.APIError as exc:
        return JudgeResult(verdict=Verdict.ERR, message=f"Docker API 错误: {exc}")

    try:
        # 注入源码 + 输入文件（put_archive 由 daemon 直接写入容器，
        # 规避 bind-mount 对容器内路径无法被宿主解析的限制）
        extra = {"input.txt": stdin_data} if stdin_data else None
        container.put_archive("/sandbox", _build_tar(Path(workdir), extra))

        if config["compile_cmd"] is not None:
            compile_result = await _exec_in_container(
                container,
                workdir,
                config["compile_cmd"],
                config["compile_timeout_ms"],
                "",
            )
            if compile_result.verdict != Verdict.AC:
                return JudgeResult(
                    verdict=Verdict.CE,
                    stderr=compile_result.stderr,
                    message=f"编译错误: {compile_result.stderr[:200]}",
                )

        return await _exec_in_container(
            container,
            workdir,
            config["run_cmd"],
            timeout_ms,
            stdin_data,
        )
    except Exception as exc:
        logger.error("Judge container exec failed: %s", exc)
        return JudgeResult(verdict=Verdict.ERR, message=f"执行异常: {exc}")
    finally:
        try:
            container.remove(force=True)
        except Exception as exc:
            logger.warning("Failed to remove judge container: %s", exc)


async def _exec_in_container(
    container,
    workdir: str,
    cmd: list[str],
    timeout_ms: int,
    stdin_data: str,
) -> JudgeResult:
    """在容器中执行一条命令（timeout 包装 + 输入文件重定向 + 输出采集）。"""
    extra = {"input.txt": stdin_data} if stdin_data else None
    container.put_archive("/sandbox", _build_tar(Path(workdir), extra))

    timeout_sec = max(1, timeout_ms // 1000)
    shell_cmd = f"timeout {timeout_sec}s " + " ".join(shlex.quote(c) for c in cmd)
    if stdin_data:
        shell_cmd += " < input.txt"
    exec_result = container.exec_run(
        ["sh", "-c", shell_cmd],
        demux=True,
        workdir="/sandbox",
    )

    exit_code = exec_result.exit_code
    if isinstance(exec_result.output, tuple):
        out, err = exec_result.output
    else:
        out, err = exec_result.output, b""
    stdout = (out or b"").decode("utf-8", errors="replace")
    stderr = (err or b"").decode("utf-8", errors="replace")

    max_bytes = settings.SANDBOX_MAX_OUTPUT_BYTES
    stdout = stdout[:max_bytes]
    stderr = stderr[:max_bytes]

    if exit_code == 0:
        return JudgeResult(
            verdict=Verdict.AC,
            stdout=stdout.strip(),
            stderr=stderr.strip(),
        )
    elif exit_code == 124:
        # timeout 命令在超限时杀死子进程并返回 124
        return JudgeResult(
            verdict=Verdict.TLE,
            message="时间超限",
        )
    elif exit_code == 137:
        # SIGKILL (内存超限)
        return JudgeResult(
            verdict=Verdict.RE,
            stderr="Memory Limit Exceeded",
            message="内存超限",
        )
    else:
        return JudgeResult(
            verdict=Verdict.RE,
            stderr=stderr.strip(),
            message=f"Runtime Error (exit code {exit_code})",
        )


def _normalize_output(text: str) -> str:
    """标准化输出用于对比：去除首尾空白，统一换行符。"""
    if not text:
        return ""
    return text.strip().replace("\r\n", "\n").replace("\r", "\n")
