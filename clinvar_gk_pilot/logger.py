import json
import logging.config

with open("log_conf.json", "r") as f:
    conf = json.load(f)
    logging.config.dictConfig(conf)

logger = logging.getLogger("clinvar_gk_pilot")
