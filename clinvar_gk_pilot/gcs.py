import os
import queue
import subprocess
import threading
import time
from pathlib import Path, PurePath

import requests
from google.cloud import storage

from clinvar_gk_pilot.logger import logger
from clinvar_gk_pilot.utils import make_progress_logger


def _get_gcs_client() -> storage.Client:
    if getattr(_get_gcs_client, "client", None) is None:
        setattr(_get_gcs_client, "client", storage.Client())
    return getattr(_get_gcs_client, "client")


def parse_blob_uri(uri: str, client: storage.Client = None) -> storage.Blob:
    if not uri.startswith("gs://"):
        raise ValueError("Must be a fully qualified URI beginning with gs://")
    if client is None:
        client = _get_gcs_client()
    proto, *rest = uri.split("://")
    bucket, *path_segments = rest[0].split("/")
    return storage.Blob(
        name="/".join(path_segments), bucket=storage.Bucket(client=client, name=bucket)
    )


def _local_file_path_for(blob_uri: str, root_dir: str = "buckets") -> str:
    parsed_uri = parse_blob_uri(blob_uri)
    relpath = f"{root_dir}/{parsed_uri.bucket.name}/{parsed_uri.name}"
    return relpath


def already_downloaded(blob_uri: str) -> bool:
    """
    Returns true if a file at the expected path (using _local_file_path_for)
    exists locally and has the same size as the remote blob.
    """
    expected_local_file = _local_file_path_for(blob_uri)
    blob = parse_blob_uri(blob_uri)
    # load the blob metadata from the server
    blob.reload()
    blob_bytes = blob.size
    return (
        Path(expected_local_file).exists()
        and Path(expected_local_file).stat().st_size == blob_bytes
    )


def download_to_local_file(blob_uri: str) -> str:
    """
    Expects a blob_uri beginning with "gs://".
    Downloads to a local file using _local_file_path_for to generate the local path.
    """
    if not blob_uri.startswith("gs://"):
        raise RuntimeError(
            "Expecting a google cloud storage URI beginning with 'gs://'."
        )
    blob = parse_blob_uri(blob_uri)
    local_file_name = _local_file_path_for(blob_uri)
    # Make parents
    os.makedirs(os.path.dirname(local_file_name), exist_ok=True)
    with open(local_file_name, "wb") as f:
        logger.info(f"Downloading {blob_uri} to {local_file_name}")
        blob.download_to_file(file_obj=f)
    return local_file_name


def copy_file_to_bucket(
    local_file_uri: str, remote_blob_uri: str, client: storage.Client = None
):
    """
    Upload the contents of file `local_file_uri` on local filesystem, to `remote_blob_uri` in
    """
    logger.info(f"Uploading {local_file_uri} to {remote_blob_uri}")
    if client is None:
        client = _get_gcs_client()
    blob = parse_blob_uri(remote_blob_uri, client=client)
    blob.upload_from_filename(client=client, filename=local_file_uri)
    logger.info(f"Finished uploading {local_file_uri} to {remote_blob_uri}")


def blob_writer(
    blob_uri: str, client: storage.Client = None, binary=True
) -> storage.Blob:
    """
    Returns a file-like object that can be used to write to the blob at `blob_uri`
    """
    if client is None:
        client = _get_gcs_client()
    blob = parse_blob_uri(blob_uri, client=client)
    return blob.open("wb" if binary else "w")


def blob_reader(
    blob_uri: str, client: storage.Client | None = None, binary=True
) -> storage.Blob:
    """
    Returns a file-like object that can be used to read from the blob at `blob_uri`
    """
    if client is None:
        client = _get_gcs_client()
    blob = parse_blob_uri(blob_uri, client=client)
    return blob.open("rb" if binary else "r")


