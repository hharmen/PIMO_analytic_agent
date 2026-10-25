"""Runner: запускает TLC (Java) отдельным процессом и возвращает сырой вывод.

Каждый запуск идёт во временной папке: туда кладём Model.tla и Model.cfg,
там же TLC создаёт свои служебные файлы. После запуска папка удаляется.
Отдельный процесс нужен, чтобы по таймауту его можно было принудительно убить.
"""

import os
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

CHECKER_DIR = Path(__file__).resolve().parent.parent

TLA2TOOLS_JAR = os.environ.get("TLA2TOOLS_JAR", str(CHECKER_DIR / "tools" / "tla2tools.jar"))
JAVA_BIN = os.environ.get("JAVA_BIN", "java")
JAVA_OPTS = os.environ.get("JAVA_OPTS", "-XX:+UseParallelGC -Xmx1g").split()
KEEP_RUNS = os.environ.get("CHECKER_KEEP_RUNS") == "1"


@dataclass
class RunResult:
    output: str 
    exit_code: int | None  
    timed_out: bool 
    seconds: float  
    error: str | None = None  


def run_tlc(tla_text: str, cfg_text: str, timeout_seconds: int = 30) -> RunResult:
    """Записывает файлы во временную папку и запускает в ней TLC."""
    if KEEP_RUNS:
        runs_dir = CHECKER_DIR / "runs"
        runs_dir.mkdir(exist_ok=True)
        workdir = tempfile.mkdtemp(prefix="run_", dir=runs_dir)
        return _run_in_dir(Path(workdir), tla_text, cfg_text, timeout_seconds)

    with tempfile.TemporaryDirectory(prefix="tlc_") as workdir:
        return _run_in_dir(Path(workdir), tla_text, cfg_text, timeout_seconds)


def _run_in_dir(workdir: Path, tla_text: str, cfg_text: str, timeout_seconds: int) -> RunResult:
    (workdir / "Model.tla").write_text(tla_text, encoding="utf-8")
    (workdir / "Model.cfg").write_text(cfg_text, encoding="utf-8")

    if not Path(TLA2TOOLS_JAR).is_file():
        return RunResult("", None, False, 0.0, error=f"Не найден tla2tools.jar: {TLA2TOOLS_JAR}")

    command = [
        JAVA_BIN,
        *JAVA_OPTS,
        f"-Djava.io.tmpdir={workdir}",
        "-cp", TLA2TOOLS_JAR,
        "tlc2.TLC",
        "-workers", "1",
        "-config", "Model.cfg",
        "-metadir", str(workdir / "states"), 
        "Model.tla",
    ]

    start = time.monotonic()
    try:
        completed = subprocess.run(
            command,
            cwd=workdir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:

        return RunResult(_to_text(exc.stdout), None, True, _since(start))
    except FileNotFoundError:
        return RunResult("", None, False, _since(start), error=f"Не найдена Java (команда '{JAVA_BIN}')")

    return RunResult(completed.stdout, completed.returncode, False, _since(start))


def _since(start: float) -> float:
    return round(time.monotonic() - start, 2)


def _to_text(data: bytes | str | None) -> str:
    """При таймауте Python может отдать вывод байтами, а может строкой."""
    if data is None:
        return ""
    if isinstance(data, bytes):
        return data.decode("utf-8", errors="replace")
    return data
