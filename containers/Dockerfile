# syntax=docker/dockerfile:1

# The pinned runtime environment for this cache.
#
# Everything shared comes from the base image: Debian, git-annex, the virtual environment, the
# `dandi_cache_utils` library that `code/update.py` imports, and the vendored `update_pipeline.sh`
# that CI extracts and runs on the runner.
#
# The `:latest` tag rather than `:nwb`, because this cache reads the archive's own manifests over S3 and never opens an NWB file. That tag carries boto3 and the DANDI API and stops there.
#
# The image holds only the environment, not this cache's code. The code is mounted at run time, so
# a single image serves any revision of it.
FROM ghcr.io/dandi-cache/dandi-cache-utils:latest

# The source label associates the image on the GitHub Container Registry with this repository.
LABEL org.opencontainers.image.source="https://github.com/dandi-cache/dandiset-id-to-number-of-assets"
LABEL org.opencontainers.image.description="The pinned runtime environment for the DANDI Cache dandiset-id-to-number-of-assets update pipeline."

CMD ["python", "--version"]
