"""Nhận diện phần cứng cục bộ và quản lý hồ sơ hiệu năng (Eco / Balanced / Performance)."""
import ctypes
import logging
import os
import subprocess
import sys
from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple

from app.database import get_app_setting, set_app_setting

logger = logging.getLogger(__name__)

VALID_PROFILE_MODES = ("auto", "eco", "balanced", "performance")
HARDWARE_PROFILE_SETTING_KEY = "hardware_profile_mode"

PROFILE_DEFINITIONS: Dict[str, Dict[str, Any]] = {
    "eco": {
        "id": "eco",
        "label": "Eco (Máy yếu / Tiết kiệm RAM)",
        "description": "Ưu tiên tìm kiếm FTS5 tức thì, tắt Reranker nặng, giữ context gọn để chạy mượt trên máy 4–8GB RAM hoặc chỉ có CPU.",
        "warmup_embeddings": False,
        "warmup_reranker": False,
        "warmup_ollama": False,
        "enable_dense_retrieval": True,
        "fts_first_shortcut": True,
        "rerank_enabled": False,
        "rerank_max_candidates": 0,
        "top_k": 3,
        "max_context_tokens": 1200,
        "max_history_tokens": 280,
        "num_ctx": 2048,
        "num_predict": 1024,
        "max_reasoning_steps": 2,
        "enable_self_verify": False,
        "embed_batch_size": 8,
        "preferred_models": ["qwen2.5:1.5b", "qwen2.5:3b", "llama3.2:3b", "llama3.2:1b"],
    },
    "balanced": {
        "id": "balanced",
        "label": "Cân bằng (RAM 16GB / GPU 4GB)",
        "description": "Hybrid RAG kèm Cache ma trận Vector trong RAM, bỏ qua Rerank khi đã khớp rõ ràng và giữ sẵn model Ollama.",
        "warmup_embeddings": True,
        "warmup_reranker": False,
        "warmup_ollama": True,
        "enable_dense_retrieval": True,
        "fts_first_shortcut": False,
        "rerank_enabled": True,
        "rerank_max_candidates": 6,
        "top_k": 5,
        "max_context_tokens": 2200,
        "max_history_tokens": 550,
        "num_ctx": 4096,
        "num_predict": 2048,
        "max_reasoning_steps": 3,
        "enable_self_verify": True,
        "embed_batch_size": 24,
        "preferred_models": ["qwen2.5:3b", "qwen2.5:7b", "llama3.2:3b"],
    },
    "performance": {
        "id": "performance",
        "label": "Hiệu năng cao (RAM >= 24GB / GPU >= 8GB)",
        "description": "Kích hoạt đầy đủ Hybrid RAG, Cross-Encoder Rerank tối đa 12 ứng viên và vòng suy luận đa bước mở rộng.",
        "warmup_embeddings": True,
        "warmup_reranker": True,
        "warmup_ollama": True,
        "enable_dense_retrieval": True,
        "fts_first_shortcut": False,
        "rerank_enabled": True,
        "rerank_max_candidates": 12,
        "top_k": 6,
        "max_context_tokens": 2800,
        "max_history_tokens": 850,
        "num_ctx": 6144,
        "num_predict": 2560,
        "max_reasoning_steps": 4,
        "enable_self_verify": True,
        "embed_batch_size": 32,
        "preferred_models": ["qwen2.5:7b", "qwen2.5:14b", "llama3.1:8b"],
    },
}


def _read_windows_memory_gb() -> Tuple[float, float]:
    """Đọc tổng RAM và RAM khả dụng (GB) trên Windows qua GlobalMemoryStatusEx."""
    class _MemoryStatusEx(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_ulong),
            ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    stat = _MemoryStatusEx()
    stat.dwLength = ctypes.sizeof(_MemoryStatusEx)
    if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):  # type: ignore[attr-defined]
        gb = 1024.0 ** 3
        return round(stat.ullTotalPhys / gb, 2), round(stat.ullAvailPhys / gb, 2)
    return 8.0, 4.0


