# HiveGreatSage-Verify

蜂巢·大圣平台 - 网络验证系统（中枢）

## 快速开始

1. 创建虚拟环境：`python -m venv venv`
2. 激活环境并安装依赖：`pip install -r requirements.txt`
3. 复制 `.env.example` 为 `.env` 并填入真实配置
4. 初始化数据库：`alembic upgrade head`
5. 启动服务：`uvicorn app.main:app --reload`

访问 http://127.0.0.1:8000/docs 查看 API 文档。
