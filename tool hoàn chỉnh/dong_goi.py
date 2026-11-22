#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import os
import queue
import re
import shlex
import subprocess
import sys
import threading
import time
import traceback
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, List

import tkinter as tk
from tkinter import filedialog, messagebox, ttk, scrolledtext

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

APP_TITLE = "Trình Đóng Gói Python → EXE  |  Professional Edition 2.0"
CONFIG_FILE = Path.home() / ".dong_goi_config.json"
HISTORY_FILE = Path.home() / ".dong_goi_history.json"
LOG_DIR = Path.home() / ".dong_goi_logs"
MAX_LOG_LINES_UI = 2500
MAX_HISTORY = 30

DEFAULT_CONFIG = {
    "last_py_file": "",
    "last_output_dir": "",
    "last_name": "",
    "last_icon": "",
    "onefile": True,
    "noconsole": False,
    "clean": True,
    "add_data": "",
    "hidden_import": "",
    "upx": False,
    "upx_dir": "",
    "exclude_module": "",
    "version_file": "",
    "uac_admin": False,
    "debug": False,
    "strip": False,
    "extra_args": "",
}

ADD_DATA_SEP = ";" if sys.platform == "win32" else ":"

# Preset theo framework
PRESETS = {
    "Console cơ bản": {
        "onefile": True,
        "noconsole": False,
        "hidden_import": "",
        "exclude_module": "",
        "extra_args": "",
    },
    "Tkinter GUI": {
        "onefile": True,
        "noconsole": True,
        "hidden_import": "",
        "exclude_module": "",
        "extra_args": "",
    },
    "PyQt5 / PySide2": {
        "onefile": True,
        "noconsole": True,
        "hidden_import": "PyQt5,PySide2",
        "exclude_module": "",
        "extra_args": "--collect-all PyQt5",
    },
    "Kivy": {
        "onefile": True,
        "noconsole": True,
        "hidden_import": "kivy",
        "exclude_module": "",
        "extra_args": "--collect-all kivy --collect-data kivy",
    },
    "AI / OpenCV / Torch (cơ bản)": {
        "onefile": False,          # one-dir ổn định hơn với AI
        "noconsole": False,
        "hidden_import": "cv2,torch,torchvision",
        "exclude_module": "",
        "extra_args": "--collect-all torch --collect-all cv2",
    },
}

INVALID_NAME_CHARS = r'<>:"/\|?*'


@dataclass
class BuildConfig:
    py_file: str = ""
    output_dir: str = ""
    name: str = ""
    icon: str = ""
    onefile: bool = True
    noconsole: bool = False
    clean: bool = True
    add_data: str = ""
    hidden_import: str = ""
    upx: bool = False
    upx_dir: str = ""
    exclude_module: str = ""
    version_file: str = ""
    uac_admin: bool = False
    debug: bool = False
    strip: bool = False
    extra_args: str = ""
    workpath: str = ""
    specpath: str = ""


@dataclass
class BuildEvent:
    kind: str
    message: str = ""
    level: str = "info"
    success: Optional[bool] = None
    data: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def ensure_dir(p: Path) -> Path:
    p.mkdir(parents=True, exist_ok=True)
    return p


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path: Path, data: Any) -> bool:
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def load_config() -> dict:
    data = load_json(CONFIG_FILE, {})
    merged = DEFAULT_CONFIG.copy()
    merged.update({k: v for k, v in data.items() if k in DEFAULT_CONFIG})
    return merged


def save_config(cfg: dict) -> None:
    save_json(CONFIG_FILE, cfg)


def load_history() -> List[dict]:
    return load_json(HISTORY_FILE, [])


def add_history(entry: dict) -> None:
    history = load_history()
    history.insert(0, entry)
    history = history[:MAX_HISTORY]
    save_json(HISTORY_FILE, history)


def get_python_info() -> dict:
    info = {
        "executable": sys.executable,
        "version": sys.version.split()[0],
        "architecture": "64-bit" if sys.maxsize > 2**32 else "32-bit",
        "platform": sys.platform,
    }
    try:
        r = subprocess.run(
            [sys.executable, "-m", "PyInstaller", "--version"],
            capture_output=True, text=True, timeout=10, check=False
        )
        info["pyinstaller"] = r.stdout.strip() if r.returncode == 0 else "Chưa cài"
    except Exception:
        info["pyinstaller"] = "Không xác định"
    return info


def kill_process_tree(pid: int) -> None:
    if sys.platform != "win32":
        try:
            os.kill(pid, 15)
            time.sleep(0.2)
            os.kill(pid, 9)
        except Exception:
            pass
        return
    try:
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(pid)],
            capture_output=True, text=True, timeout=10, check=False
        )
    except Exception:
        try:
            os.kill(pid, 9)
        except Exception:
            pass


def is_writable_dir(path: Path) -> bool:
    try:
        ensure_dir(path)
        test = path / ".dong_goi_write_test"
        test.write_text("ok", encoding="utf-8")
        test.unlink(missing_ok=True)
        return True
    except Exception:
        return False


def is_valid_exe_name(name: str) -> tuple[bool, str]:
    name = name.strip()
    if not name:
        return False, "Tên EXE không được để trống"
    if any(c in name for c in INVALID_NAME_CHARS):
        return False, f"Tên EXE chứa ký tự không hợp lệ: {INVALID_NAME_CHARS}"
    if name.endswith("."):
        return False, "Tên EXE không được kết thúc bằng dấu chấm"
    if len(name) > 100:
        return False, "Tên EXE quá dài"
    return True, ""


def open_path(path: str | Path) -> None:
    path = str(path)
    if sys.platform == "win32":
        os.startfile(path)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


