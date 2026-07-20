# clinvar-gk-python

Project for reading and normalizing ClinVar variants into GA4GH GKS forms.

## Setup

### Prerequisites

1. **Docker** (or podman) - Required to run the UTA and Gene Normalizer database services
1. **Python 3.11+** - Required for the main application
1. **SeqRepo database** - Local sequence repository
1. **UTA database** - Universal Transcript Archive (required; also used for liftover)

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

### Database Services Setup

This project requires two database services (UTA and Gene Normalizer) that can be set up using the `variation-normalizer-compose.yaml` included in this repository. That file is based on the [variation-normalization 0.15.0 compose file](https://raw.githubusercontent.com/cancervariants/variation-normalization/0.15.0/compose.yaml) and is maintained here with this project's local setup changes. The compose file also includes a Variation Normalizer API service, but this project uses the variation-normalization Python library directly and does not require the API container.

Before starting, set `SEQREPO_ROOT_DIR` to your versioned local SeqRepo directory. The Compose file mounts its parent directory read-only; do not edit the Compose file for a machine-specific path.

```bash
export SEQREPO_ROOT_DIR=/usr/local/share/seqrepo/2024-12-20
```

1. Create the external volume required by the UTA service:

```bash
docker volume create uta_vol
```
(*or `podman volume create uta_vol` for podman*)

1. Download the `uta_20241220.pgd.gz` snapshot from the [UTA local-installation instructions](https://github.com/biocommons/uta#installing-uta-locally) in a browser. The UTA download site requires human verification. Set `UTA_SNAPSHOT_PATH` to its absolute path:

```bash
export UTA_SNAPSHOT_PATH=/path/to/uta_20241220.pgd.gz
```

1. Initialize the UTA volume and start the required services. The initialization override is required only for this first start:

```bash
docker compose \
  -f variation-normalizer-compose.yaml \
  -f variation-normalizer-uta-init.yaml up -d
```
(*or `podman compose -f variation-normalizer-compose.yaml -f variation-normalizer-uta-init.yaml up -d` for podman*)

This will start:
- **UTA database** (port 5434): Universal Transcript Archive for transcript mapping
- **Gene Normalizer database** (port 8000): Gene normalization service
- **Variation Normalizer API** (port 8001): Not required by this project, but started by the compose file

#### Initialize UTA data

On the first start with a new `uta_vol`, the UTA image restores the snapshot and then runs this project's `uta-setup.sql` initialization script. This can take several minutes (longer under architecture emulation, e.g. amd64 images on Apple Silicon). Wait for the UTA logs to report `You may now connect to uta`, then stop following the logs with <kbd>Ctrl</kbd>-<kbd>C</kbd>:

```bash
docker compose -f variation-normalizer-compose.yaml logs -f uta
```
(*or `podman compose -f variation-normalizer-compose.yaml logs -f uta` for podman*)

Confirm that both the restored UTA schema and this project's additional setup are present:

```bash
psql -XAt postgres://anonymous@localhost:5434/uta -c "
SELECT
  (SELECT count(*) = 329090 FROM uta_20241220.transcript) AS transcript_restored,
  to_regclass('uta_20241220.genomic') IS NOT NULL AS genomic_table_present,
  (SELECT count(*) = 3
     FROM pg_indexes
    WHERE schemaname = 'uta_20241220'
      AND tablename = 'genomic'
      AND indexname IN ('alt_pos_index', 'gene_alt_index', 'alt_ac_index'))
    AS genomic_indexes_present;"
# Expected output: t|t|t
```

If any value is `f`, the volume is incomplete (for example, it was restored using the prior snapshot-only procedure). PostgreSQL does not rerun initialization scripts for an existing data directory, so recreate the local UTA volume and initialize it again. This removes only the local UTA data:

```bash
docker compose -f variation-normalizer-compose.yaml down
docker volume rm uta_vol
docker volume create uta_vol
```
(*Use `podman compose` and `podman volume` instead when using podman.*)

Then repeat the snapshot download and two-file initialization command above.

The image consumes the snapshot and runs `uta-setup.sql` only for a new `uta_vol`; both are skipped when reusing an existing volume. Once the verification reports `t|t|t`, start the services normally—without `UTA_SNAPSHOT_PATH` or the initialization override. Base Compose starts assume this initialized UTA volume:

```bash
docker compose -f variation-normalizer-compose.yaml up -d
```
(*or `podman compose -f variation-normalizer-compose.yaml up -d` for podman*)

For complete upstream setup and troubleshooting guidance, see the [UTA local-installation instructions](https://github.com/biocommons/uta#installing-uta-locally).

#### Port Conflicts

Before starting the services, check for existing containers using the same ports:

```bash
docker ps -a | grep -E '5434|8000|8001'
```

If you have conflicts, you can modify the port mappings in `variation-normalizer-compose.yaml`:

- For UTA database: Change `5434:5432` to another available port (e.g., `5433:5432`)
- For Gene Normalizer: Change `8000:8000` to `8002:8000` (or another available port)
- For Variation Normalizer API: Change `8001:80` to `8003:80` (or another available port)

Verify the required containers are running:
```bash
docker ps -a | grep 'uta\|gene-norm'
```

### Environment Configuration

Set up the required environment variables:

```bash
# SeqRepo configuration - Update path to your local SeqRepo installation
export SEQREPO_ROOT_DIR=/usr/local/share/seqrepo/2024-12-20
export SEQREPO_DATAPROXY_URL=seqrepo+file://${SEQREPO_ROOT_DIR}

# Required by the hgvs library to use local SeqRepo instead of fetching
# sequences from NCBI eutils over the network (which is very slow)
export HGVS_SEQREPO_DIR=${SEQREPO_ROOT_DIR}

# Database URLs (using the Docker compose services)
export UTA_DB_URL=postgresql://anonymous:anonymous@localhost:5434/uta/uta_20241220
export GENE_NORM_DB_URL=http://localhost:8000

# Dummy AWS credentials required by the Gene Normalizer local DynamoDB
export AWS_ACCESS_KEY_ID=DUMMYIDEXAMPLE
export AWS_SECRET_ACCESS_KEY=DUMMYEXAMPLEKEY
export AWS_DEFAULT_REGION=us-east-2
```

**Important**: If you modified the ports in the compose file, update the corresponding environment variables accordingly (e.g., change `5432` to `5433` in `UTA_DB_URL` if you changed the UTA port).

The AWS credentials are not real credentials — they are dummy values required by the local DynamoDB instance used by the Gene Normalizer. Without them, the application will fail with `NoCredentialsError` or a `302` error when connecting to the Gene Normalizer database.

### Python Installation

Install the project and its dependencies:

```bash
pip install -e '.[dev]'
```

## Running

### Basic Usage

The `clinvar_gk_pilot` main entrypoint can automatically handle downloading `gs://` URLs. It places the file in a directory called `buckets`, with the bucket name and the same path prefix. e.g. `gs://clinvar-gks/2025-07-06/dev/vi.json.gz` gets automatically downloaded to `buckets/clinvar-gks/2025-07-06/dev/vi.json.gz`. The input file is expected to be compressed with GZIP and in JSONL/NDJSON format with each line being a JSON object.

The output is written to the same path as the local input file, but under an `output` directory in the current working directory. e.g. for the input filename `gs://clinvar-gks/2025-07-06/dev/vi.json.gz`, the file will be auto-cached to `buckets/clinvar-gks/2025-07-06/dev/vi.json.gz` and the output will be written to `output/buckets/clinvar-gks/2025-07-06/dev/vi.json.gz`


Process a ClinVar variant-identity file:

```bash
python clinvar_gk_pilot/main.py --filename gs://clinvar-gks/2025-07-06/dev/vi.json.gz --parallelism 4
```

### Command Line Options

- `--filename`: Input file path (supports local files and gs:// URLs)
- `--parallelism`: Number of worker processes for parallel processing (default: 1)
- `--liftover`: Enable liftover functionality for genomic coordinate conversion

### Example Commands

Process a local file:
```bash
clinvar-gk-pilot --filename sample-input.ndjson.gz --parallelism 4
```

Process a file from Google Cloud Storage:
```bash
clinvar-gk-pilot --filename gs://clinvar-gks/2025-07-06/dev/vi.json.gz --parallelism 4
```

### Release Processing Script

The `misc/clinvar-vrsification` script is a convenience wrapper for processing a ClinVar release and uploading the results back to GCS. It takes a release date as its only argument:

```bash
./misc/clinvar-vrsification 2025-07-06
```

This will:

1. Download and normalize `gs://clinvar-gks/<date>/dev/vi.jsonl.gz` with parallelism 2 (no liftover)
1. Log output to `<date>-noliftover.log`
1. Upload the result to `gs://clinvar-gks/<date>/dev/vi-normalized-no-liftover.jsonl.gz`

Requires `gcloud` CLI configured with write access to the `clinvar-gks` bucket.

### Parallelism

Parallelism is configurable and uses python multiprocessing and multiprocessing queues. Some parallelism is significantly beneficial but since there is interprocess communication overhead and they are hitting the same filesystem there can be diminishing returns. On a Macbook Pro with 16 cores, setting parallelism to 4-6 provides clear benefit, but exceeding 10 saturates the machine and may be counterproductive. The code will partition the input file into `<parallelism>` number of files and each worker will process one, and then the outputs will be combined.

If parallelism is enabled, each worker also monitors its child process, terminates excessively long tasks, and add an error annotation to the output record for that variant indicating that it exceeded the time limit.


### Important Notes on Liftover

When using the `--liftover` option, the application will send queries to the UTA PostgreSQL database for genomic coordinate conversion. Due to Docker's default shared memory constraints, high parallelism combined with liftover can cause out-of-memory errors.

**Recommendations:**
- Keep `--parallelism` on the lower side (2-4) when using `--liftover` and when UTA is in docker
- Alternatively, increase the `shm_size` for the UTA container in `variation-normalizer-compose.yaml`:

```yaml
services:
  uta:
    # ... other configuration
    shm_size: 256m  # Add this line to increase shared memory to 256MB
```

## Development


### Testing

Run the test suite:
```bash
pytest
```

Run specific tests:
```bash
pytest test/test_cli.py::test_parse_args
```

### Code Quality

Check and fix code quality issues:
```bash
# Check code quality
./lint.sh

# Apply automatic fixes
./lint.sh apply
```

The lint script runs:
- black, isort, ruff, pylint