def blob_size(blob_uri: str, client: storage.Client | None = None) -> int:
    """
    Returns the size of the blob in bytes if it exists. Raises an error if it does not.
    """
    if client is None:
        client = _get_gcs_client()
    blob = parse_blob_uri(blob_uri, client=client)
    blob.reload()  # Refreshes local Blob object properties from the remote object
    assert blob.exists()
    assert blob.size is not None
    return blob.size


def list_blobs(bucket_name: str, prefix: str, client: storage.Client | None = None):
    if client is None:
        client = _get_gcs_client()

    bucket = client.get_bucket(bucket_name)
    blobs = bucket.list_blobs(prefix=prefix)

    # Generate the list of blob URIs
    blob_uris = [f"gs://{bucket_name}/{blob.name}" for blob in blobs]

    return blob_uris


def http_download_requests(
    http_uri: str,
    local_path: PurePath,
    file_size: int,
    chunk_size=8 * 1024 * 1024,
):
    """
    Download the contents of `http_uri` to `local_path` using requests.get
    """
    logger.info(f"Downloading {http_uri} to {local_path}")

    bytes_read = 0
    response = requests.get(http_uri, stream=True, timeout=10)
    response.raise_for_status()
    opened_file_size = int(response.headers.get("Content-Length"))

    log_progress = make_progress_logger(
        logger=logger,
        fmt="Read {elapsed_value} bytes in {elapsed:.2f} seconds. Total bytes read: {current_value}/{max_value}.",
        max_value=opened_file_size,
    )

    if file_size and opened_file_size != file_size:
        raise RuntimeError(
            f"File size mismatch. Expected {file_size} but got {opened_file_size}."
        )
    with open(local_path, "wb") as f_out:
        for chunk in response.iter_content(chunk_size=chunk_size):
            chunk_bytes_read = len(chunk)
            bytes_read += chunk_bytes_read

            log_progress(bytes_read)

            if len(chunk) > 0:
                f_out.write(chunk)

            if len(chunk) == 0:
                wait_time = 10
                logger.warning(
                    f"Received an empty chunk from {http_uri} at byte {bytes_read}. Pausing {wait_time} seconds"
                )
                time.sleep(wait_time)

    return Path(local_path)


def http_download_curl(
    http_uri: str,
    local_path: PurePath,
    file_size: int,
) -> Path:
    """
    Download the contents of `http_uri` to `local_path` using a subprocess call to curl.

    NOTE: an executable named `curl` must be available in the system PATH.
    """
    p = subprocess.Popen(
        ["curl", "-o", local_path, http_uri],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    def reader(pipe: subprocess.PIPE, q: queue.Queue):
        try:
            with pipe:
                for line in iter(pipe.readline, b""):
                    q.put((pipe, line))
        finally:
            q.put(None)

    q = queue.Queue()
    t1 = threading.Thread(target=reader, args=(p.stdout, q))
    t1.start()
    t2 = threading.Thread(target=reader, args=(p.stderr, q))
    t2.start()

    def file_stat(path: Path, q: queue.Queue):
        while True:
            try:
                _ = q.get_nowait()
                break
            except queue.Empty:
                if not path.exists():
                    logger.info(f"{path} does not exist")
                else:
                    logger.info(f"{path} size: {path.stat().st_size}")
            time.sleep(10)

    t_stat_stop = queue.Queue()
    t_stat = threading.Thread(target=file_stat, args=(Path(local_path), t_stat_stop))
    t_stat.start()

    for _ in range(2):
        for pipe, line in iter(q.get, None):
            logger.info(f"{pipe}: {line.decode('utf-8')}")

    returncode = p.wait()
    logger.info(f"curl return code: {returncode}")

    t_stat_stop.put(None)

    actual_path = Path(local_path)
    if not actual_path.exists():
        raise RuntimeError(f"File {local_path} does not exist")
    if actual_path.stat().st_size != file_size:
        raise RuntimeError(
            f"File size mismatch. Expected {file_size} but got {actual_path.stat().st_size}."
        )
    return actual_path
