#!/usr/bin/env bash

# get the parent directory of this script and refer to combine-catvars.py

script="$(dirname "$(realpath "$0")")/combine-catvars.py"

echo "$script"

if [ ! -f "$script" ]; then
    echo "Script not found: $script"
    exit 1
fi

# input files: clinvar-gk-pilot/2025-03-23/dev/final_out/json
# Don't use leading or trailing slashes in paths
export bucket_name=clinvar-gk-pilot
export folder_path=2025-03-23/dev/final_out/json
export file_pattern=".*.json.gz"
export output_file_path="final_out-combined.ndjson.gz"
export output_blob_path=2025-03-23/dev/final_out-combined.ndjson.gz

python ${script}
