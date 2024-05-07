import enum
import os
import pathlib
import gzip
import csv
import json
import sys
import time

# increase csv field size limit
csv.field_size_limit(sys.maxsize)

directory = "buckets/clinvar-gk-pilot/2024-04-07/dev/catvar_output_v2/"
file_names = os.listdir(directory)  # without directory path
# print(file_names)

# file_names = file_names[:1]

output_keys_count = 0
last_logged_output_count_time = time.time()
last_logged_output_count_value = 0

output_file_name = "combined-catvar_output.json"
f0 = pathlib.Path(directory) / file_names[0]
with gzip.open(output_file_name, "wt", compresslevel=9) as f_out:
    f_out.write("{\n")

    for file_idx, file_name in enumerate(file_names):
        file_path = pathlib.Path(directory) / file_name
        print(f"Reading {file_path} ({file_idx + 1}/{len(file_names)})...")
        try:
            with gzip.open(file_path, "rt") as f_in:
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
                    output_keys_count += 1
                    is_first_row = False
                    now = time.time()
                    if now - last_logged_output_count_time > 5:
                        new_lines = output_keys_count - last_logged_output_count_value
                        print(
                            f"Output keys written: {output_keys_count} ({new_lines/5:.2f} lines/s)"
                        )
                        last_logged_output_count_value = output_keys_count
                        last_logged_output_count_time = now
        except Exception as e:
            print(f"Exception while reading {file_name}: {e}")
            raise e
    f_out.write("}\n")

print(f"Wrote {output_file_name} successfully!")
