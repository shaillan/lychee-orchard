"""一键启动：python run.py
服务地址：http://127.0.0.1:8000
  /           果农端（移动端 H5）
  /dashboard  农事数据看板
  /trace      品质溯源（可 ?code=LZ-P03-20260702-0001）
  /docs       FastAPI 接口文档
"""
import os
import sys

# 兼容：本机 Python（E:\\python.exe）在部分工作目录下 site-packages 会从
# sys.path 中丢失，这里显式补回，确保无论从哪个目录启动都能 import 依赖。
_site = os.path.join(os.path.dirname(os.path.abspath(sys.executable)), "Lib", "site-packages")
if _site not in sys.path:
    sys.path.insert(0, _site)

import uvicorn  # noqa: E402

if __name__ == "__main__":
    # 真机预览小程序时用 HOST=0.0.0.0 启动，手机通过电脑局域网 IP 访问。
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8000"))
    if host == "0.0.0.0":
        print(f"服务已监听 0.0.0.0:{port}，小程序真机预览请使用 http://<电脑局域网IP>:{port}")
    uvicorn.run("backend.main:app", host=host, port=port, reload=False)
