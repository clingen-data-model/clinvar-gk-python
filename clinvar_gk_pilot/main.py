import argparse
import gzip
import json
import sys
from typing import List

import ndjson
from ga4gh.vrs.dataproxy import create_dataproxy
from ga4gh.vrs.extras.translator import AlleleTranslator, CnvTranslator

from clinvar_gk_pilot.gcs import parse_blob_uri
from clinvar_gk_pilot.logger import logger

# TODO - implement as separate strategy class for using vrs_python
#        vs. another for anyvar vs. another for variation_normalizer
#        Encapsulate trnslators and data_proxy in strategy class
# TODO - source dataproxy string environment var
data_proxy = create_dataproxy("seqrepo+file:///Users/toneill/dev/seqrepo-2021-01-29/")
allele_translator = AlleleTranslator(data_proxy=data_proxy)
cnv_translator = CnvTranslator(data_proxy=data_proxy)


def parse_args(args: List[str]) -> dict:
    """
    Parse arguments and return as dict.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--filename", required=True, help="Filename to read")
    return vars(parser.parse_args(args))


def download_and_decompress_file(filename: str) -> str:
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
    data = blob.download_as_bytes()
    bytes_data = gzip.decompress(data)
    return str(bytes_data, "utf-8")


def process_as_json(str_data: str, outfile: str) -> None:
    """
    Processes data as lines of ndjson.

    Makes processing decisions based on 'type' and 'policy' in 'vrs_xform_plan'.

    Outputs ndjson into 'outfile' with an 'in' key representing the input json
    and an 'out' key representing an vrs output, 'errors' dict, or null if
    'Unsupported'.

    Possible vrs_xform_policy contents:
        {"type": "Allele", "policy": "Canonical SPDI"}
        {"type": "Allele", "policy": "Remaining valid hgvs alleles"}
        {"type": "CopyNumberChange", "policy": "Copy number change (cn loss|del and cn gain|dup)"}
        {"type": "CopyNumberCount", "policy": "Absolute copy count"}
        {"type": "Unsupported", "policy": "Genotype/Haplotype"}
        {"type": "Unsupported", "policy": "Invalid/unsupported hgvs"}
        {"type": "Unsupported", "policy": "Min/max copy count range not supported"}
        {"type": "Unsupported", "policy": "No hgvs or location info"}
    """
    with open(outfile, "wt", encoding="utf-8") as f:
        for clinvar_json in ndjson.loads(str_data):
            vrs_xform_plan = clinvar_json["vrs_xform_plan"]
            plan_type = vrs_xform_plan["type"]
            plan_policy = vrs_xform_plan["policy"]
            result = None
            if plan_type == "Allele":
                if plan_policy == "Canonical SPDI":
                    result = canonical_spdi(clinvar_json)
                else:
                    result = hgvs(clinvar_json)
            elif plan_type == "CopyNumberChange":
                result = copy_number_change(clinvar_json)
            elif plan_type == "CopyNumberCount":
                result = copy_number_count(clinvar_json)
            content = {"in": clinvar_json, "out": result}
            f.write(str(json.dumps(content) + "\n"))


def canonical_spdi(clinvar_json: dict) -> dict:
    try:
        spdi = clinvar_json["canonical_spdi"]
        vrs = allele_translator.translate_from(var=spdi, fmt="spdi")
        return vrs.model_dump(exclude_none=True)
    except Exception as e:
        logger.error(f"Exception raised in 'canonical_spdi' processing: {clinvar_json}")
        return {"errors": str(e)}


def get_hgvs(clinvar_json: dict) -> str:
    """
    Returns the hgvs expression from clinvar json
    """
    return clinvar_json["vrs_xform_plan"]["anyvar_variation_put_request"]["definition"]


def hgvs(clinvar_json: dict) -> dict:
    try:
        hgvs = get_hgvs(clinvar_json)
        vrs = allele_translator.translate_from(var=hgvs, fmt="hgvs")
        return vrs.model_dump(exclude_none=True)
    except Exception as e:
        logger.error(f"Exception raised in 'hgvs' processing: {clinvar_json}")
        return {"errors": str(e)}


def copy_number_change(clinvar_json: dict) -> dict:
    try:
        hgvs = get_hgvs(clinvar_json)
        variation_type = clinvar_json["variation_type"]
        efo_code = (
            "efo:0030067"
            if variation_type == "Deletion" or variation_type == "copy number loss"
            else "efo:0030070"
        )
        kwargs = {"copy_change": efo_code}
        vrs = cnv_translator.translate_from(var=hgvs, fmt="hgvs", **kwargs)
        return vrs.model_dump(exclude_none=True)
    except Exception as e:
        logger.error(
            f"Exception raised in 'copy_number_change' processing: {clinvar_json}"
        )
        return {"errors": str(e)}


def copy_number_count(clinvar_json: dict) -> dict:
    try:
        hgvs = get_hgvs(clinvar_json)
        copies = clinvar_json["absolute_copies"]
        kwargs = {"copies": copies}
        vrs = cnv_translator.translate_from(var=hgvs, fmt="hgvs", **kwargs)
        return vrs.model_dump(exclude_none=True)
    except Exception as e:
        logger.error(
            f"Exception raised in 'copy_number_count' processing: {clinvar_json}"
        )
        return {"errors": str(e)}


def main(argv=sys.argv):
    """
    Process the --filename argument (expected as 'gs://..../filename.json.gz')
    and returns contents in file 'output-filename.ndjson'
    """
    filename = parse_args(argv)["filename"]
    str_data = download_and_decompress_file(filename)
    outfile = str(
        "output-" + filename.split("/")[-1].replace(".json.gz", "") + ".ndjson"
    )
    process_as_json(str_data, outfile)


if __name__ == "__main__":
    main(["--filename", "gs://clinvar-gk-pilot/2024-02-21/dev/vi.json.gz"])
