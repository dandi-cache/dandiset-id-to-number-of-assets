# syntax=docker/dockerfile:1

# The container is the project's pinned, reproducible runtime environment and the official way to run the pipeline.
# The loose dependencies declared in envs/pyproject.toml are resolved fresh at build time, and the resulting image (by digest) is the lock.
# As such, there is no lockfile in the repository to hold in sync.
# uv is intentionally not used inside the image; it stays an outside-the-container convenience for running locally while debugging (`uv run --project envs python code/update.py`).
#
# The image holds only the environment, not the code.
# The code is supplied at run time (checked out or mounted), so a single image serves any revision of the code.
#
# NeuroDebian trixie (Debian 13) is the base layer.
# it provides Python and a recent git-annex-standalone, which DataLad requires for the annex-backed dataset and its provenance.
FROM neurodebian:trixie

# The source label associates the image on the GitHub Container Registry with this repository.
LABEL org.opencontainers.image.source="https://github.com/dandi-cache/<cache-name>"
LABEL org.opencontainers.image.description="The pinned runtime environment for the DANDI Cache <cache-name> update pipeline."

# git-annex (for DataLad / annex provenance), Python, and the basics for cloning and TLS.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        git \
        git-annex-standalone \
        python3 \
        python3-pip \
        python3-venv \
    && rm -rf /var/lib/apt/lists/*

ENV VIRTUAL_ENV=/opt/venv \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Debian's system interpreter is externally managed (PEP 668), so install into a dedicated virtual environment rather than forcing pip with --break-system-packages.
# this also keeps our dependencies cleanly separated from the apt-managed Python packages.
RUN python3 -m venv "${VIRTUAL_ENV}"
ENV PATH="${VIRTUAL_ENV}/bin:${PATH}"

COPY envs/pyproject.toml /tmp/build/pyproject.toml
RUN pip install /tmp/build \
    && rm -rf /tmp/build

CMD ["python", "--version"]
