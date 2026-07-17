# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Python project that converts ClinVar variant-identity data into GA4GH GKS (Genomic Knowledge Standards) forms. The project processes NDJSON files containing ClinVar variants and converts them to VRS (Variation Representation Specification) format using the variation-normalization library.

## Common Development Commands

### Installation
```bash
pip install -e '.[dev]'
```

### Testing
```bash
pytest
pytest test/test_cli.py::test_parse_args  # Run specific test
```

### Code Quality
```bash
./lint.sh                # Check code quality (black, isort, ruff, pylint)
./lint.sh apply          # Apply automatic fixes
```

### Running the Application
```bash
# Process a local file
clinvar-gk-pilot --filename sample-input.ndjson.gz --parallelism 4

# Process a file from Google Cloud Storage
clinvar-gk-pilot --filename gs://clinvar-gks/2025-07-06/dev/vi.json.gz --parallelism 4

# Enable liftover for genomic coordinate conversion
clinvar-gk-pilot --filename input.ndjson.gz --parallelism 2 --liftover
```

## Architecture

### Core Processing Pipeline
- **Input**: GZIP-compressed NDJSON files with ClinVar variant data
- **Processing**: Converts variants to VRS format using variation-normalization library
- **Output**: GZIP-compressed NDJSON files with input/output pairs

### Key Components
- `clinvar_gk_pilot/main.py`: Core processing logic with multiprocessing support
- `clinvar_gk_pilot/cli.py`: Command-line argument parsing
- `clinvar_gk_pilot/gcs.py`: Google Cloud Storage download utilities
- Uses variation-normalization library for VRS conversion
- Supports three variant types: Allele, CopyNumberChange, CopyNumberCount

### Parallel Processing
- Uses Python multiprocessing with configurable worker count
- Files are partitioned by line count across workers
- Each worker runs with timeout protection (10 seconds per variant)
- Workers use persistent async event loops for variation-normalization queries

## Required Environment Variables

```bash
# SeqRepo configuration
export SEQREPO_ROOT_DIR=/usr/local/share/seqrepo/2024-12-20
export SEQREPO_DATAPROXY_URL=seqrepo+file://${SEQREPO_ROOT_DIR}

# Database URLs (from Docker compose services)
export UTA_DB_URL=postgresql://anonymous:anonymous@localhost:5434/uta/uta_20241220
export GENE_NORM_DB_URL=http://localhost:8000
```

## External Dependencies

### Required Services
The repository includes `variation-normalizer-compose.yaml` for the required Docker services. For a fresh `uta_vol`, download `uta_20241220.pgd.gz` following the [UTA local-installation instructions](https://github.com/biocommons/uta#installing-uta-locally), then set its absolute path and include the initialization override:

```bash
export UTA_SNAPSHOT_PATH=/path/to/uta_20241220.pgd.gz
docker compose \
  -f variation-normalizer-compose.yaml \
  -f variation-normalizer-uta-init.yaml up -d
```

This starts:
- UTA database (port 5434): Universal Transcript Archive
- Gene Normalizer database (port 8000): Gene normalization service
- Variation Normalizer API (port 8001): Variation normalization service

Do not replace the checked-in compose file with the upstream variation-normalization compose file. Configure the local SeqRepo mount in the checked-in file. For a new UTA volume, the UTA image consumes the snapshot and automatically runs `uta-setup.sql`. Subsequent starts use only `variation-normalizer-compose.yaml`. See the [README UTA setup instructions](README.md#database-services-setup) for completion verification and recovery of a snapshot-only volume.

### Memory Considerations
When using `--liftover` with high parallelism, increase Docker shared memory:
```yaml
services:
  uta:
    shm_size: 256m
```

## File Structure Notes

- Input files: Expected to be GZIP-compressed NDJSON format
- Output location: Files written to `output/` directory with same path structure
- GCS files: Auto-downloaded to `buckets/` directory with bucket name preserved
- Logs: Created per-worker as `{input_file}.log`
