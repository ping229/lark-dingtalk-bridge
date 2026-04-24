#!/bin/bash
set -e

INSTALL_DIR="/opt/lark-bridge"
SERVICE_NAME="lark_bridge"

echo "=== 自动部署飞书↔钉钉消息桥接服务 ==="

# 1. 安装系统依赖
echo ">>> 安装系统依赖..."
if command -v yum &> /dev/null; then
    yum install -y python3 python3-pip
elif command -v apt &> /dev/null; then
    apt update && apt install -y python3 python3-pip
fi

# 2. 安装 Python 依赖
echo ">>> 安装 Python 依赖..."
pip3 install flask requests

# 3. 创建目录
echo ">>> 创建项目目录 $INSTALL_DIR"
mkdir -p $INSTALL_DIR
cd $INSTALL_DIR

# 4. 复制当前目录下的所有 .py 文件到安装目录
# 如果当前目录已经有文件（比如通过 git clone 得到的），直接复制
cp -f *.py . 2>/dev/null || true

# 5. 创建 systemd 服务
echo ">>> 创建 systemd 服务"
cat > /etc/systemd/system/$SERVICE_NAME.service << 'SERVICE_EOF'
[Unit]
Description=Lark to DingTalk Bridge
After=network.target

[Service]
User=root
WorkingDirectory=/opt/lark-bridge
ExecStart=/usr/bin/python3 /opt/lark-bridge/app.py
Restart=always
RestartSec=10
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
SERVICE_EOF

systemctl daemon-reload
systemctl enable $SERVICE_NAME
systemctl restart $SERVICE_NAME

# 6. 开放防火墙端口
if command -v firewall-cmd &> /dev/null; then
    firewall-cmd --permanent --add-port=5000/tcp
    firewall-cmd --reload
    echo ">>> 防火墙已开放 5000 端口"
fi

# 7. 获取公网 IP 并输出完成信息
PUBLIC_IP=$(curl -s ifconfig.me)
echo "========================================="
echo "✅ 部署完成！"
echo "🌐 访问管理后台: http://${PUBLIC_IP}:5000"
echo "💡 请完成以下配置："
echo "    1. 在飞书后台填写 Verification Token 和回调 URL（页面已显示）"
echo "    2. 在页面中填写钉钉的 Webhook 和关键词"
echo "    3. 在页面中屏蔽不需要转发的用户"
echo "========================================="
