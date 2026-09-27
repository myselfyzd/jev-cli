"""配置与密钥解析。

优先级：命令行参数 > 配置文件 > 环境变量 > 兜底路径。
密钥只从环境变量或已有配置文件读，本工具自己写的配置里不会存密钥（除非你手动加）。
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

CONFIG_PATH = Path(os.path.expanduser("~/.config/jev-cli/config.json"))
PROJECT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_LOG_DIR = PROJECT_DIR / "logs"
DEFAULT_FIXTURES = PROJECT_DIR / "fixtures" / "labeled_set.json"
# 本机已有的 key 兜底：chat_tool 的配置文件
FALLBACK_KEY_FILES = (Path(os.path.expanduser("~/chat_tool/config.json")),)


@dataclass
class Config:
    relationship: str = "romantic partners"
    judge: str = "deepseek"          # deepseek | jev
    model: str = "deepseek-chat"
    rank: bool = True
    quiet: bool = False
    color: bool = True
    log_dir: str = str(DEFAULT_LOG_DIR)
    fixtures: str = str(DEFAULT_FIXTURES)
    deepseek_api_key: str = ""       # 一般留空，用环境变量
    openrouter_api_key: str = ""
    extra_key_files: list = field(default_factory=lambda: [str(p) for p in FALLBACK_KEY_FILES])

    def to_json(self) -> dict:
        data = asdict(self)
        for key in ("deepseek_api_key", "openrouter_api_key"):
            if data.get(key):
                data[key] = "[写在这里不会被读取，请用环境变量]"
        return data


def load_config(path: Path | None = None) -> Config:
    path = Path(path) if path else CONFIG_PATH
    cfg = Config()
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            data = {}
        if isinstance(data, dict):
            for key, value in data.items():
                if hasattr(cfg, key) and value not in (None, ""):
                    setattr(cfg, key, value)
    env = os.environ.get("DEEPSEEK_API_KEY")
    if env:
        cfg.deepseek_api_key = env.strip()
    env = os.environ.get("OPENROUTER_API_KEY")
    if env:
        cfg.openrouter_api_key = env.strip()
    return cfg


def save_config(cfg: Config, path: Path | None = None) -> Path:
    path = Path(path) if path else CONFIG_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cfg.to_json(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def resolve_deepseek_key(cfg: Config) -> str:
    if cfg.deepseek_api_key:
        return cfg.deepseek_api_key
    for candidate in cfg.extra_key_files:
        try:
            data = json.loads(Path(os.path.expanduser(str(candidate))).read_text(encoding="utf-8"))
            key = str(data["api"]["api_key"]).strip()
            if key:
                return key
        except (OSError, KeyError, TypeError, json.JSONDecodeError):
            continue
    return ""


def resolve_openrouter_key(cfg: Config) -> str:
    return cfg.openrouter_api_key or os.environ.get("OPENROUTER_API_KEY", "").strip()


__all__ = ["Config", "load_config", "save_config", "resolve_deepseek_key",
           "resolve_openrouter_key", "CONFIG_PATH", "PROJECT_DIR", "DEFAULT_LOG_DIR",
           "DEFAULT_FIXTURES"]
