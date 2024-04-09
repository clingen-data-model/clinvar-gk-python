import argparse
import gzip
import json
import os
import sys
from typing import List

import ndjson
from ga4gh.vrs.dataproxy import create_dataproxy
from ga4gh.vrs.extras.translator import AlleleTranslator, CnvTranslator

from clinvar_gk_pilot.gcs import parse_blob_uri
from clinvar_gk_pilot.logger import logger

# TODO - implement as separate strategy class for using vrs_python
#        vs. another for anyvar vs. another for variation_normalizer
#        Encapsulate translators and data_proxy in strategy class
seqrepo_dataproxy_url = os.environ.get("SEQREPO_DATAPROXY_URL", "seqrepo+file:///Users/toneill/dev/seqrepo-2024-02-20/")
if not seqrepo_dataproxy_url:
    raise RuntimeError("'SEQREPO_DATAPROXY_URL' must be defined in the environment.")
data_proxy = create_dataproxy(seqrepo_dataproxy_url)
allele_translators = {
    "36": AlleleTranslator(data_proxy=data_proxy, default_assembly_name="GRCh36"),
    "37": AlleleTranslator(data_proxy=data_proxy, default_assembly_name="GRCh37"),
    "38": AlleleTranslator(data_proxy=data_proxy)
}

cnv_translators = {
    "36": CnvTranslator(data_proxy=data_proxy, default_assembly_name="GRCh36"),
    "37": CnvTranslator(data_proxy=data_proxy, default_assembly_name="GRCh37"),
    "38": CnvTranslator(data_proxy=data_proxy)
}


def parse_args(args: List[str]) -> dict:
    """
    Parse arguments and return as dict.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--filename", required=True, help="Filename to read")
    return vars(parser.parse_args(args))


def download_to_local_file(filename: str) -> str:
    """
    Expects a filename beginning with "gs://" and ending with ".json.gz".
    Downloads and decompresses into string form.
    # TODO - this likely will not work for large ClinVar release files
    """
    if not filename.startswith("gs://"):
        raise RuntimeError(
            "Expecting a google cloud storage URI beginning with 'gs://'."
        )
    if not filename.endswith(".json.gz"):
        raise RuntimeError("Expecting a compressed filename ending with '.json.gz'.")
    blob = parse_blob_uri(filename)
    local_file_name = filename.split("/")[-1]
    with open(local_file_name, 'wb') as f:
        blob.download_to_file(file_obj=f)
    return local_file_name


def process_as_json(input_file_name: str, output_file_name: str) -> None:
    with gzip.GzipFile(input_file_name, "rb") as input, open(output_file_name, "wt", encoding="utf-8") as output:
        for line in input:
            for clinvar_json in ndjson.loads(line.decode("utf-8")):
                if clinvar_json.get('issue') is not None:
                    result = None
                else:
                    cls = clinvar_json['vrs_class']
                    if cls == 'Allele':
                        result = allele(clinvar_json)
                    elif cls == 'CopyNumberChange':
                        result = copy_number_change(clinvar_json)
                    elif cls == 'CopyNumberCount':
                        result = copy_number_count(clinvar_json)
                content = {"in": clinvar_json, "out": result}
                output.write(str(json.dumps(content) + "\n"))


def allele(clinvar_json: dict) -> dict:
    try:
        tlr = allele_translators.get(clinvar_json.get('assembly_version', '38'))
        vrs = tlr.translate_from(var=clinvar_json['source'], fmt=clinvar_json['fmt'])
        return vrs.model_dump(exclude_none=True)
    except Exception as e:
        logger.error(f"Exception raised in 'allele' processing: {clinvar_json}")
        return {"errors": str(e)}


def copy_number_count(clinvar_json: dict) -> dict:
    try:
        tlr = cnv_translators.get(clinvar_json.get('assembly_version', '38'))
        kwargs = {"copies": clinvar_json['absolute_copies']}
        vrs = tlr.translate_from(var=clinvar_json['source'], fmt=clinvar_json['fmt'], **kwargs)
        return vrs.model_dump(exclude_none=True)
    except Exception as e:
        logger.error(f"Exception raised in 'copy_number_count' processing: {clinvar_json}")
        return {"errors": str(e)}


def copy_number_change(clinvar_json: dict) -> dict:
    try:
        tlr = cnv_translators.get(clinvar_json.get('assembly_version', '38'))
        kwargs = {"copy_change": clinvar_json['copy_change_type']}
        vrs = tlr.translate_from(var=clinvar_json['source'], fmt=clinvar_json['fmt'], **kwargs)
        return vrs.model_dump(exclude_none=True)
    except Exception as e:
        logger.error(f"Exception raised in 'copy_number_change' processing: {clinvar_json}")
        return {"errors": str(e)}


def main(argv=sys.argv):
    """
    Process the --filename argument (expected as 'gs://..../filename.json.gz')
    and returns contents in file 'output-filename.ndjson'
    """
    filename = parse_args(argv)["filename"]
    local_file_name = download_to_local_file(filename)
    outfile = str(
        "output-" + local_file_name.replace(".json.gz", "") + ".ndjson"
    )
    process_as_json(local_file_name, outfile)


if __name__ == "__main__":
    main(["--filename", "gs://clinvar-gk-pilot/2024-04-07/dev/vi.json.gz"])
