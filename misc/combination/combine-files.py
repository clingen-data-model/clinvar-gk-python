import csv
from dataclasses import dataclass
import json
import os
import re
import gzip
import sys
import time
# from flask import Flask, request, jsonify
from google.cloud import storage

# increase csv field size limit
csv.field_size_limit(sys.maxsize)

# app = Flask(__name__)


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


def _open(file_path, mode):
    if file_path.startswith("gs://"):
        return storage.open(file_path, mode)

    if file_path.endswith(".gz"):
        return gzip.open(file_path, mode)
    return open(file_path, mode)


class NDJson:

    def __init__(self, file_path):
        self.file_path = file_path

    def __enter__(self):
        self.file = open(self.file_path, "w")
        self.file.write("[\n")
        return self

    def write(self, obj):
        self.file.write(json.dumps(obj) + "\n")

    def __exit__(self, exc_type, exc_value, traceback):
        self.file.write("]\n")
        self.file.close()


def combine_files(bucket_name, folder_path, file_pattern, output_file_path, output_blob_path=None):

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

    files_to_combine = [blob.name for blob in blobs if re.match(
        file_pattern, os.path.basename(blob.name))]

    if len(files_to_combine) == 0:
        print(f"No files found matching pattern {file_pattern} to combine.")
        return

    # Logging stuff
    output_keys_count = 0
    last_logged_output_count_time = time.time()
    last_logged_output_count_value = 0

    with gzip.open(output_file_path, 'wt') as f_out:
        f_out.write("{\n")

        # Iterate over each file
        for file_name in files_to_combine:
            print(f"Processing file: {file_name}")
            blob = bucket.get_blob(file_name)
            with gzip.open(blob.open("rb"), 'rt') as f_in:
                reader = csv.reader(f_in)
                is_first_row = True
                for i, row in enumerate(reader):
                    assert (
                        len(row) == 1
                    ), f"row {i} of file {file_name} had more than 1 column! ({len(row)} columns) {row}"
                    obj = json.loads(row[0])
                    assert (
                        len(obj) == 1
                    ), f"row {i} of file {file_name} had more than 1 key! ({len(obj)} keys) {obj}"

                    # Write key and value
                    key, value = list(obj.items())[0]
                    assert isinstance(
                        key, str
                    ), f"key {key} on line {i} of file {file_name} is not a string!"

                    if not is_first_row:
                        f_out.write(",\n")
                    f_out.write("    ")
                    f_out.write(f'"{key}": ')
                    f_out.write(json.dumps(value))
                    is_first_row = False

                    # Progress logging
                    output_keys_count += 1
                    now = time.time()
                    if now - last_logged_output_count_time > 5:
                        new_lines = output_keys_count - last_logged_output_count_value
                        print(
                            f"Output keys written: {output_keys_count} ({new_lines/5:.2f} lines/s)"
                        )
                        last_logged_output_count_value = output_keys_count
                        last_logged_output_count_time = now

        f_out.write("\n}\n")

    print(f"Combined file {output_file_path} created successfully.")

    if output_blob_path:
        # Upload the combined file to the output_blob_uri
        blob = bucket.blob(output_blob_path)
        blob.upload_from_filename(output_file_path)

        print(
            f"Combined file {output_file_path} uploaded to {output_blob_path}."
        )


# @app.route('/')
# def combine_files_http():
#     # Get query parameters
#     bucket_name = request.args.get('bucket_name')
#     folder_path = request.args.get('folder_path')
#     file_pattern = request.args.get('file_pattern')
#     output_file_path = request.args.get('output_file_path')
#     output_blob_path = request.args.get('output_blob_path', default=None)

#     print(f"bucket_name: {bucket_name}, "
#           f"folder_path: {folder_path}, "
#           f"file_pattern: {file_pattern}, "
#           f"output_file_path: {output_file_path}, "
#           f"output_blob_path: {output_blob_path}")

#     # Call the function to combine files
#     combine_files(bucket_name, folder_path, file_pattern,
#                   output_file_path, output_blob_path)

#     ret = {'message': 'Combined file created successfully.'}
#     if output_blob_path:
#         ret['output_blob_path'] = f"gs://{bucket_name}/{output_blob_path}"

#     print(json.dumps(ret))
#     return jsonify(ret)


if __name__ == '__main__':
    # app.run(debug=True, host="0.0.0.0")
    env = Env()
    print(f"bucket_name: {env.bucket_name}, "
          f"folder_path: {env.folder_path}, "
          f"file_pattern: {env.file_pattern}, "
          f"output_file_path: {env.output_file_path}, "
          f"output_blob_path: {env.output_blob_path}")

    combine_files(
        bucket_name=env.bucket_name,
        folder_path=env.folder_path,
        file_pattern=env.file_pattern,
        output_file_path=env.output_file_path,
        output_blob_path=env.output_blob_path
    )
