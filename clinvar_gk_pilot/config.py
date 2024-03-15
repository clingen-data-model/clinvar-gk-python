import os
import pathlib

from dotenv import dotenv_values

seqrepo_dataproxy_key = "SEQREPO_DATAPROXY_URL"

_dotenv_env = os.environ.get("DOTENV_ENV", "dev")
_dotenv_values = dotenv_values(pathlib.Path(__file__).parent / f".{_dotenv_env}.env")


def get_env():
    proxy = os.getenv(seqrepo_dataproxy_key) or _dotenv_values.get(seqrepo_dataproxy_key)
    return {seqrepo_dataproxy_key: proxy}
