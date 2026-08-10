import argparse
import concurrent.futures
import functools
import json
import pathlib

import boto3
import botocore
import botocore.config
import botocore.exceptions

# This cache is first-in-chain: it has no upstream `sourcedata` and instead pulls its inputs
# directly from the public DANDI archive S3 bucket. Every Dandiset has a `draft` version, whose
# `assets.jsonld` manifest is a JSON array holding one entry per asset and is regenerated the
# moment an asset is added or removed -- published versions are frozen snapshots taken at
# publish time, so `draft` alone reflects the current contents of a Dandiset.
#
# The number of assets is taken as the length of that array rather than from the
# `assetsSummary.numberOfFiles` field of the far smaller `dandiset.jsonld`: for `draft`
# versions that summary is frequently stale or absent (across a random sample of 40 Dandisets
# it disagreed with the manifest for most of the non-empty ones, usually reading 0), whereas
# the manifest is the archive's own listing of the assets themselves.
#
# The archive also publishes the same manifest as `assets.yaml`, which is deliberately ignored:
# JSON parses orders of magnitude faster than YAML.
_BUCKET = "dandiarchive"
_REGION = "us-east-2"
_DANDISETS_PREFIX = "dandisets/"
_DRAFT_MANIFEST_SUFFIX = "/draft/assets.jsonld"

# Testing mode processes only this many Dandisets and writes to its own designated file
# (`derivatives/testing.jsonl`), leaving the real cache untouched.
_TESTING_LIMIT = 10
_CACHE_FILE_NAME = "dandiset_id_to_number_of_assets.jsonl"
_TESTING_FILE_NAME = "testing.jsonl"


def _build_s3_client(max_pool_connections: int = 10) -> "botocore.client.BaseClient":
    # `dandiarchive` is a public bucket, so requests are sent unsigned (anonymous). The
    # connection pool must hold one connection per download worker, or the surplus workers
    # redo the TCP/TLS handshake on every request.
    config = botocore.config.Config(
        signature_version=botocore.UNSIGNED,
        max_pool_connections=max_pool_connections,
        retries={"mode": "standard"},
    )
    return boto3.client("s3", region_name=_REGION, config=config)


def _iter_dandiset_ids(s3_client: "botocore.client.BaseClient"):
    """Yield every Dandiset ID (its folder name) under `dandisets/`, in lexicographic order."""
    paginator = s3_client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=_BUCKET, Prefix=_DANDISETS_PREFIX, Delimiter="/"):
        for entry in page.get("CommonPrefixes", []):
            yield entry["Prefix"].removeprefix(_DANDISETS_PREFIX).rstrip("/")


def _count_assets(s3_client: "botocore.client.BaseClient", dandiset_id: str) -> tuple[str, int] | None:
    key = f"{_DANDISETS_PREFIX}{dandiset_id}{_DRAFT_MANIFEST_SUFFIX}"
    try:
        response = s3_client.get_object(Bucket=_BUCKET, Key=key)
    except botocore.exceptions.ClientError as error:
        error_code = error.response.get("Error", {}).get("Code", "")
        # Embargoed Dandisets list their `draft` manifest publicly but deny anonymous reads
        # (AccessDenied); a Dandiset can also have no draft manifest at all, or have it deleted
        # between listing and fetching (NoSuchKey). Both are expected upstream states, not
        # pipeline failures, so skip.
        if error_code in ("AccessDenied", "NoSuchKey"):
            print(f"Skipping inaccessible manifest `{key}` ({error_code}).", flush=True)
            return None
        raise

    body = response["Body"].read()
    all_asset_metadata = json.loads(body) if body.strip() else []

    # The manifest is a JSON array with one entry per asset, so its length is the asset count.
    # A manifest that is not an array would otherwise be counted silently and wrongly (a mapping
    # would yield its number of keys), so a layout change is made to fail loudly instead.
    if not isinstance(all_asset_metadata, list):
        message = (
            f"\nThe manifest `{key}` is not a JSON array of assets.\n"
            "The DANDI archive's manifest layout may have changed.\n"
        )
        raise ValueError(message)

    return dandiset_id, len(all_asset_metadata)


