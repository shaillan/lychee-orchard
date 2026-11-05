"""集中配置：读取项目根目录 .env 与环境变量。

不要把真实 Key 提交到仓库；复制 .env.example 为 .env 后填写。
"""
from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> None:
    """极简 .env 解析：KEY=VALUE，忽略注释与空行，不覆盖已有环境变量。"""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)


_load_dotenv(BASE_DIR / ".env")

# ---------------------------------------------------------------------------
# 病虫害识别
# ---------------------------------------------------------------------------
# auto：有 DASHSCOPE_API_KEY 走通义千问，其次 VISION_API_URL，最后本地模拟
# dashscope / custom / mock：强制指定
VISION_PROVIDER = os.environ.get("VISION_PROVIDER", "auto").strip().lower()

DASHSCOPE_API_KEY = os.environ.get("DASHSCOPE_API_KEY", "").strip()
DASHSCOPE_BASE_URL = os.environ.get(
    "DASHSCOPE_BASE_URL",
    "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
).strip()
VISION_MODEL = os.environ.get("VISION_MODEL", "qwen-vl-plus").strip()

# 自定义视觉 API（约定：POST {image_base64, plot_id} -> {class, confidence, bbox}）
VISION_API_URL = os.environ.get("VISION_API_URL", "").strip()
VISION_API_KEY = os.environ.get("VISION_API_KEY", "").strip()

# ---------------------------------------------------------------------------
# 一物一码
# ---------------------------------------------------------------------------
# 设置后二维码内容为 {QR_BASE_URL}/trace?code=xxx，便于消费者用微信/H5 扫码查看；
# 留空则二维码内容就是溯源码本身，由小程序「扫一扫」解析。
QR_BASE_URL = os.environ.get("QR_BASE_URL", "").strip()


# ---------------------------------------------------------------------------
# 天气联动（Open-Meteo，免 Key）
# ---------------------------------------------------------------------------
def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, str(default)).strip())
    except ValueError:
        return default


# 0 / false / no / off 关闭；关闭后待办里不会出现天气预警，也不发外网请求。
WEATHER_ENABLED = os.environ.get("WEATHER_ENABLED", "1").strip().lower() not in (
    "0", "false", "no", "off",
)
WEATHER_LAT = _env_float("WEATHER_LAT", 23.55)
WEATHER_LON = _env_float("WEATHER_LON", 113.58)
WEATHER_LOCATION = os.environ.get("WEATHER_LOCATION", "广东省广州市从化区").strip()
WEATHER_TIMEOUT = _env_float("WEATHER_TIMEOUT", 3.0)
