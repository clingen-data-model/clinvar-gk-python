import asyncio
import contextlib
import gzip
import json
import multiprocessing
import os
import pathlib
import queue
import sys
from dataclasses import dataclass
from functools import partial
from typing import List

import requests
from ga4gh.vrs.dataproxy import create_dataproxy
from ga4gh.vrs.extras.translator import AlleleTranslator, CnvTranslator
from ga4gh.vrs.models import CopyChange

from clinvar_gk_pilot.cli import parse_args
from clinvar_gk_pilot.gcs import (
    _local_file_path_for,
    already_downloaded,
    download_to_local_file,
)
from clinvar_gk_pilot.logger import logger

# TODO - implement as separate strategy class for using vrs_python
#        vs. another for anyvar vs. another for variation_normalizer
#        Encapsulate translators and data_proxy in strategy class
seqrepo_dataproxy_url = os.environ.get(
    "SEQREPO_DATAPROXY_URL", "seqrepo+file:///Users/toneill/dev/seqrepo-2024-02-20/"
)
if not seqrepo_dataproxy_url:
    raise RuntimeError("'SEQREPO_DATAPROXY_URL' must be defined in the environment.")
data_proxy = create_dataproxy(seqrepo_dataproxy_url)
allele_translators = {
    "36": AlleleTranslator(data_proxy=data_proxy, default_assembly_name="GRCh36"),
    "37": AlleleTranslator(data_proxy=data_proxy, default_assembly_name="GRCh37"),
    "38": AlleleTranslator(data_proxy=data_proxy),
}

cnv_translators = {
    "36": CnvTranslator(data_proxy=data_proxy, default_assembly_name="GRCh36"),
    "37": CnvTranslator(data_proxy=data_proxy, default_assembly_name="GRCh37"),
    "38": CnvTranslator(data_proxy=data_proxy),
}


def process_line(line: str) -> str:
    """
    Takes a line of JSON, processes it, and returns the result as a JSON string.
    """
    clinvar_json = json.loads(line)
    result = None
    if clinvar_json.get("issue") is None:
        cls = clinvar_json["vrs_class"]
        if cls == "Allele":
            result = allele(clinvar_json)
        elif cls == "CopyNumberChange":
            result = copy_number_change(clinvar_json)
        elif cls == "CopyNumberCount":
            result = copy_number_count(clinvar_json)
    content = {"in": clinvar_json, "out": result}
    return json.dumps(content)


def _task_worker(
    task_queue: multiprocessing.Queue, return_queue: multiprocessing.Queue
):
    """
    Worker function that processes tasks from a queue.
    """
    while True:
        task = task_queue.get()
        if task is None:
            break
        return_queue.put(task())


def worker(file_name_gz: str, output_file_name: str) -> None:
    """
    Takes an input file (a GZIP file of newline delimited), runs `process_line`
    on each line, and writes the output to a new GZIP file called `output_file_name`.
    """
    with (
        gzip.open(file_name_gz, "rt", encoding="utf-8") as input_file,
        gzip.open(output_file_name, "wt", encoding="utf-8") as output_file,
    ):
        task_queue = multiprocessing.Queue()
        return_queue = multiprocessing.Queue()
        task_timeout = 10

        def make_background_process():
            p = multiprocessing.Process(
                target=_task_worker,
                args=(task_queue, return_queue),
            )
            return p

        background_process = make_background_process()
        background_process.start()

        for line in input_file:
            task_queue.put(partial(process_line, line))
            try:
                ret = return_queue.get(timeout=task_timeout)
            except queue.Empty:
                print("Task did not complete in time, terminating it.")
                background_process.terminate()
                background_process.join()
                ret = json.dumps(
                    {
                        "in": json.loads(line),
                        "out": {
                            "errors": f"Task did not complete in {task_timeout} seconds.",
                        },
                    }
                )
                print("Restarting background process")
                background_process = make_background_process()
                background_process.start()
            output_file.write(ret)
            output_file.write("\n")

        task_queue.put(None)
        background_process.join()


def process_as_json_single_thread(input_file_name: str, output_file_name: str) -> None:
    with gzip.open(input_file_name, "rt", encoding="utf-8") as f_in:
        with gzip.open(output_file_name, "wt", encoding="utf-8") as f_out:
            for line in f_in:
                f_out.write(process_line(line))
                f_out.write("\n")
    print(f"Output written to {output_file_name}")


