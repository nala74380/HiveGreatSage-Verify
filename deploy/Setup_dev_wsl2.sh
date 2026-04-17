#!/bin/bash
# ==============================================================
# HiveGreatSage-Verify — WSL2 + Ubuntu 24.04 开发环境搭建脚本
# 使用方法：chmod +x deploy/setup_dev_wsl2.sh && ./deploy/setup_dev_wsl2.sh
# 预计耗时：10-15 分钟（首次安装）
# ==============================================================

set -e  # 任一命令失败立即退出

echo "======================================"
echo " HiveGreatSage-Verify 开发环境搭建"
echo " WSL2 + Ubuntu 24.04"
echo "======================================"

# ── 1. 更新系统包 ─────────────────────────────────────────────
echo ""
echo "[1/6] 更新系统包..."
sudo apt update && sudo apt upgrade -y

# ── 2. 安装 Python 3.11 + pip + venv ─────────────────────────
echo ""
echo "[2/6] 安装 Python 3.11..."
sudo apt install -y python3.11 python3.11-venv python3.11-dev python3-pip

# 确认版本
python3.11 --version

# ── 3. 安装 PostgreSQL ────────────────────────────────────────
echo ""
echo "[3/6] 安装 PostgreSQL..."
sudo apt install -y postgresql postgresql-contrib

# 启动 PostgreSQL 服务
sudo service postgresql start

# 创建数据库用户和主库
echo "创建数据库用户 hive_user 和主库 hive_platform..."
sudo -u postgres psql << 'EOF'
DO $$
BEGIN
   IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'hive_user') THEN
      CREATE USER hive_user WITH PASSWORD 'hive_dev_password_2026';
   END IF;
END
$$;

CREATE DATABASE hive_platform OWNER hive_user;
GRANT ALL PRIVILEGES ON DATABASE hive_platform TO hive_user;
EOF

echo "✅ PostgreSQL 配置完成"
echo "   用户: hive_user"
echo "   密码: hive_dev_password_2026（开发环境，生产环境必须修改）"
echo "   主库: hive_platform"

# ── 4. 安装 Redis ─────────────────────────────────────────────
echo ""
echo "[4/6] 安装 Redis..."
sudo apt install -y redis-server

# 启动 Redis
sudo service redis-server start

# 验证 Redis 可用
redis-cli ping && echo "✅ Redis 运行正常" || echo "❌ Redis 启动失败，请手动检查"

# ── 5. 创建 Python 虚拟环境并安装依赖 ─────────────────────────
echo ""
echo "[5/6] 创建虚拟环境并安装 Python 依赖..."

# 在项目根目录创建 venv
python3.11 -m venv venv
source venv/bin/activate

pip install --upgrade pip
pip install -r requirements.txt

echo "✅ Python 依赖安装完成"

# ── 6. 初始化配置文件 ─────────────────────────────────────────
echo ""
echo "[6/6] 初始化配置文件..."

if [ ! -f ".env" ]; then
    cp .env.example .env
    # 自动替换数据库密码为开发环境默认值
    sed -i 's|postgresql+asyncpg://hive_user:password@|postgresql+asyncpg://hive_user:hive_dev_password_2026@|g' .env
    # 生成随机 SECRET_KEY
    RANDOM_KEY=$(python3.11 -c "import secrets; print(secrets.token_hex(32))")
    sed -i "s|change-this-to-a-random-32-byte-string-in-production|${RANDOM_KEY}|g" .env
    echo "✅ .env 文件已创建（SECRET_KEY 已自动生成随机值）"
else
    echo "⚠️  .env 文件已存在，跳过创建"
fi

# ── 7. 初始化数据库（Alembic）─────────────────────────────────
echo ""
echo "运行数据库迁移（建表）..."
alembic upgrade head && echo "✅ 数据库迁移完成" || echo "❌ 迁移失败，请检查数据库连接"

# ── 完成 ──────────────────────────────────────────────────────
echo ""
echo "======================================"
echo " ✅ 开发环境搭建完成！"
echo "======================================"
echo ""
echo "启动服务："
echo "  source venv/bin/activate"
echo "  uvicorn app.main:app --reload --host 0.0.0.0 --port 8000"
echo ""
echo "访问 API 文档："
echo "  http://localhost:8000/docs"
echo ""
echo "PyCharm 配置提示："
echo "  Python 解释器 → 选择 ./venv/bin/python3.11"
echo "  运行配置 → Script: uvicorn, 参数: app.main:app --reload"
echo ""
echo "WSL2 + Windows 访问提示："
echo "  Windows 浏览器访问：http://localhost:8000/docs（WSL2 端口自动转发）"
echo "  若无法访问，在 Windows PowerShell 执行："
echo "    netsh interface portproxy add v4tov4 listenport=8000 connectaddress=\$(wsl hostname -I | awk '{print \$1}') connectport=8000"