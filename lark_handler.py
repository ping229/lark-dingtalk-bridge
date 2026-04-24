import json
import logging

logger = logging.getLogger(__name__)

class LarkHandler:
    def __init__(self, verification_token, encrypt_key=None):
        self.verification_token = verification_token
        if encrypt_key:
            logger.warning("encrypt_key provided but not supported. Please disable encryption in Feishu.")

    def parse_event(self, request_json):
        # 1. 处理 URL 验证
        if request_json.get('type') == 'url_verification':
            return {'challenge': request_json.get('challenge')}

        # 2. 加密事件不支持
        if 'encrypt' in request_json:
            raise ValueError("Encrypted event received. Please disable Encrypt Key in Feishu.")

        # 3. 兼容 v2.0 事件格式（header + event）
        header = request_json.get('header')
        event = request_json.get('event')
        if header and event:
            received_token = header.get('token')
            event_type = header.get('event_type')
        else:
            # 兼容旧版格式
            received_token = request_json.get('token')
            event_type = request_json.get('event', {}).get('type')

        # 4. 校验 token
        if received_token is None:
            logger.error(f"Missing token in request. Full request: {json.dumps(request_json)}")
            raise ValueError("Missing token in request. Please ensure Feishu event subscription uses v2.0 and Encrypt Key is empty.")

        if received_token != self.verification_token:
            raise ValueError(f"Token mismatch: '{received_token}' != '{self.verification_token}'")

        # 5. 解析消息事件 im.message.receive_v1
        if event_type == 'im.message.receive_v1':
            message = event.get('message', {})
            content_str = message.get('content', '{}')
            try:
                content = json.loads(content_str)
                text = content.get('text', '')
            except:
                text = ''

            # 提取发送者 open_id
            sender_open_id = event.get('sender', {}).get('sender_id', {}).get('open_id', 'unknown')
            # 可选：提取发送者姓名（需要额外 API，这里暂不实现）
            sender_name = sender_open_id  # 默认用 open_id 作为名称

            return {
                'type': 'message',
                'text': text,
                'sender_open_id': sender_open_id,
                'sender_name': sender_name,
                'raw': event
            }
        return None
