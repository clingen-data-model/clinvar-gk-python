# clinvar-gk-python

Project for reading and normalizing ClinVar variants into GA4GH GKS forms.

## Setup

### Prerequisites

1. **Docker** - Required to run the variation-normalization services
2. **Python 3.11+** - Required for the main application
3. **SeqRepo database** - Local sequence repository

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

This will start:
- **UTA database** (port 5432): Universal Transcript Archive for transcript mapping
- **Gene Normalizer database** (port 8000): Gene normalization service
- **Variation Normalizer API** (port 8001): Variation normalization service

**Note on Port Conflicts**: If you already have services running on these ports, you can modify the port mappings in `variation-normalizer-compose.yaml`:
- For UTA database: Change `5432:5432` to `5433:5432` (or another available port)
- For Gene Normalizer: Change `8000:8000` to `8002:8000` (or another available port)
- For Variation Normalizer API: Change `8001:80` to `8003:80` (or another available port)

### Environment Configuration

Set up the required environment variables. You can use the provided `env.sh` as a reference:

```bash
# SeqRepo configuration - Update path to your local SeqRepo installation
export SEQREPO_ROOT_DIR=/Users/kferrite/dev/data/seqrepo/2024-12-20
export SEQREPO_DATAPROXY_URL=seqrepo+file://${SEQREPO_ROOT_DIR}

# Database URLs (using the Docker compose services)
export UTA_DB_URL=postgresql://anonymous:anonymous@localhost:5432/uta/uta_20241220
export GENE_NORM_DB_URL=http://localhost:8000
```

**Important**: If you modified the ports in the compose file, update the corresponding environment variables accordingly (e.g., change `5432` to `5433` in `UTA_DB_URL` if you changed the UTA port).

Or source the provided environment file:
```bash
source env.sh
```

### Python Installation

Install the project and its dependencies:

```bash
pip install -e '.[dev]'
```

## Running

### Basic Usage

Process a ClinVar variants file:

```bash
python clinvar_gk_pilot/main.py --filename gs://clinvar-gks/2025-07-06/dev/vi.json.gz --parallelism 4
```

### Alternative Entry Point

You can also use the installed command:

```bash
clinvar-gk-pilot --filename gs://clinvar-gks/2025-07-06/dev/vi.json.gz --parallelism 4
```

### Command Line Options

- `--filename`: Input file path (supports local files and gs:// URLs)
- `--parallelism`: Number of worker processes for parallel processing (default: 1)
- `--liftover`: Enable liftover functionality for genomic coordinate conversion

### Example Commands

Process a local file:
```bash
clinvar-gk-pilot --filename sample-input.ndjson.gz --parallelism 2
```

Process a file from Google Cloud Storage:
```bash
clinvar-gk-pilot --filename gs://clinvar-gks/2025-07-06/dev/vi.json.gz --parallelism 4
```

Process with liftover enabled:
```bash
clinvar-gk-pilot --filename gs://clinvar-gks/2025-07-06/dev/vi.json.gz --parallelism 2 --liftover
```

### Important Notes on Liftover

When using the `--liftover` option, the application will send queries to the UTA PostgreSQL database for genomic coordinate conversion. Due to Docker's default shared memory constraints, high parallelism combined with liftover can cause out-of-memory errors.

**Recommendations:**
- Keep `--parallelism` on the lower side (2-4) when using `--liftover`
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
- black (code formatting)
- isort (import sorting)  
- ruff (fast linter)
- pylint (code analysis)