def process_as_json(
    input_file_name: str, output_file_name: str, parallelism: int
) -> None:
    """
    Process `input_file_name` in parallel and write the results to `output_file_name`.
    """
    assert parallelism > 0, "Parallelism must be greater than 0"
    part_input_file_names = partition_file_lines_gz(input_file_name, parallelism)

    part_output_file_names = [f"{ofn}.out" for ofn in part_input_file_names]

    workers = []
    # Start a worker per file name
    for part_ifn, part_ofn in zip(part_input_file_names, part_output_file_names):
        w = multiprocessing.Process(target=worker, args=(part_ifn, part_ofn))
        w.start()
        workers.append(w)

    # Wait for all workers to finish
    for w in workers:
        w.join()

    with gzip.open(output_file_name, "wt", encoding="utf-8") as f_out:
        for part_ofn in part_output_file_names:
            print(f"Writing output from {part_ofn} to {output_file_name}")
            line_counter = 0
            with gzip.open(part_ofn, "rt", encoding="utf-8") as f_in:
                for line in f_in:
                    f_out.write(line)
                    if not line.endswith("\n"):
                        f_out.write("\n")
                    line_counter += 1
            print(f"Lines written: {line_counter}")

    print(f"Output written to {output_file_name}")


def allele(clinvar_json: dict) -> dict:
    try:
        tlr = allele_translators[clinvar_json.get("assembly_version", "38")]
        vrs = tlr.translate_from(var=clinvar_json["source"], fmt=clinvar_json["fmt"])
        return vrs.model_dump(exclude_none=True)
    except Exception as e:
        logger.error(f"Exception raised in 'allele' processing: {clinvar_json}: {e}")
        return {"errors": str(e)}


def copy_number_count_vrspython(clinvar_json: dict) -> dict:
    try:
        tlr = cnv_translators[clinvar_json.get("assembly_version", "38")]
        kwargs = {"copies": clinvar_json["absolute_copies"]}
        vrs = tlr.translate_from(
            var=clinvar_json["source"], fmt=clinvar_json["fmt"], **kwargs
        )
        return vrs.model_dump(exclude_none=True)
    except Exception as e:
        logger.error(
            f"Exception raised in 'copy_number_count' processing: {clinvar_json}: {e}"
        )
        return {"errors": str(e)}


def copy_number_change(clinvar_json: dict) -> dict:
    """
    Create a VRS CopyNumberChange variation using the variation-normalization module.

    Returns:
        Dictionary containing VRS representation or error information
    """
    try:
        # Extract required parameters from clinvar_json
        hgvs_expr = clinvar_json["source"]
        # absolute_copies = clinvar_json["absolute_copies"]

        # Get baseline_copies by offsetting by one from absolute_copies
        if clinvar_json["variation_type"] in ["Deletion", "copy number loss"]:
            # baseline_copies = absolute_copies + 1
            copy_change = CopyChange.LOSS
        elif clinvar_json["variation_type"] in ["Duplication", "copy number gain"]:
            # baseline_copies = absolute_copies - 1
            copy_change = CopyChange.GAIN
        else:
            return {"errors": f"Unknown variation_type: {clinvar_json}"}

        vrs_variant = asyncio.run(
            query_handler.to_copy_number_handler.hgvs_to_copy_number_change(
                hgvs_expr=hgvs_expr, copy_change=copy_change
            )
        ).copy_number_change
        return vrs_variant.model_dump(exclude_none=True)

    except Exception as e:
        error_msg = f"Unexpected error: {e}"
        logger.error(f"Exception in copy_number_count: {clinvar_json}: {error_msg}")
        return {"errors": error_msg}


def copy_number_count(clinvar_json: dict) -> dict:
    """
    Create a VRS Copy Number Count variation using the variation-normalization service.

    Args:
        clinvar_json: Dictionary containing ClinVar data with keys:
            - source: HGVS expression or other variation string
            - absolute_copies: The absolute number of copies
            - assembly_version: Optional assembly version (defaults to 38)

    Returns:
        Dictionary containing VRS representation or error information
    """
    try:
        # Extract required parameters from clinvar_json
        hgvs_expr = clinvar_json["source"]
        absolute_copies = clinvar_json["absolute_copies"]

        # Get baseline_copies by offsetting by one from absolute_copies
        if clinvar_json["variation_type"] in ["Deletion", "copy number loss"]:
            baseline_copies = absolute_copies + 1
            # copy_change = CopyChange.LOSS
        elif clinvar_json["variation_type"] in ["Duplication", "copy number gain"]:
            baseline_copies = absolute_copies - 1
            # copy_change = CopyChange.GAIN
        else:
            return {"errors": f"Unknown variation_type: {clinvar_json}"}

        vrs_variant = asyncio.run(
            query_handler.to_copy_number_handler.hgvs_to_copy_number_count(
                hgvs_expr=hgvs_expr, baseline_copies=baseline_copies
            )
        ).copy_number_change
        return vrs_variant

    except Exception as e:
        error_msg = f"Unexpected error: {e}"
        logger.error(f"Exception in copy_number_count: {clinvar_json}: {error_msg}")
        return {"errors": error_msg}