def _collect_counts(s3_client: "botocore.client.BaseClient", max_workers: int, testing: bool) -> dict[str, int]:
    if testing:
        # Testing run: count manifests one at a time and stop as soon as `_TESTING_LIMIT`
        # Dandisets have been counted, so the run is fast and does not enumerate the entire
        # `dandisets/` prefix.
        counts: dict[str, int] = {}
        for dandiset_id in _iter_dandiset_ids(s3_client):
            if result := _count_assets(s3_client, dandiset_id):
                counts[result[0]] = result[1]
            if len(counts) >= _TESTING_LIMIT:
                break
        return counts

    # Full run: count every Dandiset's draft manifest concurrently.
    counts = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        count_assets = functools.partial(_count_assets, s3_client)
        for result in executor.map(count_assets, _iter_dandiset_ids(s3_client)):
            if result:
                counts[result[0]] = result[1]
    return counts


def _load_previous_cache(cache_file_path: pathlib.Path) -> dict[str, int]:
    """Read the previous run's cache back into memory (empty on a bootstrap run)."""
    previous_cache: dict[str, int] = {}
    if not cache_file_path.exists():
        return previous_cache

    with cache_file_path.open() as file_stream:
        for line in file_stream:
            if stripped_line := line.strip():
                previous_cache.update(json.loads(stripped_line))
    return previous_cache


def _run(base_directory: pathlib.Path, max_workers: int, testing: bool) -> None:
    s3_client = _build_s3_client(max_pool_connections=max_workers)

    fresh_counts = _collect_counts(s3_client, max_workers=max_workers, testing=testing)
    if len(fresh_counts) == 0:
        message = (
            f"\nNo draft asset manifests could be read under `s3://{_BUCKET}/{_DANDISETS_PREFIX}`.\n"
            "The DANDI archive bucket may be unreachable or its layout may have changed.\n"
        )
        raise RuntimeError(message)

    derivatives_directory = base_directory / "derivatives"
    derivatives_directory.mkdir(parents=True, exist_ok=True)
    # Testing runs read from and write to their own designated file, so the real cache is
    # never touched.
    output_file_path = derivatives_directory / (_TESTING_FILE_NAME if testing else _CACHE_FILE_NAME)

    # The cache is accumulative: a Dandiset's count is refreshed whenever its draft manifest is
    # readable, and its last known count is retained if the Dandiset later becomes embargoed or
    # otherwise unreadable, rather than being dropped from the map.
    dandiset_id_to_number_of_assets = _load_previous_cache(output_file_path)
    dandiset_id_to_number_of_assets.update(fresh_counts)

    # One JSON value per line: `{"<dandiset_id>": <number_of_assets>}`.
    with output_file_path.open(mode="w") as file_stream:
        for dandiset_id in sorted(dandiset_id_to_number_of_assets):
            record = {dandiset_id: dandiset_id_to_number_of_assets[dandiset_id]}
            file_stream.write(f"{json.dumps(record)}\n")


if __name__ == "__main__":
    default_base_directory = pathlib.Path(__file__).parent.parent

    parser = argparse.ArgumentParser(description="Update the dandiset-id-to-number-of-assets DANDI cache.")
    parser.add_argument(
        "--base-directory",
        type=pathlib.Path,
        default=default_base_directory,
        help=(
            "The directory containing the `derivatives` directory. "
            "Set to the mounted dataset path when run inside the pipeline container; "
            "defaults to the repository root."
        ),
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=16,
        help="Number of concurrent S3 download workers used to fetch the draft asset manifests.",
    )
    parser.add_argument(
        "--testing",
        action="store_true",
        help=(
            f"Run in testing mode: process only the first {_TESTING_LIMIT} Dandisets from S3 "
            f"and read/write `derivatives/{_TESTING_FILE_NAME}` instead of the real cache, "
            "leaving it untouched. Omit for a complete update."
        ),
    )
    args = parser.parse_args()

    _run(base_directory=args.base_directory, max_workers=args.max_workers, testing=args.testing)
