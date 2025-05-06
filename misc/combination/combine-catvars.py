"""
This script is for combining newline-delimited JSON files from a Google Cloud Storage bucket into one file and uploading it back to the bucket.

The input JSON objects are also parsed and the values from .rec.<id> are used as the final output objects written to the output file.

e.g.:
{"rec": {"12345": {"key1": "value1", "key2": "value2"}}}

becomes:

{"key1": "value1", "key2": "value2"}
"""

import gzip
import json
import os
import re
import time
from dataclasses import dataclass

from google.cloud import storage


@dataclass()
class Env:
    bucket_name: str
    folder_path: str
    file_pattern: str
    output_file_path: str
    output_blob_path: str

    def __init__(self):
        self.bucket_name = os.getenv("bucket_name")
        self.folder_path = os.getenv("folder_path")
        self.file_pattern = os.getenv("file_pattern")
        self.output_file_path = os.getenv("output_file_path")
        self.output_blob_path = os.getenv("output_blob_path")


# def _open(file_path, mode):
#     if file_path.startswith("gs://"):
#         return storage.open(file_path, mode)

#     if file_path.endswith(".gz"):
#         return gzip.open(file_path, mode)
#     return open(file_path, mode)


def combine_files(
    bucket_name, folder_path, file_pattern, output_file_path, output_blob_path=None
):
    # Initialize Google Cloud Storage client
    client = storage.Client()

    # Get the bucket
    bucket = client.get_bucket(bucket_name)

    if bucket is None:
        print(f"{bucket_name} bucket not found.")
        return

    # List all files in the folder matching the file pattern
    blobs = bucket.list_blobs(prefix=folder_path)

    if blobs is None:
        print(f"No blobs found in {folder_path}.")
        return

    # log the blobs
    blobs = list(blobs)
    for blob in blobs:
        print(f"Blob: {blob.name}")

    files_to_combine = [
        blob.name
        for blob in blobs
        if re.match(file_pattern, os.path.basename(blob.name))
    ]

    if len(files_to_combine) == 0:
        print(f"No files found matching pattern {file_pattern} to combine.")
        return

    # Logging stuff
    output_keys_count = 0
    last_logged_output_count_time = time.time()
    last_logged_output_count_value = 0

    with gzip.open(output_file_path, "wt") as f_out:
        # Iterate over each file
        for file_name in files_to_combine:
            print(f"Processing file: {file_name}")
            blob = bucket.get_blob(file_name)
            with gzip.open(blob.open("rb"), "rt") as f_in:
                for i, line in enumerate(f_in):
                    obj = json.loads(line)
                    assert len(obj) == 1, (
                        f"row {i} of file {file_name} had more than 1 key! ({len(obj)} keys) {obj}"
                    )
                    obj = obj["rec"]
                    assert len(obj) == 1, (
                        f"row {i} of file {file_name} had more than 1 key! ({len(obj)} keys) {obj}"
                    )
                    obj = obj[list(obj.keys())[0]]

                    f_out.write(json.dumps(obj))
                    f_out.write("\n")

                    # Progress logging
                    output_keys_count += 1
                    now = time.time()
                    if now - last_logged_output_count_time > 5:
                        new_lines = output_keys_count - last_logged_output_count_value
                        print(
                            f"Output keys written: {output_keys_count} ({new_lines / 5:.2f} lines/s)"
                        )
                        last_logged_output_count_value = output_keys_count
                        last_logged_output_count_time = now

        f_out.write("\n")

    print(f"Combined file {output_file_path} created successfully.")

    if output_blob_path:
        # Upload the combined file to the output_blob_uri
        blob = bucket.blob(output_blob_path)
        blob.upload_from_filename(output_file_path)

        print(f"Combined file {output_file_path} uploaded to {output_blob_path}.")


if __name__ == "__main__":
    # app.run(debug=True, host="0.0.0.0")
    env = Env()
    print(
        f"bucket_name: {env.bucket_name}, "
        f"folder_path: {env.folder_path}, "
        f"file_pattern: {env.file_pattern}, "
        f"output_file_path: {env.output_file_path}, "
        f"output_blob_path: {env.output_blob_path}"
    )

    combine_files(
        bucket_name=env.bucket_name,
        folder_path=env.folder_path,
        file_pattern=env.file_pattern,
        output_file_path=env.output_file_path,
        output_blob_path=env.output_blob_path,
    )
