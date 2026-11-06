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


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, str(default)).strip())
    except ValueError:
        return default

# ---------------------------------------------------------------------------
# 病虫害识别
# ---------------------------------------------------------------------------
# auto：有云端 Key 走云端视觉 API，其次自定义 VISION_API_URL，最后本地模拟
# api / dashscope：OpenAI 兼容的云端视觉接口（智谱 GLM / 通义千问 / 豆包 / 硅基流动…）
# custom / mock：强制指定
VISION_PROVIDER = os.environ.get("VISION_PROVIDER", "auto").strip().lower()

# 兼容旧变量名：DASHSCOPE_* 仍可用，新配置建议写 VISION_*
DASHSCOPE_API_KEY = os.environ.get("DASHSCOPE_API_KEY", "").strip()
DASHSCOPE_BASE_URL = os.environ.get("DASHSCOPE_BASE_URL", "").strip()

_ZHIPU_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
_DASHSCOPE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"

VISION_API_KEY = os.environ.get("VISION_API_KEY", "").strip() or DASHSCOPE_API_KEY

# 端点优先级：VISION_BASE_URL > 旧 DASHSCOPE_BASE_URL > 按旧 Key 推断 > 智谱（默认免费）
if os.environ.get("VISION_BASE_URL", "").strip():
    VISION_BASE_URL = os.environ["VISION_BASE_URL"].strip()
elif DASHSCOPE_BASE_URL:
    VISION_BASE_URL = DASHSCOPE_BASE_URL
elif DASHSCOPE_API_KEY:
    VISION_BASE_URL = _DASHSCOPE_URL
else:
    VISION_BASE_URL = _ZHIPU_URL

# 模型名留空时按端点自动选：智谱 → glm-4.1v-thinking-flash（免费），其余 → qwen-vl-plus
_DEFAULT_MODEL = "glm-4.1v-thinking-flash" if "bigmodel" in VISION_BASE_URL else "qwen-vl-plus"
VISION_MODEL = os.environ.get("VISION_MODEL", "").strip() or _DEFAULT_MODEL

# 备选模型：主模型限流/不可用时自动切换（免费档 1305 很常见），留空则不切换
VISION_FALLBACK_MODEL = os.environ.get("VISION_FALLBACK_MODEL", "").strip()

# 图片传参格式：data_uri（默认，带 data:image/jpeg;base64, 前缀）| raw（纯 base64，个别网关要求）
VISION_IMAGE_FORMAT = os.environ.get("VISION_IMAGE_FORMAT", "data_uri").strip().lower()
VISION_TIMEOUT = _env_float("VISION_TIMEOUT", 45.0)

# 二次确认：首轮识别为病虫害后，再用同一模型复核图中是否真有该症状。
# 未通过严格降级为「无法判断」；复核调用失败则保留首轮结果（fail-open）。
VISION_CONFIRM = os.environ.get("VISION_CONFIRM", "1").strip().lower() not in (
    "0", "false", "no", "off",
)
VISION_CONFIRM_TIMEOUT = _env_float("VISION_CONFIRM_TIMEOUT", 12.0)

# 自定义视觉 API（约定：POST {image_base64, plot_id} -> {class, confidence, bbox}）
# 变量名与云端 VISION_API_KEY 分开，否则 auto 模式会把自定义接口误判成云端
VISION_CUSTOM_URL = os.environ.get("VISION_CUSTOM_URL", "").strip()
VISION_CUSTOM_KEY = os.environ.get("VISION_CUSTOM_KEY", "").strip()

# ---------------------------------------------------------------------------
# 一物一码
# ---------------------------------------------------------------------------
# 设置后二维码内容为 {QR_BASE_URL}/trace?code=xxx，便于消费者用微信/H5 扫码查看；
# 留空则二维码内容就是溯源码本身，由小程序「扫一扫」解析。
QR_BASE_URL = os.environ.get("QR_BASE_URL", "").strip()


# ---------------------------------------------------------------------------
# 天气联动（Open-Meteo，免 Key）
# ---------------------------------------------------------------------------
# 0 / false / no / off 关闭；关闭后待办里不会出现天气预警，也不发外网请求。
WEATHER_ENABLED = os.environ.get("WEATHER_ENABLED", "1").strip().lower() not in (
    "0", "false", "no", "off",
)
WEATHER_LAT = _env_float("WEATHER_LAT", 23.55)
WEATHER_LON = _env_float("WEATHER_LON", 113.58)
WEATHER_LOCATION = os.environ.get("WEATHER_LOCATION", "广东省广州市从化区").strip()
WEATHER_TIMEOUT = _env_float("WEATHER_TIMEOUT", 3.0)