# ---------------------------------------------------------------------------
# Worker (đã sửa Critical)
# ---------------------------------------------------------------------------

class BuildWorker(threading.Thread):
    def __init__(self, config: BuildConfig, event_queue: queue.Queue, cancel_event: threading.Event):
        super().__init__(daemon=True)
        self.config = config
        self.q = event_queue
        self.cancel = cancel_event
        self.proc: Optional[subprocess.Popen] = None
        self._log_file = None
        self._stage = "Chuẩn bị"
        self._progress = 0
        self._build_start_time = 0.0
        self._expected_product: Optional[Path] = None

    def _emit(self, kind: str, message: str = "", level: str = "info", **kwargs):
        self.q.put(BuildEvent(kind=kind, message=message, level=level, **kwargs))

    def _set_stage(self, stage: str, progress: int):
        self._stage = stage
        self._progress = max(self._progress, progress)
        self._emit("progress", data={"value": self._progress, "stage": stage})
        self._emit("status", stage)

    def _log(self, msg: str, level: str = "info"):
        self._emit("log", msg, level)
        if self._log_file:
            try:
                self._log_file.write(msg + "\n")
                self._log_file.flush()
            except Exception:
                pass

    def run(self):
        log_path = None
        try:
            ensure_dir(LOG_DIR)
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            log_path = LOG_DIR / f"build_{stamp}.log"
            self._log_file = open(log_path, "w", encoding="utf-8", errors="replace")
            self._emit("status", "Bắt đầu", data={"log_path": str(log_path)})
            self._set_stage("Kiểm tra môi trường", 3)

            # --- Validate ---
            py = Path(self.config.py_file)
            if not py.is_file() or py.suffix.lower() != ".py":
                self._emit("finished", "File Python không hợp lệ", success=False)
                return

            out_dir = Path(self.config.output_dir or (py.parent / "dist"))
            if not is_writable_dir(out_dir):
                self._emit("finished", f"Không có quyền ghi vào thư mục:\n{out_dir}", success=False)
                return

            name = self.config.name.strip() or py.stem
            ok, err = is_valid_exe_name(name)
            if not ok:
                self._emit("finished", err, success=False)
                return

            # Xác định sản phẩm mong đợi trước khi build
            if self.config.onefile:
                self._expected_product = out_dir / f"{name}.exe"
            else:
                self._expected_product = out_dir / name

            # Kiểm tra các file tùy chọn
            if self.config.icon.strip() and not Path(self.config.icon).is_file():
                self._log(f"Cảnh báo: Icon không tồn tại → bỏ qua: {self.config.icon}", "warn")
            if self.config.version_file.strip() and not Path(self.config.version_file).is_file():
                self._log(f"Cảnh báo: Version-file không tồn tại → bỏ qua", "warn")
            if self.config.upx and self.config.upx_dir.strip():
                upx_exe = Path(self.config.upx_dir) / ("upx.exe" if sys.platform == "win32" else "upx")
                if not upx_exe.is_file():
                    self._log(f"Cảnh báo: Không tìm thấy upx trong {self.config.upx_dir}", "warn")

            if not self._ensure_pyinstaller():
                self._emit("finished", "Không thể sử dụng PyInstaller", success=False)
                return

            if self.cancel.is_set():
                self._emit("finished", "Đã hủy trước khi build", success=False, data={"cancelled": True})
                return

            self._set_stage("Đang phân tích & đóng gói", 10)
            self._build_start_time = time.time()

            cmd = self._build_command(out_dir)
            self._log("Lệnh: " + " ".join(f'"{c}"' if " " in c else c for c in cmd))
            self._log("-" * 60)

            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0

            self.proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                creationflags=creationflags,
            )

            # ===== Reader thread (sửa lỗi treo khi hủy) =====
            line_queue: queue.Queue = queue.Queue()

            def reader():
                try:
                    assert self.proc is not None and self.proc.stdout is not None
                    for line in self.proc.stdout:
                        line_queue.put(line)
                    line_queue.put(None)  # EOF
                except Exception:
                    line_queue.put(None)

            t_reader = threading.Thread(target=reader, daemon=True)
            t_reader.start()

            while True:
                if self.cancel.is_set():
                    self._log(">>> Người dùng yêu cầu hủy...", "warn")
                    self._set_stage("Đang hủy...", 0)
                    self._terminate()
                    self._emit("finished", "Đã hủy bởi người dùng", success=False, data={"cancelled": True})
                    return

                try:
                    line = line_queue.get(timeout=0.25)
                except queue.Empty:
                    if self.proc.poll() is not None:
                        # process đã kết thúc, lấy nốt phần còn lại
                        while True:
                            try:
                                line = line_queue.get_nowait()
                                if line is None:
                                    break
                                self._process_line(line)
                            except queue.Empty:
                                break
                        break
                    continue

                if line is None:
                    break

                self._process_line(line)

            ret = self.proc.wait(timeout=8)
            self.proc = None

            if self.cancel.is_set():
                self._emit("finished", "Đã hủy", success=False, data={"cancelled": True})
                return

            if ret != 0:
                self._log(f"PyInstaller thoát với mã {ret}", "error")
                self._emit("finished", f"Build thất bại (mã {ret})", success=False)
                return

            # ===== Kiểm tra sản phẩm chính xác =====
            self._set_stage("Đang kiểm tra sản phẩm", 92)
            product = self._verify_product()
            if not product:
                self._log("Không tìm thấy sản phẩm hợp lệ sau build!", "error")
                self._emit("finished", "Build báo thành công nhưng không tìm thấy sản phẩm hợp lệ", success=False)
                return

            size_mb = 0.0
            if product.is_file():
                size_mb = product.stat().st_size / (1024 * 1024)
                self._log(f"Sản phẩm: {product}")
                self._log(f"Kích thước: {size_mb:.2f} MB")
            else:
                self._log(f"Sản phẩm (thư mục): {product}")

            # Post-build verification nhẹ
            if product.is_file() and product.suffix.lower() == ".exe":
                self._log("Đã xác nhận file EXE tồn tại và được tạo trong lần build này.")

            self._set_stage("Hoàn tất", 100)
            self._emit(
                "finished",
                "Đóng gói THÀNH CÔNG",
                success=True,
                data={
                    "product": str(product),
                    "size_mb": size_mb,
                    "log_path": str(log_path),
                    "duration": time.time() - self._build_start_time,
                },
            )

        except Exception as e:
            self._log(traceback.format_exc(), "error")
            self._emit("finished", f"Lỗi không mong muốn: {e}", success=False)
        finally:
            if self._log_file:
                try:
                    self._log_file.close()
                except Exception:
                    pass
            self.proc = None

    def _process_line(self, line: str):
        line = line.rstrip("\r\n")
        self._log(line)

        # Cập nhật giai đoạn dựa trên log
        low = line.lower()
        if "analyzing" in low or "analysis" in low:
            self._set_stage("Đang phân tích mã nguồn", 20)
        elif "processing" in low or "looking for" in low or "collecting" in low:
            self._set_stage("Đang thu thập thư viện", 40)
        elif "building pkg" in low or "building exe" in low or "building collect" in low:
            self._set_stage("Đang đóng gói EXE", 70)
        elif "bootloader" in low or "copying bootloader" in low:
            self._set_stage("Đang sao chép bootloader", 85)
        elif "building complete" in low or "successfully" in low:
            self._set_stage("Đang hoàn tất", 90)

    def _ensure_pyinstaller(self) -> bool:
        try:
            r = subprocess.run(
                [sys.executable, "-m", "PyInstaller", "--version"],
                capture_output=True, text=True, timeout=12, check=False
            )
            if r.returncode == 0:
                self._log(f"PyInstaller: {r.stdout.strip()}")
                return True
        except Exception as e:
            self._log(f"Kiểm tra PyInstaller lỗi: {e}", "warn")

        self._log("PyInstaller chưa có. Đang cài đặt (không upgrade)...", "warn")
        self._set_stage("Đang cài PyInstaller", 6)

        if self.cancel.is_set():
            return False

        try:
            # Không dùng --upgrade để tránh phá môi trường người dùng
            r = subprocess.run(
                [sys.executable, "-m", "pip", "install", "pyinstaller"],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=300, check=False
            )
            self._log(r.stdout or "")
            self._log(r.stderr or "")
            if r.returncode != 0:
                self._log("Cài đặt PyInstaller thất bại", "error")
                return False
            self._log("Cài đặt PyInstaller thành công")
            return True
        except Exception as e:
            self._log(f"Lỗi cài PyInstaller: {e}", "error")
            return False

    def _build_command(self, out_dir: Path) -> list[str]:
        cfg = self.config
        work = Path(cfg.workpath) if cfg.workpath else out_dir / "build"
        spec = Path(cfg.specpath) if cfg.specpath else out_dir

        cmd = [
            sys.executable, "-m", "PyInstaller",
            "--distpath", str(out_dir),
            "--workpath", str(work),
            "--specpath", str(spec),
            "--noconfirm",
        ]

        if cfg.onefile:
            cmd.append("--onefile")
        else:
            cmd.append("--onedir")

        if cfg.clean:
            cmd.append("--clean")

        if cfg.name.strip():
            cmd.extend(["--name", cfg.name.strip()])

        if cfg.icon.strip() and Path(cfg.icon).is_file():
            cmd.extend(["--icon", cfg.icon.strip()])

        if cfg.noconsole:
            cmd.append("--noconsole")
        else:
            cmd.append("--console")

        if cfg.upx and cfg.upx_dir.strip() and Path(cfg.upx_dir).exists():
            cmd.extend(["--upx-dir", cfg.upx_dir.strip()])
        else:
            cmd.append("--noupx")

        for mod in (cfg.exclude_module or "").split(","):
            mod = mod.strip()
            if mod:
                cmd.extend(["--exclude-module", mod])

        if cfg.version_file.strip() and Path(cfg.version_file).is_file():
            cmd.extend(["--version-file", cfg.version_file.strip()])

        if cfg.uac_admin:
            cmd.append("--uac-admin")
        if cfg.debug:
            cmd.append("--debug=all")
        if cfg.strip:
            cmd.append("--strip")

        for item in (cfg.add_data or "").split("|"):
            item = item.strip()
            if not item:
                continue
            if ";" in item:
                src, dest = item.split(";", 1)
                cmd.extend(["--add-data", f"{src.strip()}{ADD_DATA_SEP}{dest.strip()}"])
            else:
                cmd.extend(["--add-data", f"{item}{ADD_DATA_SEP}."])

        for imp in (cfg.hidden_import or "").split(","):
            imp = imp.strip()
            if imp:
                cmd.extend(["--hidden-import", imp])

        if cfg.extra_args.strip():
            try:
                extra = shlex.split(cfg.extra_args.strip())
                cmd.extend(extra)
            except ValueError:
                cmd.extend(cfg.extra_args.strip().split())

        cmd.append(str(Path(cfg.py_file).resolve()))
        return cmd

    def _verify_product(self) -> Optional[Path]:
        """Chỉ chấp nhận sản phẩm được tạo sau thời điểm bắt đầu build."""
        expected = self._expected_product
        if expected is None:
            return None

        if expected.exists():
            # Kiểm tra thời gian tạo/sửa
            mtime = expected.stat().st_mtime if expected.is_file() else max(
                (p.stat().st_mtime for p in expected.rglob("*") if p.is_file()),
                default=0
            )
            if mtime >= self._build_start_time - 2:  # cho phép sai số nhỏ
                return expected

        # Fallback cực kỳ hạn chế: chỉ lấy đúng tên trong lần build này
        name = self.config.name.strip() or Path(self.config.py_file).stem
        if self.config.onefile:
            candidate = expected.parent / f"{name}.exe"
            if candidate.exists() and candidate.stat().st_mtime >= self._build_start_time - 2:
                return candidate
        return None

    def _terminate(self):
        if self.proc and self.proc.poll() is None:
            pid = self.proc.pid
            self._log(f"Đang kết thúc tiến trình PID {pid}...", "warn")
            try:
                self.proc.terminate()
                try:
                    self.proc.wait(timeout=2.5)
                except subprocess.TimeoutExpired:
                    kill_process_tree(pid)
                    try:
                        self.proc.wait(timeout=3)
                    except Exception:
                        pass
            except Exception as e:
                self._log(f"Lỗi terminate: {e}", "error")
                kill_process_tree(pid)
        self.proc = None


