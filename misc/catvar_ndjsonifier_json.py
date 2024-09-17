import csv
import gzip
import json
import os
import sys
import time

from clinvar_gk_pilot.gcs import (
    _local_file_path_for,
    download_to_local_file,
    list_blobs,
)

# json (standard library)
# python3.12 misc/catvar_ndjsonifier_json.py  677.53s user 2.35s system 99% cpu 11:25.62 total
# orjson
# python3.12 misc/catvar_ndjsonifier_json.py  429.97s user 2.33s system 98% cpu 7:17.41 total


def to_json(x):
    return json.dumps(x).encode("utf-8")


def from_json(x: bytes):
    return json.loads(x.decode("utf-8"))


# import orjson
# def to_json(x):
#     return orjson.dumps(x)
# def from_json(x: bytes):
#     return orjson.loads(x)

# increase csv field size limit
csv.field_size_limit(sys.maxsize)

bucket_name = "clinvar-gk-pilot"

folder_path = "2024-09-08/stage/scv_out/json/"
output_file_name = "combined-scv_output.ndjson.gz"

blob_uris = list_blobs(bucket_name, folder_path)
blob_uris = [blob for blob in blob_uris if not blob.endswith("/")]
# for blob in blob_uris:
#     print(blob)
local_paths = []
# Download all files
print("Downloading files...")
expected_local_paths = [_local_file_path_for(blob) for blob in blob_uris]
for expected_local_path, blob_uri in zip(expected_local_paths, blob_uris):
    if not os.path.exists(expected_local_path):
        local_paths.append(download_to_local_file(blob_uri))
    else:
        local_paths.append(expected_local_path)

output_lines_count = 0
last_logged_output_count_time = time.time()
last_logged_output_count_value = 0


with gzip.open(output_file_name, "wb", compresslevel=9) as f_out:
    for file_idx, file_path in enumerate(local_paths):
        print(f"Reading {file_path} ({file_idx + 1}/{len(local_paths)})...")
        try:
            with gzip.open(file_path, "rb") as f_in:
                for line in f_in:
                    rec = from_json(line)
                    rec = rec["rec"]
                    ks = list(rec.keys())
                    if len(ks) != 1:
                        raise ValueError(
                            "Record did not contain exactly 1 key: " + line
                        )
                    value = rec[ks[0]]

                    f_out.write(to_json(value))
                    f_out.write(b"\n")

                    output_lines_count += 1
                    now = time.time()
                    if now - last_logged_output_count_time > 5:
                        new_lines = output_lines_count - last_logged_output_count_value
                        print(
                            f"Outputs written: {output_lines_count} ({new_lines/5:.2f} lines/s)"
                        )
                        last_logged_output_count_value = output_lines_count
                        last_logged_output_count_time = now
        except Exception as e:
            print(f"Exception while reading {file_path}: {e}")
            raise e

print(f"Wrote {output_file_name} successfully!")
