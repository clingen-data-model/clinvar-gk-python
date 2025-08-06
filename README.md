# clinvar-gk-python

Project for reading and normalizing ClinVar variants into GA4GH GKS forms.

## Setup

### Prerequisites

1. **Docker** (or podman) - Required to run the variation-normalization services
2. **Python 3.11+** - Required for the main application
3. **SeqRepo database** - Local sequence repository
4. **UTA database** - Local Universal Transcript Archive (only needed for liftover)

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

This project requires several database services that can be easily set up using the Docker compose configuration from the variation-normalization project.

1. Download the compose.yaml file from variation-normalization v0.15.0 (matching the version in pyproject.toml):

```bash
curl -o variation-normalizer-compose.yaml https://raw.githubusercontent.com/cancervariants/variation-normalization/0.15.0/compose.yaml
```

2. Start the required services:

```bash
docker compose -f variation-normalizer-compose.yaml up -d
```
(*or `uvx podman-compose` for podman*)

This will start:
- **UTA database** (port 5432): Universal Transcript Archive for transcript mapping
- **Gene Normalizer database** (port 8000): Gene normalization service
- **Variation Normalizer API** (port 8001): Variation normalization service

**Note on Port Conflicts**: If you already have services running on these ports, you can modify the port mappings in `variation-normalizer-compose.yaml`:
- For UTA database: Change `5432:5432` to `5433:5432` (or another available port)
- For Gene Normalizer: Change `8000:8000` to `8002:8000` (or another available port)
- For Variation Normalizer API: Change `8001:80` to `8003:80` (or another available port)

Verify containers are running on the desired ports, e.g. the UTA postgres is running on host port 5433 and the gene normalizer db is on port 8000:
```
docker ps -a | grep 'uta\|gene-norm'
```

### Environment Configuration

Set up the required environment variables. You can use the provided `env.sh` as a reference:

```bash
# SeqRepo configuration - Update path to your local SeqRepo installation
export SEQREPO_ROOT_DIR=/usr/local/share/seqrepo/2024-12-20
export SEQREPO_DATAPROXY_URL=seqrepo+file://${SEQREPO_ROOT_DIR}

# Database URLs (using the Docker compose services)
export UTA_DB_URL=postgresql://anonymous:anonymous@localhost:5432/uta/uta_20241220
export GENE_NORM_DB_URL=http://localhost:8000
```

**Important**: If you modified the ports in the compose file, update the corresponding environment variables accordingly (e.g., change `5432` to `5433` in `UTA_DB_URL` if you changed the UTA port).

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
