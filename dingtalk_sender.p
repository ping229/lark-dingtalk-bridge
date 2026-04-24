import time
import hmac
import hashlib
import base64
import requests

class DingTalkSender:
    def __init__(self, webhook_url, secret=None, keyword_prefix=""):
        self.webhook_url = webhook_url
        self.secret = secret
        self.keyword_prefix = keyword_prefix

    def _sign(self, timestamp):
        if not self.secret:
            return None
        secret_enc = self.secret.encode('utf-8')
        string_to_sign = f"{timestamp}\n{self.secret}"
        string_to_sign_enc = string_to_sign.encode('utf-8')
        hmac_code = hmac.new(secret_enc, string_to_sign_enc, digestmod=hashlib.sha256).digest()
        sign = base64.b64encode(hmac_code).decode('utf-8')
        return sign

    def send_text(self, text, sender="未知用户", at_mobiles=None, is_at_all=False):
        full_text = self.keyword_prefix + text
        timestamp = str(round(time.time() * 1000))
        sign = self._sign(timestamp)
        url = self.webhook_url
        if sign:
            url = f"{url}&timestamp={timestamp}&sign={sign}"

        headers = {'Content-Type': 'application/json'}
        data = {
            "msgtype": "text",
            "text": {"content": full_text},
            "at": {"atMobiles": at_mobiles or [], "isAtAll": is_at_all}
        }
        try:
            resp = requests.post(url, headers=headers, json=data, timeout=5)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            return {"error": str(e)}
