#!/usr/bin/env python3
"""FacadeGPT 一键健康检查脚本。

用法：
    python health_check.py

检查项：
- Python 后端依赖是否安装
- Node 前端依赖是否安装
- 后端能否正常启动
- 前端能否成功构建
- 核心 API 是否可用
- 数据库是否可读写
"""

import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
PORT = 8765  # 检查专用端口，避免和日常 8000 冲突
BASE_URL = f"http://127.0.0.1:{PORT}"

errors = []
warnings = []


def log(msg: str) -> None:
    print(f"[check] {msg}")


def fail(msg: str) -> None:
    errors.append(msg)
    print(f"  ✗ {msg}")


def warn(msg: str) -> None:
    warnings.append(msg)
    print(f"  ! {msg}")


def ok(msg: str) -> None:
    print(f"  ✓ {msg}")


def run(cmd, cwd=None, capture=True, timeout=60):
    kwargs = {"cwd": cwd or ROOT, "shell": os.name == "nt"}
    if capture:
        kwargs["stdout"] = subprocess.PIPE
        kwargs["stderr"] = subprocess.STDOUT
        kwargs["text"] = True
    return subprocess.run(cmd, **kwargs, timeout=timeout)


def check_backend_deps():
    log("检查后端依赖...")
    try:
        import uvicorn
        import fastapi
        import pypdf
        ok(f"uvicorn={uvicorn.__version__}, fastapi={fastapi.__version__}")
    except ImportError as e:
        fail(f"后端依赖缺失: {e}")
        return False
    return True


def check_frontend_deps():
    log("检查前端依赖...")
    if not (FRONTEND / "node_modules").exists():
        fail("frontend/node_modules 不存在，请先运行 npm install")
        return False
    ok("node_modules 已存在")
    return True


def check_frontend_build():
    log("检查前端生产构建...")
    result = run(["npm", "run", "build"], cwd=FRONTEND, timeout=120)
    if result.returncode != 0:
        fail("前端构建失败")
        if result.stdout:
            print(result.stdout[-1500:])
        return False
    ok("前端构建成功")
    return True


def start_backend():
    log("启动后端服务...")
    env = os.environ.copy()
    env["FACADEGPT_DB"] = str(BACKEND / "health_check.db")
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", str(PORT)],
        cwd=BACKEND,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=env,
    )
    # Wait for startup
    for _ in range(30):
        try:
            with urllib.request.urlopen(f"{BASE_URL}/api/health", timeout=1) as resp:
                if resp.status == 200:
                    ok(f"后端已启动 ({BASE_URL}/api/health)")
                    return proc
        except Exception:
            time.sleep(0.5)
    fail("后端启动超时")
    proc.terminate()
    return None


def check_api():
    log("检查核心 API...")
    checks = [
        ("GET", "/api/health", None, "健康检查"),
        ("POST", "/api/projects", {"name": "健康检查项目"}, "创建项目"),
    ]
    project_id = None
    for method, path, data, desc in checks:
        try:
            url = f"{BASE_URL}{path}"
            req_kwargs = {"method": method, "headers": {"Content-Type": "application/json"}}
            if data:
                req_kwargs["data"] = __import__("json").dumps(data, ensure_ascii=False).encode("utf-8")
            req = urllib.request.Request(url, **req_kwargs)
            with urllib.request.urlopen(req, timeout=10) as resp:
                body = resp.read().decode("utf-8")
                if resp.status in (200, 201):
                    ok(f"{desc} ({method} {path})")
                    if path == "/api/projects":
                        project_id = __import__("json").loads(body)["project_id"]
                else:
                    fail(f"{desc} 返回 {resp.status}")
        except Exception as e:
            fail(f"{desc} 失败: {e}")

    if project_id:
        try:
            url = f"{BASE_URL}/api/projects/{project_id}/parse-demand"
            data = __import__("json").dumps({"natural_language": "广州办公楼，西向，希望减少西晒并保持采光"}, ensure_ascii=False).encode("utf-8")
            req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=60) as resp:
                parsed = __import__("json").loads(resp.read().decode("utf-8"))
                ok(f"解析需求成功: {parsed['understanding_summary'][:40]}...")
        except Exception as e:
            fail(f"解析需求失败: {e}")

        try:
            url = f"{BASE_URL}/api/projects/{project_id}/generate-schemes"
            data = __import__("json").dumps({"num_schemes": 1, "strategies": ["balanced"]}, ensure_ascii=False).encode("utf-8")
            req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=300) as resp:
                result = __import__("json").loads(resp.read().decode("utf-8"))
                count = len(result.get("schemes", []))
                ok(f"生成方案成功，共 {count} 个")
        except Exception as e:
            fail(f"生成方案失败: {e}")


def main():
    print("=" * 60)
    print("FacadeGPT 健康检查")
    print("=" * 60)

    check_backend_deps()
    if not check_frontend_deps():
        print("\n请先安装依赖后再运行检查。")
        sys.exit(1)

    check_frontend_build()

    proc = start_backend()
    if proc:
        try:
            check_api()
        finally:
            log("关闭后端服务...")
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()

    # Clean up temp database
    db_path = BACKEND / "health_check.db"
    for ext in ["", "-wal", "-shm"]:
        p = Path(str(db_path) + ext)
        if p.exists():
            try:
                p.unlink()
            except OSError:
                pass

    print("\n" + "=" * 60)
    if errors:
        print(f"发现 {len(errors)} 个错误:")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)
    else:
        print("✓ 所有检查通过，项目可以正常运行。")
        if warnings:
            print(f"警告 ({len(warnings)}):")
            for w in warnings:
                print(f"  - {w}")


if __name__ == "__main__":
    main()