# ---------------------------------------------------------------------------
# Main Application
# ---------------------------------------------------------------------------

class DongGoiApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("1000x800")
        self.root.minsize(880, 680)

        self.event_q: queue.Queue = queue.Queue()
        self.cancel_event = threading.Event()
        self.worker: Optional[BuildWorker] = None
        self.building = False
        self.start_time: Optional[float] = None
        self.current_log_path: Optional[str] = None
        self.saved_cfg = load_config()

        self._build_ui()
        self._load_ui_from_config()
        self._poll_events()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self):
        main = ttk.Frame(self.root, padding=8)
        main.pack(fill=tk.BOTH, expand=True)

        self.notebook = ttk.Notebook(main)
        self.notebook.pack(fill=tk.BOTH, expand=True, pady=(0, 8))

        # ========== Tab 1: Cơ bản ==========
        tab1 = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(tab1, text="  1. Dự án & Cơ bản  ")

        # Preset
        f_preset = ttk.LabelFrame(tab1, text="Preset nhanh", padding=8)
        f_preset.pack(fill=tk.X, pady=(0, 8))
        r = ttk.Frame(f_preset)
        r.pack(fill=tk.X)
        ttk.Label(r, text="Chọn preset:").pack(side=tk.LEFT)
        self.var_preset = tk.StringVar(value="Console cơ bản")
        cb = ttk.Combobox(r, textvariable=self.var_preset, values=list(PRESETS.keys()), state="readonly", width=28)
        cb.pack(side=tk.LEFT, padx=8)
        ttk.Button(r, text="Áp dụng preset", command=self._apply_preset).pack(side=tk.LEFT)

        # File nguồn
        f1 = ttk.LabelFrame(tab1, text="File nguồn", padding=8)
        f1.pack(fill=tk.X, pady=(0, 8))
        r = ttk.Frame(f1)
        r.pack(fill=tk.X)
        ttk.Label(r, text="File Python:").pack(side=tk.LEFT)
        self.var_py = tk.StringVar()
        self.entry_py = ttk.Entry(r, textvariable=self.var_py)
        self.entry_py.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6)
        ttk.Button(r, text="Chọn…", command=self._browse_py).pack(side=tk.LEFT)
        ttk.Button(r, text="Mở thư mục", command=self._open_py_dir).pack(side=tk.LEFT, padx=(4, 0))

        # Đầu ra
        f2 = ttk.LabelFrame(tab1, text="Đầu ra", padding=8)
        f2.pack(fill=tk.X, pady=(0, 8))

        r = ttk.Frame(f2)
        r.pack(fill=tk.X, pady=2)
        ttk.Label(r, text="Tên EXE:", width=12).pack(side=tk.LEFT)
        self.var_name = tk.StringVar()
        ttk.Entry(r, textvariable=self.var_name, width=25).pack(side=tk.LEFT, padx=4)
        ttk.Label(r, text="Thư mục xuất:").pack(side=tk.LEFT, padx=(12, 0))
        self.var_outdir = tk.StringVar()
        ttk.Entry(r, textvariable=self.var_outdir).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)
        ttk.Button(r, text="Chọn…", command=self._browse_outdir).pack(side=tk.LEFT)

        r = ttk.Frame(f2)
        r.pack(fill=tk.X, pady=2)
        ttk.Label(r, text="Icon (.ico):", width=12).pack(side=tk.LEFT)
        self.var_icon = tk.StringVar()
        ttk.Entry(r, textvariable=self.var_icon).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)
        ttk.Button(r, text="Chọn…", command=self._browse_icon).pack(side=tk.LEFT)

        # Tùy chọn cơ bản
        f3 = ttk.LabelFrame(tab1, text="Tùy chọn cơ bản", padding=8)
        f3.pack(fill=tk.X)

        self.var_onefile = tk.BooleanVar(value=True)
        self.var_noconsole = tk.BooleanVar(value=False)
        self.var_clean = tk.BooleanVar(value=True)

        r = ttk.Frame(f3)
        r.pack(fill=tk.X)
        ttk.Checkbutton(r, text="One-file", variable=self.var_onefile).pack(side=tk.LEFT, padx=(0, 16))
        ttk.Checkbutton(r, text="Ẩn console (--noconsole)", variable=self.var_noconsole).pack(side=tk.LEFT, padx=(0, 16))
        ttk.Checkbutton(r, text="Clean trước khi build", variable=self.var_clean).pack(side=tk.LEFT)

        # ========== Tab 2: Nâng cao ==========
        tab2 = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(tab2, text="  2. Tùy chọn nâng cao  ")

        f_upx = ttk.LabelFrame(tab2, text="UPX", padding=8)
        f_upx.pack(fill=tk.X, pady=(0, 8))
        self.var_upx = tk.BooleanVar(value=False)
        ttk.Checkbutton(f_upx, text="Sử dụng UPX", variable=self.var_upx).pack(anchor=tk.W)
        r = ttk.Frame(f_upx)
        r.pack(fill=tk.X, pady=4)
        ttk.Label(r, text="Thư mục UPX:").pack(side=tk.LEFT)
        self.var_upx_dir = tk.StringVar()
        ttk.Entry(r, textvariable=self.var_upx_dir).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6)
        ttk.Button(r, text="Chọn…", command=self._browse_upx).pack(side=tk.LEFT)

        f_ex = ttk.LabelFrame(tab2, text="Loại trừ & Version", padding=8)
        f_ex.pack(fill=tk.X, pady=(0, 8))

        r = ttk.Frame(f_ex)
        r.pack(fill=tk.X, pady=2)
        ttk.Label(r, text="--exclude-module:", width=20).pack(side=tk.LEFT)
        self.var_exclude = tk.StringVar()
        ttk.Entry(r, textvariable=self.var_exclude).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)

        r = ttk.Frame(f_ex)
        r.pack(fill=tk.X, pady=2)
        ttk.Label(r, text="--version-file:", width=20).pack(side=tk.LEFT)
        self.var_version = tk.StringVar()
        ttk.Entry(r, textvariable=self.var_version).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)
        ttk.Button(r, text="Chọn…", command=self._browse_version).pack(side=tk.LEFT)

        f_flags = ttk.LabelFrame(tab2, text="Cờ bổ sung", padding=8)
        f_flags.pack(fill=tk.X, pady=(0, 8))
        self.var_uac = tk.BooleanVar(value=False)
        self.var_debug = tk.BooleanVar(value=False)
        self.var_strip = tk.BooleanVar(value=False)
        r = ttk.Frame(f_flags)
        r.pack(fill=tk.X)
        ttk.Checkbutton(r, text="UAC Admin", variable=self.var_uac).pack(side=tk.LEFT, padx=(0, 16))
        ttk.Checkbutton(r, text="Debug", variable=self.var_debug).pack(side=tk.LEFT, padx=(0, 16))
        ttk.Checkbutton(r, text="Strip", variable=self.var_strip).pack(side=tk.LEFT)

        f_data = ttk.LabelFrame(tab2, text="Dữ liệu & Import ẩn", padding=8)
        f_data.pack(fill=tk.X, pady=(0, 8))

        r = ttk.Frame(f_data)
        r.pack(fill=tk.X, pady=2)
        ttk.Label(r, text="--add-data:", width=20).pack(side=tk.LEFT)
        self.var_adddata = tk.StringVar()
        ttk.Entry(r, textvariable=self.var_adddata).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)

        r = ttk.Frame(f_data)
        r.pack(fill=tk.X, pady=2)
        ttk.Label(r, text="--hidden-import:", width=20).pack(side=tk.LEFT)
        self.var_hidden = tk.StringVar()
        ttk.Entry(r, textvariable=self.var_hidden).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)

        f_extra = ttk.LabelFrame(tab2, text="Đối số thêm", padding=8)
        f_extra.pack(fill=tk.X)
        self.var_extra = tk.StringVar()
        ttk.Entry(f_extra, textvariable=self.var_extra).pack(fill=tk.X, pady=4)
        ttk.Label(f_extra, text="Ví dụ: --collect-all sklearn --collect-data certifi", foreground="gray").pack(anchor=tk.W)

        # ========== Tab 3: Log ==========
        tab3 = ttk.Frame(self.notebook, padding=8)
        self.notebook.add(tab3, text="  3. Log build  ")

        self.txt_log = scrolledtext.ScrolledText(
            tab3, height=18, font=("Consolas", 9), state=tk.DISABLED, wrap=tk.WORD
        )
        self.txt_log.pack(fill=tk.BOTH, expand=True)
        self.txt_log.tag_config("info", foreground="#1a1a1a")
        self.txt_log.tag_config("warn", foreground="#b36b00")
        self.txt_log.tag_config("error", foreground="#c62828")
        self.txt_log.tag_config("success", foreground="#2e7d32")

        r = ttk.Frame(tab3)
        r.pack(fill=tk.X, pady=(6, 0))
        ttk.Button(r, text="Xóa log", command=self._clear_log_ui).pack(side=tk.LEFT)
        ttk.Button(r, text="Sao chép", command=self._copy_log).pack(side=tk.LEFT, padx=4)
        ttk.Button(r, text="Mở file log", command=self._open_log_file).pack(side=tk.LEFT, padx=4)
        ttk.Button(r, text="Lưu log…", command=self._save_log_as).pack(side=tk.LEFT, padx=4)

        # ========== Tab 4: Lịch sử ==========
        tab4 = ttk.Frame(self.notebook, padding=8)
        self.notebook.add(tab4, text="  4. Lịch sử build  ")

        cols = ("time", "name", "result", "size", "duration")
        self.tree_history = ttk.Treeview(tab4, columns=cols, show="headings", height=16)
        self.tree_history.heading("time", text="Thời gian")
        self.tree_history.heading("name", text="Tên")
        self.tree_history.heading("result", text="Kết quả")
        self.tree_history.heading("size", text="Kích thước")
        self.tree_history.heading("duration", text="Thời gian chạy")
        self.tree_history.column("time", width=140)
        self.tree_history.column("name", width=180)
        self.tree_history.column("result", width=100)
        self.tree_history.column("size", width=100)
        self.tree_history.column("duration", width=100)
        self.tree_history.pack(fill=tk.BOTH, expand=True)

        r = ttk.Frame(tab4)
        r.pack(fill=tk.X, pady=(6, 0))
        ttk.Button(r, text="Làm mới", command=self._refresh_history).pack(side=tk.LEFT)
        ttk.Button(r, text="Xóa lịch sử", command=self._clear_history).pack(side=tk.LEFT, padx=6)

        # ========== Thanh điều khiển ==========
        ctrl = ttk.LabelFrame(main, text="Tiến trình", padding=8)
        ctrl.pack(fill=tk.X)

        self.progress = ttk.Progressbar(ctrl, mode="determinate", maximum=100)
        self.progress.pack(fill=tk.X, pady=(0, 4))

        r = ttk.Frame(ctrl)
        r.pack(fill=tk.X)
        self.lbl_status = ttk.Label(r, text="Sẵn sàng", foreground="gray")
        self.lbl_status.pack(side=tk.LEFT)
        self.lbl_time = ttk.Label(r, text="")
        self.lbl_time.pack(side=tk.RIGHT)

        r = ttk.Frame(ctrl)
        r.pack(fill=tk.X, pady=(6, 0))
        self.btn_start = ttk.Button(r, text="▶  Bắt đầu đóng gói", command=self._start_build)
        self.btn_start.pack(side=tk.LEFT, padx=(0, 6))
        self.btn_cancel = ttk.Button(r, text="■  Hủy", command=self._cancel_build, state=tk.DISABLED)
        self.btn_cancel.pack(side=tk.LEFT, padx=(0, 6))
        self.btn_open_out = ttk.Button(r, text="Mở thư mục xuất", command=self._open_outdir, state=tk.DISABLED)
        self.btn_open_out.pack(side=tk.LEFT, padx=(0, 6))
        self.btn_open_exe = ttk.Button(r, text="Mở EXE", command=self._open_exe, state=tk.DISABLED)
        self.btn_open_exe.pack(side=tk.LEFT, padx=(0, 6))
        self.btn_show_cmd = ttk.Button(r, text="Xem lệnh", command=self._show_command)
        self.btn_show_cmd.pack(side=tk.LEFT)

        self.statusbar = ttk.Label(self.root, text="", relief=tk.SUNKEN, anchor=tk.W)
        self.statusbar.pack(side=tk.BOTTOM, fill=tk.X)
        self._update_env_info()
        self._refresh_history()

    def _update_env_info(self):
        info = get_python_info()
        self.statusbar.config(
            text=f"Python {info['version']} ({info['architecture']})  |  "
                 f"PyInstaller: {info['pyinstaller']}  |  {info['executable']}"
        )

    # ------------------------------------------------------------------ Config & Preset
    def _load_ui_from_config(self):
        c = self.saved_cfg
        self.var_py.set(c.get("last_py_file", ""))
        self.var_outdir.set(c.get("last_output_dir", ""))
        self.var_name.set(c.get("last_name", ""))
        self.var_icon.set(c.get("last_icon", ""))
        self.var_onefile.set(c.get("onefile", True))
        self.var_noconsole.set(c.get("noconsole", False))
        self.var_clean.set(c.get("clean", True))
        self.var_adddata.set(c.get("add_data", ""))
        self.var_hidden.set(c.get("hidden_import", ""))
        self.var_upx.set(c.get("upx", False))
        self.var_upx_dir.set(c.get("upx_dir", ""))
        self.var_exclude.set(c.get("exclude_module", ""))
        self.var_version.set(c.get("version_file", ""))
        self.var_uac.set(c.get("uac_admin", False))
        self.var_debug.set(c.get("debug", False))
        self.var_strip.set(c.get("strip", False))
        self.var_extra.set(c.get("extra_args", ""))

    def _collect_config(self) -> BuildConfig:
        return BuildConfig(
            py_file=self.var_py.get().strip(),
            output_dir=self.var_outdir.get().strip(),
            name=self.var_name.get().strip(),
            icon=self.var_icon.get().strip(),
            onefile=self.var_onefile.get(),
            noconsole=self.var_noconsole.get(),
            clean=self.var_clean.get(),
            add_data=self.var_adddata.get().strip(),
            hidden_import=self.var_hidden.get().strip(),
            upx=self.var_upx.get(),
            upx_dir=self.var_upx_dir.get().strip(),
            exclude_module=self.var_exclude.get().strip(),
            version_file=self.var_version.get().strip(),
            uac_admin=self.var_uac.get(),
            debug=self.var_debug.get(),
            strip=self.var_strip.get(),
            extra_args=self.var_extra.get().strip(),
        )

    def _persist_config(self, cfg: BuildConfig):
        self.saved_cfg.update({
            "last_py_file": cfg.py_file,
            "last_output_dir": cfg.output_dir,
            "last_name": cfg.name,
            "last_icon": cfg.icon,
            "onefile": cfg.onefile,
            "noconsole": cfg.noconsole,
            "clean": cfg.clean,
            "add_data": cfg.add_data,
            "hidden_import": cfg.hidden_import,
            "upx": cfg.upx,
            "upx_dir": cfg.upx_dir,
            "exclude_module": cfg.exclude_module,
            "version_file": cfg.version_file,
            "uac_admin": cfg.uac_admin,
            "debug": cfg.debug,
            "strip": cfg.strip,
            "extra_args": cfg.extra_args,
        })
        save_config(self.saved_cfg)

    def _apply_preset(self):
        name = self.var_preset.get()
        preset = PRESETS.get(name)
        if not preset:
            return
        self.var_onefile.set(preset.get("onefile", True))
        self.var_noconsole.set(preset.get("noconsole", False))
        self.var_hidden.set(preset.get("hidden_import", ""))
        self.var_exclude.set(preset.get("exclude_module", ""))
        self.var_extra.set(preset.get("extra_args", ""))
        messagebox.showinfo("Preset", f"Đã áp dụng preset: {name}")

    # ------------------------------------------------------------------ Browse
    def _browse_py(self):
        p = filedialog.askopenfilename(title="Chọn file Python", filetypes=[("Python", "*.py"), ("All", "*.*")])
        if p:
            self.var_py.set(p)
            if not self.var_name.get().strip():
                self.var_name.set(Path(p).stem)
            if not self.var_outdir.get().strip():
                self.var_outdir.set(str(Path(p).parent / "dist"))

    def _browse_outdir(self):
        p = filedialog.askdirectory(title="Chọn thư mục xuất")
        if p:
            self.var_outdir.set(p)

    def _browse_icon(self):
        p = filedialog.askopenfilename(title="Chọn icon", filetypes=[("Icon", "*.ico"), ("All", "*.*")])
        if p:
            self.var_icon.set(p)

    def _browse_upx(self):
        p = filedialog.askdirectory(title="Chọn thư mục chứa upx.exe")
        if p:
            self.var_upx_dir.set(p)

    def _browse_version(self):
        p = filedialog.askopenfilename(title="Chọn version file", filetypes=[("Text", "*.txt"), ("All", "*.*")])
        if p:
            self.var_version.set(p)

    def _open_py_dir(self):
        p = self.var_py.get().strip()
        if p and Path(p).exists():
            open_path(Path(p).parent)
        else:
            messagebox.showinfo("Thông báo", "Chưa chọn file hợp lệ.")

    def _open_outdir(self):
        p = self.var_outdir.get().strip()
        if p and Path(p).exists():
            open_path(p)
        else:
            messagebox.showinfo("Thông báo", "Thư mục xuất chưa tồn tại.")

    def _open_exe(self):
        if hasattr(self, "_last_product") and self._last_product and Path(self._last_product).exists():
            open_path(self._last_product)
        else:
            messagebox.showinfo("Thông báo", "Chưa có sản phẩm hợp lệ.")

    def _show_command(self):
        cfg = self._collect_config()
        if not cfg.py_file or not Path(cfg.py_file).is_file():
            messagebox.showwarning("Cảnh báo", "Vui lòng chọn file Python hợp lệ trước.")
            return
        out_dir = Path(cfg.output_dir or (Path(cfg.py_file).parent / "dist"))
        dummy = BuildWorker(cfg, queue.Queue(), threading.Event())
        cmd = dummy._build_command(out_dir)
        cmd_str = " ".join(f'"{c}"' if " " in c else c for c in cmd)
        messagebox.showinfo("Lệnh PyInstaller sẽ chạy", cmd_str)

    # ------------------------------------------------------------------ Log & History
    def _append_log(self, text: str, level: str = "info"):
        self.txt_log.config(state=tk.NORMAL)
        self.txt_log.insert(tk.END, text + "\n", level)
        lines = int(self.txt_log.index("end-1c").split(".")[0])
        if lines > MAX_LOG_LINES_UI:
            self.txt_log.delete("1.0", f"{lines - MAX_LOG_LINES_UI}.0")
        self.txt_log.see(tk.END)
        self.txt_log.config(state=tk.DISABLED)

    def _clear_log_ui(self):
        self.txt_log.config(state=tk.NORMAL)
        self.txt_log.delete("1.0", tk.END)
        self.txt_log.config(state=tk.DISABLED)

    def _copy_log(self):
        content = self.txt_log.get("1.0", tk.END)
        self.root.clipboard_clear()
        self.root.clipboard_append(content)
        messagebox.showinfo("Sao chép", "Đã sao chép log vào clipboard.")

    def _open_log_file(self):
        if self.current_log_path and Path(self.current_log_path).exists():
            open_path(self.current_log_path)
        else:
            messagebox.showinfo("Thông báo", "Chưa có file log của lần build này.")

    def _save_log_as(self):
        p = filedialog.asksaveasfilename(defaultextension=".log", filetypes=[("Log", "*.log"), ("Text", "*.txt")])
        if p:
            try:
                with open(p, "w", encoding="utf-8") as f:
                    f.write(self.txt_log.get("1.0", tk.END))
                messagebox.showinfo("Thành công", f"Đã lưu log:\n{p}")
            except Exception as e:
                messagebox.showerror("Lỗi", str(e))

    def _refresh_history(self):
        for i in self.tree_history.get_children():
            self.tree_history.delete(i)
        for item in load_history():
            self.tree_history.insert("", tk.END, values=(
                item.get("time", ""),
                item.get("name", ""),
                item.get("result", ""),
                item.get("size", ""),
                item.get("duration", ""),
            ))

    def _clear_history(self):
        if messagebox.askyesno("Xác nhận", "Xóa toàn bộ lịch sử build?"):
            save_json(HISTORY_FILE, [])
            self._refresh_history()

    # ------------------------------------------------------------------ Build control
    def _set_building(self, active: bool):
        self.building = active
        state = tk.DISABLED if active else tk.NORMAL
        self.btn_start.config(state=state)
        self.btn_cancel.config(state=tk.NORMAL if active else tk.DISABLED)
        self.btn_show_cmd.config(state=state)
        try:
            self.entry_py.config(state=state)
        except Exception:
            pass
        if active:
            self.progress["value"] = 0
            self.start_time = time.time()
            self._last_product = None
            self.btn_open_exe.config(state=tk.DISABLED)
        else:
            self.start_time = None

    def _start_build(self):
        if self.building:
            return
        cfg = self._collect_config()

        # Validation
        if not cfg.py_file:
            messagebox.showwarning("Cảnh báo", "Vui lòng chọn file Python.")
            return
        if not Path(cfg.py_file).is_file():
            messagebox.showerror("Lỗi", "File Python không tồn tại.")
            return
        if not cfg.py_file.lower().endswith(".py"):
            messagebox.showerror("Lỗi", "File phải có phần mở rộng .py")
            return

        name = cfg.name or Path(cfg.py_file).stem
        ok, err = is_valid_exe_name(name)
        if not ok:
            messagebox.showerror("Lỗi tên EXE", err)
            return

        out = Path(cfg.output_dir or (Path(cfg.py_file).parent / "dist"))
        if not is_writable_dir(out):
            messagebox.showerror("Lỗi", f"Không có quyền ghi vào thư mục:\n{out}")
            return

        candidate = out / (f"{name}.exe" if cfg.onefile else name)
        if candidate.exists():
            if not messagebox.askyesno("File đã tồn tại", f"Sản phẩm có thể bị ghi đè:\n{candidate}\n\nTiếp tục?"):
                return

        self._persist_config(cfg)
        self.cancel_event.clear()
        self._clear_log_ui()
        self._set_building(True)
        self.lbl_status.config(text="Đang chuẩn bị…", foreground="blue")
        self.btn_open_out.config(state=tk.DISABLED)
        self.notebook.select(2)

        self.worker = BuildWorker(cfg, self.event_q, self.cancel_event)
        self.worker.start()

    def _cancel_build(self):
        if not self.building:
            return
        self.cancel_event.set()
        self.lbl_status.config(text="Đang hủy…", foreground="orange")
        self.btn_cancel.config(state=tk.DISABLED)

    def _on_finished(self, ev: BuildEvent):
        self._set_building(False)
        cancelled = ev.data.get("cancelled", False)
        duration = ev.data.get("duration", 0)
        size_mb = ev.data.get("size_mb", 0)
        product = ev.data.get("product", "")

        # Ghi lịch sử
        entry = {
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "name": Path(product).name if product else (self.var_name.get() or "unknown"),
            "result": "Hủy" if cancelled else ("Thành công" if ev.success else "Thất bại"),
            "size": f"{size_mb:.2f} MB" if size_mb else "-",
            "duration": f"{int(duration)}s" if duration else "-",
        }
        add_history(entry)
        self._refresh_history()

        if cancelled:
            self.lbl_status.config(text="Đã hủy", foreground="orange")
            self._append_log("=== ĐÃ HỦY ===", "warn")
        elif ev.success:
            self.progress["value"] = 100
            self.lbl_status.config(text="Thành công", foreground="green")
            self._append_log("=== THÀNH CÔNG ===", "success")
            if product:
                self._append_log(f"Sản phẩm: {product}", "success")
                self._last_product = product
                self.btn_open_out.config(state=tk.NORMAL)
                self.btn_open_exe.config(state=tk.NORMAL)
            messagebox.showinfo("Thành công", f"{ev.message}\n\n{product}")
        else:
            self.lbl_status.config(text="Thất bại", foreground="red")
            self._append_log(f"=== THẤT BẠI: {ev.message} ===", "error")
            messagebox.showerror("Thất bại", ev.message)

        if "log_path" in ev.data:
            self.current_log_path = ev.data["log_path"]

    def _poll_events(self):
        try:
            while True:
                ev: BuildEvent = self.event_q.get_nowait()
                if ev.kind == "log":
                    self._append_log(ev.message, ev.level)
                elif ev.kind == "status":
                    self.lbl_status.config(text=ev.message, foreground="blue")
                    if "log_path" in ev.data:
                        self.current_log_path = ev.data["log_path"]
                elif ev.kind == "progress":
                    self.progress["value"] = ev.data.get("value", 0)
                    stage = ev.data.get("stage")
                    if stage:
                        self.lbl_status.config(text=stage, foreground="blue")
                elif ev.kind == "finished":
                    self._on_finished(ev)
                elif ev.kind == "error":
                    self._append_log(ev.message, "error")
        except queue.Empty:
            pass

        if self.building and self.start_time:
            elapsed = int(time.time() - self.start_time)
            self.lbl_time.config(text=f"Thời gian: {elapsed // 60:02d}:{elapsed % 60:02d}")

        self.root.after(80, self._poll_events)

    def _on_close(self):
        if not self.building:
            self.root.destroy()
            return
        if messagebox.askyesno("Đang đóng gói", "Đang có tiến trình build.\nBạn có muốn hủy và thoát không?"):
            self.cancel_event.set()
            self.lbl_status.config(text="Đang dừng để thoát…", foreground="orange")
            self.root.after(200, self._wait_and_destroy)

    def _wait_and_destroy(self, retries: int = 40):
        if self.worker and self.worker.is_alive() and retries > 0:
            if retries < 10 and self.worker.proc and self.worker.proc.poll() is None:
                kill_process_tree(self.worker.proc.pid)
            self.root.after(200, lambda: self._wait_and_destroy(retries - 1))
        else:
            try:
                self.root.destroy()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Entry
# ---------------------------------------------------------------------------

def main():
    root = tk.Tk()
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    style = ttk.Style()
    if "vista" in style.theme_names():
        style.theme_use("vista")
    app = DongGoiApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()