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

import logging
import tempfile
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

        # 编译（如果需要）
        if config["compile_cmd"] is not None:
            compile_result = await _run_in_docker(
                workdir=str(workdir),
                cmd=config["compile_cmd"],
                timeout_ms=config["compile_timeout_ms"],
                memory_mb=512,
                stdin_data="",
            )
            if compile_result.verdict != Verdict.AC:
                return JudgeResult(
                    verdict=Verdict.CE,
                    stderr=compile_result.stderr,
                    message=f"编译错误: {compile_result.stderr[:200]}",
                )

        # 执行
        stdin_data = test_input or ""
        run_result = await _run_in_docker(
            workdir=str(workdir),
            cmd=config["run_cmd"],
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


async def _run_in_docker(
    workdir: str,
    cmd: list[str],
    timeout_ms: int,
    memory_mb: int,
    stdin_data: str,
) -> JudgeResult:
    """在 Docker 容器中执行命令。

    Returns:
        JudgeResult with AC if execution successful, TLE/RE/ERR otherwise.
    """
    import docker

    try:
        client = docker.from_env()
    except docker.errors.DockerException as exc:
        logger.error("Docker client failed: %s", exc)
        return JudgeResult(verdict=Verdict.ERR, message=f"Docker 环境不可用: {exc}")

    try:
        container = client.containers.run(
            image=settings.SANDBOX_IMAGE,
            command=cmd,
            working_dir="/sandbox",
            volumes={workdir: {"bind": "/sandbox", "mode": "rw"}},
            stdin_open=True,
            network_disabled=settings.SANDBOX_NETWORK_DISABLED,
            mem_limit=f"{memory_mb}m",
            memswap_limit=f"{memory_mb}m",
            cpu_period=100000,
            cpu_quota=int(settings.SANDBOX_CPU_LIMIT * 100000),
            pids_limit=settings.SANDBOX_PIDS_LIMIT,
            read_only=True,
            user=settings.SANDBOX_USER,
            detach=True,
        )

        try:
            # 等待容器完成或超时
            exit_info = container.wait(timeout=timeout_ms / 1000 + 5)
            exit_code = exit_info.get("StatusCode", -1)

            # 收集输出
            stdout = container.logs(stdout=True, stderr=False).decode("utf-8", errors="replace")
            stderr = container.logs(stdout=False, stderr=True).decode("utf-8", errors="replace")

            # 截断输出
            max_bytes = settings.SANDBOX_MAX_OUTPUT_BYTES
            stdout = stdout[:max_bytes]
            stderr = stderr[:max_bytes]

            if exit_code == 0:
                return JudgeResult(
                    verdict=Verdict.AC,
                    stdout=stdout.strip(),
                    stderr=stderr.strip(),
                )
            elif exit_code == 137:
                # SIGKILL (内存超限)
                return JudgeResult(
                    verdict=Verdict.RE,
                    stderr="Memory Limit Exceeded",
                    message="内存超限",
                )
            elif exit_code == 124:
                return JudgeResult(
                    verdict=Verdict.TLE,
                    message="时间超限",
                )
            else:
                return JudgeResult(
                    verdict=Verdict.RE,
                    stderr=stderr.strip(),
                    message=f"Runtime Error (exit code {exit_code})",
                )

        except Exception as exc:
            # 超时或容器异常
            if "timeout" in str(exc).lower() or "timed out" in str(exc).lower():
                return JudgeResult(verdict=Verdict.TLE, message="时间超限")
            return JudgeResult(verdict=Verdict.ERR, message=f"执行异常: {exc}")
        finally:
            try:
                container.remove(force=True)
            except Exception as exc:
                logger.warning("Failed to remove judge container: %s", exc)

    except docker.errors.ImageNotFound:
        return JudgeResult(
            verdict=Verdict.ERR,
            message=f"沙箱镜像 {settings.SANDBOX_IMAGE} 未找到，请先执行 docker build -t algo-sandbox sandbox/",
        )
    except docker.errors.APIError as exc:
        return JudgeResult(verdict=Verdict.ERR, message=f"Docker API 错误: {exc}")


def _normalize_output(text: str) -> str:
    """标准化输出用于对比：去除首尾空白，统一换行符。"""
    if not text:
        return ""
    return text.strip().replace("\r\n", "\n").replace("\r", "\n")
