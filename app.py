import logging
from flask import Flask, request, jsonify, render_template_string
from config_manager import ConfigManager
from dingtalk_sender import DingTalkSender
from lark_handler import LarkHandler
import requests as http_requests
from datetime import datetime
from collections import deque

app = Flask(__name__)
config = ConfigManager()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 存储最近的消息（最多 20 条）
recent_messages = deque(maxlen=20)

def get_public_ip():
    try:
        ip = http_requests.get('https://api.ipify.org', timeout=3).text
        return ip
    except:
        return "YOUR_SERVER_IP"

def forward_to_dingtalk(text, sender_open_id, sender_name):
    """转发消息到钉钉，并在转发前检查黑名单"""
    block_list = config.get('filter.block_list', [])
    if sender_open_id in block_list:
        logger.info(f"消息被过滤: 发送者 {sender_open_id} 在黑名单中，不转发。")
        # 仍然记录到最近消息（但标注已过滤）
        recent_messages.append({
            'timestamp': datetime.now().strftime('%H:%M:%S'),
            'open_id': sender_open_id,
            'text': text[:100],
            'blocked': True
        })
        return

    dt_cfg = config.get('dingtalk')
    if not dt_cfg.get('webhook_url'):
        logger.warning("钉钉 Webhook 未配置，跳过发送")
        return

    sender_obj = DingTalkSender(
        webhook_url=dt_cfg['webhook_url'],
        secret=dt_cfg.get('secret') or None,
        keyword_prefix=dt_cfg.get('keyword_prefix', '')
    )
    display_name = sender_name if sender_name != sender_open_id else sender_open_id
    formatted_msg = f"📨 来自飞书 [{display_name}]: {text}"
    result = sender_obj.send_text(formatted_msg, sender=display_name)
    logger.info(f"转发消息: {formatted_msg} -> 钉钉响应: {result}")

    # 记录到最近消息
    recent_messages.append({
        'timestamp': datetime.now().strftime('%H:%M:%S'),
        'open_id': sender_open_id,
        'text': text[:100],
        'blocked': False
    })

@app.route('/webhook', methods=['POST'])
def lark_webhook():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "empty body"}), 400

        lark_cfg = config.get('lark')
        handler = LarkHandler(
            verification_token=lark_cfg.get('verification_token', ''),
            encrypt_key=lark_cfg.get('encrypt_key') or None
        )
        result = handler.parse_event(data)

        if result and 'challenge' in result:
            return jsonify({"challenge": result['challenge']})

        if result and result.get('type') == 'message':
            text = result.get('text', '')
            sender_open_id = result.get('sender_open_id', 'unknown')
            sender_name = result.get('sender_name', sender_open_id)
            if text.strip():
                forward_to_dingtalk(text, sender_open_id, sender_name)

        return jsonify({"code": 0, "msg": "success"})
    except Exception as e:
        logger.exception("Webhook 处理错误")
        return jsonify({"error": str(e)}), 500