def copy_number_change_vrspython(clinvar_json: dict) -> dict:
    try:
        tlr = cnv_translators[clinvar_json.get("assembly_version", "38")]
        kwargs = {"copy_change": clinvar_json["copy_change_type"]}
        vrs = tlr.translate_from(
            var=clinvar_json["source"], fmt=clinvar_json["fmt"], **kwargs
        )
        return vrs.model_dump(exclude_none=True)
    except Exception as e:
        logger.error(
            f"Exception raised in 'copy_number_change' processing: {clinvar_json}: {e}"
        )
        return {"errors": str(e)}


def partition_file_lines_gz(local_file_path_gz: str, partitions: int) -> List[str]:
    """
    Split `local_file_path_gz` into `partitions` roughly equal parts by line count.

    Return a list of `partitions` file names that are a roughly equal
    number of lines from `local_file_path_gz`.
    """
    filenames = [f"{local_file_path_gz}.part_{i + 1}" for i in range(partitions)]

    # Read the file and write each line to a file, looping through the output files
    with gzip.open(local_file_path_gz, "rt") as f:
        # Open output files
        with contextlib.ExitStack() as stack:
            files = [
                stack.enter_context(gzip.open(filename, "wt", encoding="utf-8"))
                for filename in filenames
            ]
            for i, line in enumerate(f):
                file_idx = i % partitions
                files[file_idx].write(line)

    return filenames


def main(argv=sys.argv[1:]):
    """
    Process the --filename argument (expected as 'gs://..../filename.json.gz')
    and returns contents in file 'output-filename.ndjson'
    """
    opts = parse_args(argv)
    filename = opts["filename"]
    if filename.startswith("gs://"):
        if not already_downloaded(filename):
            local_file_name = download_to_local_file(filename)
        else:
            local_file_name = _local_file_path_for(filename)
    else:
        local_file_name = filename

    outfile = str(pathlib.Path("output") / local_file_name)
    # Make parents
    os.makedirs(os.path.dirname(outfile), exist_ok=True)

    # run_opts = Options(vrs_type_filter=opts.vrs_type_filter)

    if opts["parallelism"] == 0:
        process_as_json_single_thread(local_file_name, outfile)
    else:
        process_as_json(local_file_name, outfile, opts["parallelism"])


if __name__ == "__main__":
    creds_contents = """[default]
    aws_access_key_id = asdf
    aws_secret_access_key = asdf"""
    aws_fake_creds_filename = "aws_fake_creds"
    with open(aws_fake_creds_filename, "w") as f:
        f.write(creds_contents)
    os.environ["AWS_SHARED_CREDENTIALS_FILE"] = str(
        pathlib.Path.cwd() / aws_fake_creds_filename
    )
    if "GENE_NORM_DB_URL" not in os.environ:
        raise RuntimeError("Must set GENE_NORM_DB_URL (e.g. http://localhost:8001)")
    if "SEQREPO_ROOT_DIR" not in os.environ:
        raise RuntimeError(
            "Must set SEQREPO_ROOT_DIR (e.g. /Users/kferrite/dev/data/seqrepo/2024-12-20)"
        )
    if "UTA_DB_URL" not in os.environ:
        raise RuntimeError(
            "Must set UTA_DB_URL (e.g. postgresql://anonymous@localhost:5433/uta/uta_20241220)"
        )

    # Import and initialize variation-normalizer QueryHandler
    # Requires env vars to be set and dynamodb jar to be run locally and pointed to with GENE_NORM_DB_URL
    # https://github.com/clingen-data-model/architecture/tree/master/helm/charts/clingen-vicc/docker/dynamodb
    # In the `dynamodb` directory above, build:
    # podman build -t gene-normalizer-dynamodb:latest .
    # Then run it (uses host gcloud config to authenticate to our bucket which has a snapshot of the gene database)
    # podman run -it -p 8001:8000 -v $HOME/.config/gcloud:/config/gcloud -v dynamodb:/data -e DATA_DIR=/data -e GOOGLE_APPLICATION_CREDENTIALS=/config/gcloud/application_default_credentials.json -e CLOUDSDK_CONFIG=/config/gcloud gene-normalizer-dynamodb:latest
    import variation
    from variation.query import QueryHandler

    query_handler = QueryHandler()

    if len(sys.argv) == 1:
        main(
            [
                "--filename",
                "gs://clinvar-gk-pilot/2025-03-23/dev/vi.json.gz",
                "--parallelism",
                "2",
            ]
        )

        # main(
        #     [
        #         "--filename",
        #         "vi-100000.json.gz",
        #         "--parallelism",
        #         "1",
        #     ]
        # )
    else:
        main(sys.argv[1:])
