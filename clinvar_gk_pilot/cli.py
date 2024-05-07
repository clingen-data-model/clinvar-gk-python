import argparse
from typing import List


def parse_args(args: List[str]) -> dict:
    """
    Parse arguments and return as dict.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--filename", required=True, help="Filename to read")
    parser.add_argument(
        "--parallelism",
        type=int,
        default=1,
        help=(
            "Number of worker threads. "
            "Default 1, which still uses a separate process to run tasks. "
            "Set to 0 to run in main thread."
        ),
    )
    return vars(parser.parse_args(args))
