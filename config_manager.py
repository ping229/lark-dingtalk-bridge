import json
import os

CONFIG_FILE = "config.json"

DEFAULT_CONFIG = {
    "lark": {
        "verification_token": "",
        "encrypt_key": "",
        "callback_url": ""
    },
    "dingtalk": {
        "webhook_url": "",
        "secret": "",
        "keyword_prefix": "[飞书消息] "
    },
    "filter": {
        "block_list": []      # 存储要屏蔽的飞书用户 open_id 列表
    },
    "server": {
        "host": "0.0.0.0",
        "port": 5000,
        "debug": False
    }
}

class ConfigManager:
    def __init__(self, config_file=CONFIG_FILE):
        self.config_file = config_file
        self.config = self.load_config()

    def load_config(self):
        if os.path.exists(self.config_file):
            with open(self.config_file, 'r', encoding='utf-8') as f:
                saved = json.load(f)
                # 确保所有默认字段存在
                for section in DEFAULT_CONFIG:
                    if section not in saved:
                        saved[section] = DEFAULT_CONFIG[section]
                    else:
                        for key in DEFAULT_CONFIG[section]:
                            if key not in saved[section]:
                                saved[section][key] = DEFAULT_CONFIG[section][key]
                return saved
        else:
            self.save_config(DEFAULT_CONFIG)
            return DEFAULT_CONFIG.copy()

    def save_config(self, config=None):
        if config is None:
            config = self.config
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=4, ensure_ascii=False)

    def get(self, key, default=None):
        keys = key.split('.')
        value = self.config
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default
        return value if value is not None else default

    def set(self, key, value):
        keys = key.split('.')
        target = self.config
        for k in keys[:-1]:
            target = target.setdefault(k, {})
        target[keys[-1]] = value
        self.save_config()

    def reload(self):
        self.config = self.load_config()
