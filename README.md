# clinvar-gk-python
Project for reading and normalizing ClinVar variants into GA4GH GKS forms


## Installation

From git directly:
```
pip install git+https://github.com/clingen-data-model/clinvar-gk-python
```

For development:
```
git clone https://github.com/clingen-data-model/clinvar-gk-python
cd clinvar-gk-python
pip install -e '.[dev]'
```

## Configuration

A SeqRepo and UTA instance should be downloaded and/or running locally.

The preferred method is to download a SeqRepo DB dir to your local filesystem, and to run the UTA docker image.

See: https://github.com/biocommons/anyvar?tab=readme-ov-file#required-dependencies

The docker compose file in `vrs-python` or `anyvar` can be used / trimmed down to run a UTA container from a snapshot and bind it to an available local port. If you have postgresql running natively on your system on port 5432 you need to modify the compose file in order to ensure the left hand side of the UTA port field is some other port like 5433. And then make sure you use that port number in the `UTA_DB_URL` variable below.

e.g. In the file below change the left hand side of `.services.uta.ports[0]` to `127.0.0.1:5433`.

https://github.com/ga4gh/vrs-python/blob/main/docker-compose.yml

Then run with podman (or docker) compose:
```
uvx podman-compose -f ./docker-compose.yml up
```

Verify the UTA postgres is running on host port 5433:
```
podman ps -a | grep uta
```

## Using

Point the tool at a SeqRepo database directory at a `seqrepo-rest-service` HTTP URL.

And to a postgresql server containing the UTA database.

The `clinvar_gk_pilot` main entrypoint can automatically handle downloading `gs://` URLs. It places the file in a directory called `buckets`, with the bucket name and the same path prefix. e.g. `gs://clinvar-gks/2025-07-06/dev/vi.json.gz` gets automatically downloaded to `buckets/clinvar-gks/2025-07-06/dev/vi.json.gz`.

```sh
export UTA_DB_URL=postgresql://anonymous@localhost:5433/uta/uta_20241220
export SEQREPO_DATAPROXY_URL='seqrepo+file:///Users/kferrite/dev/data/seqrepo/2024-12-20'
python clinvar_gk_pilot/main.py --filename gs://clinvar-gks/2025-07-06/dev/vi.json.gz --parallelism 4 2>&1 | tee 2025-07-06.log
```

Parallelism is configurable and uses python multiprocessing and multiprocessing queues. Some parallelism is significantly beneficial but since there is interprocess communication overhead and they are hitting the same database there can be diminishing returns. On a Macbook Pro with 16 cores, setting parallelism to 4-6 provides clear benefit, but exceeding 10 saturates the machine and may be counterproductive. The code will partition the input file into `<parallelism>` number of files and each worker will process one, and then the outputs will be combined.

If parallelism is enabled, each worker also monitors its child process and terminates excessively long tasks.

The output is written to the same path as the local input file, but under an `output` directory in the current working directory. e.g. for the input filename `gs://clinvar-gks/2025-07-06/dev/vi.json.gz`, the file will be auto-cached to `buckets/clinvar-gks/2025-07-06/dev/vi.json.gz` and the output will be written to `output/buckets/clinvar-gks/2025-07-06/dev/vi.json.gz`
