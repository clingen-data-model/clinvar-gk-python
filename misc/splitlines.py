import argparse
import contextlib
import gzip
import os
import shutil
import sys


def split(input_filename, output_directory, partitions):
    with gzip.open(input_filename, "rt", encoding="utf-8") as f:
        filenames = [f"part-{i}.ndjson.gz" for i in range(partitions)]
        file_paths = [
            os.path.join(output_directory, filename) for filename in filenames
        ]
        with contextlib.ExitStack() as stack:
            files = [
                stack.enter_context(gzip.open(file_path, "wt"))
                for file_path in file_paths
            ]
            for i, line in enumerate(f):
                file_idx = i % partitions
                files[file_idx].write(line)


def main(args=sys.argv[1:]):
    parser = argparse.ArgumentParser()
    parser.add_argument("input_filename")
    parser.add_argument("output_directory")
    parser.add_argument("partitions", type=int)
    args = parser.parse_args(args)

    if os.path.exists(args.output_directory):
        shutil.rmtree(args.output_directory)
    os.makedirs(args.output_directory, exist_ok=True)

    return split(args.input_filename, args.output_directory, args.partitions)


if __name__ == "__main__":
    main()
