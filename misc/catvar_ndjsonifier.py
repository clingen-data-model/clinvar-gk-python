import enum
import os
import pathlib
import gzip
import csv
import json
import sys
import time

import clinvar_gk_pilot
from clinvar_gk_pilot.gcs import (
    list_blobs,
    already_downloaded,
    download_to_local_file,
    _local_file_path_for,
)

# increase csv field size limit
csv.field_size_limit(sys.maxsize)


bucket_name = "clinvar-gk-pilot"

# folder_path = "2024-04-07/dev/catvar_output_v2/"
# output_file_name = "combined-catvar_output.ndjson.gz"

folder_path = "2024-04-07/dev/scv_output_v2/"
output_file_name = "combined-scv_output.ndjson.gz"

blob_uris = list_blobs(bucket_name, folder_path)
blob_uris = [blob for blob in blob_uris if not blob.endswith("/")]
for blob in blob_uris:
    print(blob)
local_paths = []
# Download all files
print("Downloading files...")
expected_local_paths = [_local_file_path_for(blob) for blob in blob_uris]
for expected_local_path, blob_uri in zip(expected_local_paths, blob_uris):
    if not os.path.exists(expected_local_path):
        local_paths.append(download_to_local_file(blob_uri))
    else:
        local_paths.append(expected_local_path)
# for blob in blob_uris:
#     if not already_downloaded(blob):
#         print(f"Downloading {blob}...")
#         local_paths.append(download_to_local_file(blob))
#     else:
#         print(f"Already downloaded {blob}")
#         local_paths.append(_local_file_path_for(blob))

# sys.exit(0)

output_lines_count = 0
last_logged_output_count_time = time.time()
last_logged_output_count_value = 0


with gzip.open(output_file_name, "wt", compresslevel=9) as f_out:
    for file_idx, file_path in enumerate(local_paths):
        print(f"Reading {file_path} ({file_idx + 1}/{len(local_paths)})...")
        try:
            with gzip.open(file_path, "rt") as f_in:
                reader = csv.reader(f_in)
                for i, row in enumerate(reader):
                    assert (
                        len(row) == 1
                    ), f"row {i} of file {file_path} had more than 1 column! ({len(row)} columns) {row}"
                    obj = json.loads(row[0])
                    assert (
                        len(obj) == 1
                    ), f"row {i} of file {file_path} had more than 1 key! ({len(obj)} keys) {obj}"

                    # Write key and value
                    key, value = list(obj.items())[0]
                    assert isinstance(
                        key, str
                    ), f"key {key} on line {i} of file {file_path} is not a string!"

                    f_out.write(json.dumps(value))
                    f_out.write("\n")
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