def _read_unix_memory_gb() -> Tuple[float, float]:
    """Đọc RAM tổng và khả dụng (GB) trên Linux/macOS."""
    try:
        if os.path.exists("/proc/meminfo"):
            values: Dict[str, int] = {}
            with open("/proc/meminfo", "r", encoding="utf-8") as fh:
                for line in fh:
                    parts = line.split(":", 1)
                    if len(parts) == 2:
                        num_parts = parts[1].strip().split()
                        if num_parts and num_parts[0].isdigit():
                            values[parts[0].strip()] = int(num_parts[0])
            total_kb = values.get("MemTotal", 8 * 1024 * 1024)
            avail_kb = values.get("MemAvailable", total_kb // 2)
            return round(total_kb / (1024.0 ** 2), 2), round(avail_kb / (1024.0 ** 2), 2)
        out = subprocess.check_output(["sysctl", "-n", "hw.memsize"], timeout=1.5, text=True).strip()
        total_gb = round(int(out) / (1024.0 ** 3), 2)
        return total_gb, round(total_gb * 0.5, 2)
    except Exception:
        return 8.0, 4.0


def get_memory_gb() -> Tuple[float, float]:
    """Trả về cặp (total_ram_gb, available_ram_gb)."""
    try:
        if sys.platform.startswith("win"):
            return _read_windows_memory_gb()
        return _read_unix_memory_gb()
    except Exception:
        return 8.0, 4.0


@lru_cache(maxsize=1)
def _detect_nvidia_gpu() -> Tuple[Optional[str], int]:
    """Kiểm tra GPU NVIDIA và VRAM (MiB) một lần duy nhất khi khởi động."""
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
            timeout=1.5,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        if not out:
            return None, 0
        first_line = out.splitlines()[0]
        parts = [p.strip() for p in first_line.split(",")]
        name = parts[0] if parts else None
        vram_mb = int(float(parts[1])) if len(parts) > 1 else 0
        return name, vram_mb
    except Exception:
        return None, 0


def detect_hardware_specs() -> Dict[str, Any]:
    """Thu thập thông số phần cứng hiện tại (CPU, RAM, GPU VRAM)."""
    cpu_count = os.cpu_count() or 4
    total_ram_gb, available_ram_gb = get_memory_gb()
    gpu_name, gpu_vram_mb = _detect_nvidia_gpu()
    return {
        "cpu_count": cpu_count,
        "total_ram_gb": total_ram_gb,
        "available_ram_gb": available_ram_gb,
        "gpu_name": gpu_name,
        "gpu_vram_mb": gpu_vram_mb,
        "has_dedicated_gpu": bool(gpu_name and gpu_vram_mb >= 2000),
    }


def recommend_profile_id(specs: Dict[str, Any]) -> str:
    """Đề xuất hồ sơ hiệu năng phù hợp với cấu hình máy."""
    total_ram = float(specs.get("total_ram_gb") or 8.0)
    cpu_count = int(specs.get("cpu_count") or 4)
    vram_mb = int(specs.get("gpu_vram_mb") or 0)

    if vram_mb >= 7500 or (total_ram >= 24.0 and vram_mb >= 3800):
        return "performance"
    if total_ram <= 9.0 or (vram_mb == 0 and total_ram < 12.0) or (cpu_count <= 4 and vram_mb == 0):
        return "eco"
    return "balanced"


def get_selected_profile_mode() -> str:
    """Lấy chế độ hồ sơ người dùng đã chọn ('auto', 'eco', 'balanced', 'performance')."""
    env_mode = (os.getenv("HARDWARE_PROFILE") or "").strip().lower()
    if env_mode in VALID_PROFILE_MODES and env_mode != "auto":
        return env_mode
    saved = (get_app_setting(HARDWARE_PROFILE_SETTING_KEY, "auto") or "auto").strip().lower()
    return saved if saved in VALID_PROFILE_MODES else "auto"


def set_selected_profile_mode(mode: str) -> Dict[str, Any]:
    """Lưu chế độ hồ sơ hiệu năng vào SQLite và trả về trạng thái mới."""
    clean = (mode or "auto").strip().lower()
    if clean not in VALID_PROFILE_MODES:
        raise ValueError(f"Hồ sơ không hợp lệ: {mode}. Chỉ chấp nhận {', '.join(VALID_PROFILE_MODES)}.")
    set_app_setting(HARDWARE_PROFILE_SETTING_KEY, clean)
    return get_hardware_profile_summary()


def get_active_profile_config(mode_override: Optional[str] = None) -> Dict[str, Any]:
    """Trả về tham số runtime đã tinh chỉnh theo phần cứng và lựa chọn hiện tại."""
    specs = detect_hardware_specs()
    recommended_id = recommend_profile_id(specs)
    selected_mode = (mode_override or get_selected_profile_mode()).strip().lower()
    if selected_mode not in VALID_PROFILE_MODES:
        selected_mode = "auto"

    active_id = recommended_id if selected_mode == "auto" else selected_mode
    base = dict(PROFILE_DEFINITIONS[active_id])
    cpu_count = int(specs.get("cpu_count") or 4)

    if active_id == "eco":
        base["cpu_threads_cap"] = max(2, cpu_count // 2)
    elif active_id == "balanced":
        base["cpu_threads_cap"] = max(4, cpu_count - 2) if cpu_count > 4 else cpu_count
    else:
        base["cpu_threads_cap"] = max(4, cpu_count)

    base["selected_mode"] = selected_mode
    base["recommended_id"] = recommended_id
    base["specs"] = specs
    return base


def get_hardware_profile_summary() -> Dict[str, Any]:
    """Dữ liệu tóm tắt trả về qua /api/v1/status và API cấu hình hiệu năng."""
    active = get_active_profile_config()
    available_profiles: List[Dict[str, Any]] = [
        {
            "id": p["id"],
            "label": p["label"],
            "description": p["description"],
            "top_k": p["top_k"],
            "num_ctx": p["num_ctx"],
            "rerank_enabled": p["rerank_enabled"],
            "fts_first_shortcut": p["fts_first_shortcut"],
            "max_reasoning_steps": p["max_reasoning_steps"],
            "preferred_models": p["preferred_models"],
        }
        for p in PROFILE_DEFINITIONS.values()
    ]
    return {
        "active_id": active["id"],
        "active_label": active["label"],
        "selected_mode": active["selected_mode"],
        "recommended_id": active["recommended_id"],
        "specs": active["specs"],
        "runtime": {
            "top_k": active["top_k"],
            "num_ctx": active["num_ctx"],
            "max_context_tokens": active["max_context_tokens"],
            "rerank_enabled": active["rerank_enabled"],
            "fts_first_shortcut": active["fts_first_shortcut"],
            "max_reasoning_steps": active["max_reasoning_steps"],
            "embed_batch_size": active["embed_batch_size"],
            "preferred_models": active["preferred_models"],
        },
        "profiles": available_profiles,
    }