# ---------- Web 管理界面（内嵌 HTML，新增实时消息监控） ----------
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>飞书 ↔ 钉钉 消息桥接</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 40px; background: #f0f2f5; }
        .container { max-width: 1200px; margin: auto; background: white; padding: 25px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        .card { border: 1px solid #ddd; border-radius: 8px; padding: 20px; margin-bottom: 25px; background: #fafbfc; }
        .card h2 { margin-top: 0; color: #333; font-size: 1.4em; }
        .row { margin-bottom: 15px; }
        label { display: inline-block; width: 180px; font-weight: bold; vertical-align: top; margin-top: 8px; }
        input, textarea { width: calc(100% - 200px); padding: 8px; border: 1px solid #ccc; border-radius: 4px; }
        .readonly-input { background: #e9ecef; cursor: not-allowed; }
        button { background: #007bff; color: white; border: none; padding: 10px 20px; border-radius: 5px; cursor: pointer; margin-right: 10px; }
        button:hover { background: #0056b3; }
        .status { background: #d4edda; color: #155724; padding: 10px; border-radius: 5px; margin-bottom: 20px; }
        .test-area { margin-top: 20px; padding-top: 20px; border-top: 1px solid #ddd; }
        table { width: 100%; border-collapse: collapse; }
        th, td { text-align: left; padding: 8px; border-bottom: 1px solid #ddd; }
        th { background-color: #f2f2f2; }
        .block-btn { background-color: #dc3545; color: white; border: none; padding: 4px 8px; border-radius: 4px; cursor: pointer; font-size: 12px; }
        .block-btn:hover { background-color: #c82333; }
        .already-blocked { color: #6c757d; font-style: italic; }
        .message-row { font-family: monospace; }
    </style>
    <script>
        let refreshInterval = null;

        function loadConfig() {
            fetch('/api/config')
                .then(res => res.json())
                .then(cfg => {
                    document.getElementById('lark_token').value = cfg.lark.verification_token || '';
                    document.getElementById('lark_encrypt').value = cfg.lark.encrypt_key || '';
                    document.getElementById('dingtalk_webhook').value = cfg.dingtalk.webhook_url || '';
                    document.getElementById('dingtalk_secret').value = cfg.dingtalk.secret || '';
                    document.getElementById('dingtalk_keyword').value = cfg.dingtalk.keyword_prefix || '';
                    let blockList = cfg.filter?.block_list || [];
                    document.getElementById('block_list').value = blockList.join('\\n');
                    document.getElementById('status').innerHTML = '✅ 配置已加载';
                    // 刷新黑名单显示
                    displayBlockList(blockList);
                })
                .catch(err => { document.getElementById('status').innerHTML = '❌ 加载失败: ' + err; });
        }

        function displayBlockList(blockList) {
            const container = document.getElementById('current_block_list');
            if (!blockList.length) {
                container.innerHTML = '<span class="already-blocked">暂无屏蔽用户</span>';
                return;
            }
            let html = '<ul>';
            blockList.forEach(open_id => {
                html += `<li><code>${open_id}</code> <button class="block-btn" onclick="removeFromBlacklist('${open_id}')">移除</button></li>`;
            });
            html += '</ul>';
            container.innerHTML = html;
        }

        function saveConfig() {
            let blockListRaw = document.getElementById('block_list').value;
            let blockList = blockListRaw.split('\\n').filter(line => line.trim().length > 0);

            const config = {
                lark: {
                    verification_token: document.getElementById('lark_token').value,
                    encrypt_key: document.getElementById('lark_encrypt').value
                },
                dingtalk: {
                    webhook_url: document.getElementById('dingtalk_webhook').value,
                    secret: document.getElementById('dingtalk_secret').value,
                    keyword_prefix: document.getElementById('dingtalk_keyword').value
                },
                filter: {
                    block_list: blockList
                }
            };
            fetch('/api/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(config)
            })
            .then(res => res.json())
            .then(data => {
                alert('配置已���存');
                loadConfig();
            })
            .catch(err => alert('保存失败: ' + err));
        }

        function testDingTalk() {
            const msg = document.getElementById('test_msg_content').value;
            if (!msg) { alert('请输入测试消息内容'); return; }
            fetch('/api/test_dingtalk', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: msg })
            })
            .then(res => res.json())
            .then(data => alert('发送结果: ' + JSON.stringify(data)))
            .catch(err => alert('测试失败: ' + err));
        }

        function loadRecentMessages() {
            fetch('/api/recent_messages')
                .then(res => res.json())
                .then(data => {
                    const tbody = document.getElementById('messages_tbody');
                    tbody.innerHTML = '';
                    data.messages.forEach(msg => {
                        const row = tbody.insertRow();
                        row.className = 'message-row';
                        row.insertCell(0).innerText = msg.timestamp;
                        row.insertCell(1).innerText = msg.open_id;
                        row.insertCell(2).innerText = msg.text;
                        const actionCell = row.insertCell(3);
                        if (msg.blocked) {
                            actionCell.innerText = '已屏蔽';
                            actionCell.className = 'already-blocked';
                        } else {
                            const btn = document.createElement('button');
                            btn.innerText = '加入黑名单';
                            btn.className = 'block-btn';
                            btn.onclick = () => addToBlacklist(msg.open_id);
                            actionCell.appendChild(btn);
                        }
                    });
                })
                .catch(err => console.error('加载消息失败:', err));
        }

        function addToBlacklist(open_id) {
            fetch('/api/add_to_blacklist', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ open_id: open_id })
            })
            .then(res => res.json())
            .then(data => {
                alert(`已添加 ${open_id} 到黑名单`);
                loadConfig();  // 刷新配置
                loadRecentMessages(); // 刷新消息列表，按钮可能变为“已屏蔽”
            })
            .catch(err => alert('添加失败: ' + err));
        }

        function removeFromBlacklist(open_id) {
            // 从当前黑名单中移除
            let current = document.getElementById('block_list').value.split('\\n').filter(l => l.trim());
            const newList = current.filter(id => id !== open_id);
            document.getElementById('block_list').value = newList.join('\\n');
            saveConfig(); // 保存后会自动刷新黑名单显示
        }

        window.onload = () => {
            loadConfig();
            loadRecentMessages();
            refreshInterval = setInterval(loadRecentMessages, 3000);
        };
        window.onbeforeunload = () => {
            if (refreshInterval) clearInterval(refreshInterval);
        };
    </script>
</head>
<body>
<div class="container">
    <h1>📡 飞书 ↔ 钉钉 消息桥接</h1>
    <div class="status" id="status">正在加载配置...</div>

    <div class="card">
        <h2>🎤 飞书配置（HTTP 回调模式）</h2>
        <div class="row">
            <label>回调 URL（公网）:</label>
            <input type="text" id="callback_url" class="readonly-input" readonly value="http://{{ public_ip }}:5000/webhook">
            <small style="display:block; margin-left:180px;">请将此地址填入飞书后台「事件配置」和「回调配置」的请求地址</small>
        </div>
        <div class="row">
            <label>Verification Token:</label>
            <input type="text" id="lark_token" placeholder="从飞书后台复制">
        </div>
        <div class="row">
            <label>Encrypt Key（可选）:</label>
            <textarea id="lark_encrypt" rows="2" placeholder="如非必要，请留空（本服务不支持加密）"></textarea>
            <small style="display:block; margin-left:180px;">⚠️ 请务必在飞书后台关闭加密（Encrypt Key留空）</small>
        </div>
    </div>

    <div class="card">
        <h2>📢 钉钉配置</h2>
        <div class="row">
            <label>Webhook URL:</label>
            <input type="text" id="dingtalk_webhook" placeholder="https://oapi.dingtalk.com/robot/send?access_token=xxx">
        </div>
        <div class="row">
            <label>加签 Secret（可选）:</label>
            <textarea id="dingtalk_secret" rows="2" placeholder="如果钉钉设置了加签，填写此密钥"></textarea>
        </div>
        <div class="row">
            <label>自定义关键词前缀:</label>
            <input type="text" id="dingtalk_keyword" placeholder="例如 [飞书消息] ">
            <small style="display:block; margin-left:180px;">每条飞书消息会加上此前缀，请将此关键词加入钉钉机器人的安全设置</small>
        </div>
    </div>

    <div class="card">
        <h2>⚙️ 消息过滤（黑名单）</h2>
        <div class="row">
            <label>屏蔽用户 Open ID:</label>
            <textarea id="block_list" rows="4" placeholder="每行一个 open_id，例如：&#10;ou_f18326913799f709cd7aca4a8d34a5df"></textarea>
            <small style="display:block; margin-left:180px;">列表中的用户发送的消息将不会被转发到钉钉。</small>
        </div>
        <div class="row">
            <label>当前黑名单:</label>
            <div id="current_block_list" style="display:inline-block; width:calc(100% - 200px); padding:8px; background:#e9ecef; border-radius:4px;">
                加载中...
            </div>
        </div>
    </div>

    <div>
        <button onclick="saveConfig()">💾 保存全部配置</button>
        <button onclick="testDingTalk()">🧪 测试钉钉发送</button>
    </div>

    <div class="card">
        <h2>📋 实时消息监控（最近20条）</h2>
        <table>
            <thead>
                <tr><th>时间</th><th>Open ID</th><th>消息内容</th><th>操作</th></tr>
            </thead>
            <tbody id="messages_tbody">
                <tr><td colspan="4">加载中...</td></tr>
            </tbody>
        </table>
        <small>消息自动刷新，点击“加入黑名单”可直接屏蔽该用户。</small>
    </div>

    <div class="test-area">
        <h3>📨 手动发送测试消息到钉钉</h3>
        <input type="text" id="test_msg_content" placeholder="输入测试消息" style="width: 70%;">
        <button onclick="testDingTalk()">发送测试消息</button>
    </div>
</div>
</body>
</html>
'''

@app.route('/')
def index():
    public_ip = get_public_ip()
    config.set('lark.callback_url', f"http://{public_ip}:{config.get('server.port')}/webhook")
    return render_template_string(HTML_TEMPLATE, public_ip=public_ip)

@app.route('/api/config', methods=['GET'])
def get_config():
    return jsonify(config.config)

@app.route('/api/config', methods=['POST'])
def update_config():
    new_cfg = request.get_json()
    for section in ['lark', 'dingtalk', 'filter']:
        if section in new_cfg:
            for key, value in new_cfg[section].items():
                config.set(f"{section}.{key}", value)
    return jsonify({"status": "ok"})

@app.route('/api/test_dingtalk', methods=['POST'])
def test_dingtalk():
    data = request.get_json()
    msg = data.get('message', '')
    if not msg:
        return jsonify({"error": "消息不能为空"}), 400
    dt_cfg = config.get('dingtalk')
    if not dt_cfg.get('webhook_url'):
        return jsonify({"error": "钉钉 Webhook 未配置"}), 400
    sender = DingTalkSender(
        webhook_url=dt_cfg['webhook_url'],
        secret=dt_cfg.get('secret') or None,
        keyword_prefix=dt_cfg.get('keyword_prefix', '')
    )
    result = sender.send_text(msg, sender="测试用户")
    return jsonify(result)

# ---------- 新增 API：获取最近消息 ----------
@app.route('/api/recent_messages', methods=['GET'])
def get_recent_messages():
    return jsonify({"messages": list(recent_messages)})

# ---------- 新增 API：添加 open_id 到黑名单 ----------
@app.route('/api/add_to_blacklist', methods=['POST'])
def add_to_blacklist():
    data = request.get_json()
    open_id = data.get('open_id')
    if not open_id:
        return jsonify({"error": "missing open_id"}), 400
    block_list = config.get('filter.block_list', [])
    if open_id not in block_list:
        block_list.append(open_id)
        config.set('filter.block_list', block_list)
    return jsonify({"status": "ok", "open_id": open_id})

if __name__ == '__main__':
    srv_cfg = config.get('server')
    app.run(host=srv_cfg.get('host', '0.0.0.0'),
            port=srv_cfg.get('port', 5000),
            debug=srv_cfg.get('debug', False),
            threaded=True)
