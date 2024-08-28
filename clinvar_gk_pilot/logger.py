import json
import logging.config
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

with open(PROJECT_ROOT / "log_conf.json", "r", encoding="utf-8") as f:
    conf = json.load(f)
    logging.config.dictConfig(conf)

logger = logging.getLogger("clinvar_gk_pilot")
