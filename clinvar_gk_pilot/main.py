import argparse
import json
import logging
import sys
from typing import List

import requests

with open("log_conf.json", "r") as f:
    conf = json.load(f)
    logging.config.dictConfig(conf)


def parse_args(args: List[str]) -> dict:
    """
    Parse arguments and return as dict
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--filename", required=True, help="Filename to read")

    return vars(parser.parse_args(args))


def process_line(record: dict, opts: dict) -> dict:
    """
    Process one line and return normalized variation.

    Args:
        record (dict): The input record containing variation information.
        opts (dict): Additional options for processing.

    Returns:
        dict: The normalized variation.

    Raises:
        RuntimeError: If the response status is not 200 or if the response has errors.

    """
    print("in process_line")

    def validate_response(resp):
        if resp.status_code != 200:
            raise RuntimeError("Response status was not 200: " + str(vars(resp)))
        j = json.loads(resp.text)
        if len(j.get("errors", [])) > 0:
            raise RuntimeError("Response had errors: " + str(j))
        return j

    var = None
    if "canonical_spdi" in record:
        print("process_line got a canonical_spdi")
        url = opts["normalizer_url"] + "/translate_from"
        resp = requests.get(
            url,
            params={"variation": record["canonical_spdi"], "fmt": "spdi"},
            headers={"Accept": "application/json"},
            timeout=30,
        )
        obj = validate_response(resp)
        var = obj["variation"]
    print("returning from process_line")
    return var


def main(argv=sys.argv):
    pass
