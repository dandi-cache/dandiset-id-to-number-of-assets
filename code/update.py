import argparse
import collections.abc
import concurrent.futures
import functools
import itertools
import json
import pathlib

import boto3
import botocore
import botocore.config
import botocore.exceptions
import ijson

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

# Field names of a cache entry. The manifest's S3 modification time is published alongside the
# count: it tells a consumer how current that count is, and it is what lets a run skip the
# Dandisets whose draft manifest has not been rewritten since the previous run (see `_run`).
_NUMBER_OF_ASSETS_FIELD = "number_of_assets"
_LAST_MODIFIED_FIELD = "manifest_last_modified"

# The ijson events that open a top-level element of the manifest array. Asset entries are always
# JSON objects (`start_map`); the scalar and nested-array events are listed only so that a
# hypothetical change in the manifest layout is still counted rather than silently ignored.
_ELEMENT_START_EVENTS = frozenset(
    {"start_map", "start_array", "null", "boolean", "integer", "double", "number", "string"}
)

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


def _list_draft_manifests(s3_client: "botocore.client.BaseClient") -> dict[str, tuple[str, str]]:
    """
    Map every Dandiset ID to its draft asset manifest's key and S3 modification time.

    A single recursive listing of `dandisets/` covers the whole archive in a handful of requests
    and carries the modification times with it, so the far more expensive manifest downloads can
    be restricted to the Dandisets that actually changed. Insertion order is the lexicographic
    listing order, which the rest of the run relies on for a deterministic testing slice.
    """
    draft_manifests: dict[str, tuple[str, str]] = {}
    paginator = s3_client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=_BUCKET, Prefix=_DANDISETS_PREFIX):
        for entry in page.get("Contents", []):
            key = entry["Key"]
            if not key.endswith(_DRAFT_MANIFEST_SUFFIX):
                continue
            # Key layout: `dandisets/<dandiset_id>/draft/assets.jsonld`.
            dandiset_id = key.split("/")[1]
            draft_manifests[dandiset_id] = (key, entry["LastModified"].isoformat())
    return draft_manifests


def _count_assets(
    s3_client: "botocore.client.BaseClient", dandiset_id_and_key: tuple[str, str]
) -> tuple[str, int] | None:
    dandiset_id, key = dandiset_id_and_key
    try:
        response = s3_client.get_object(Bucket=_BUCKET, Key=key)
    except botocore.exceptions.ClientError as error:
        error_code = error.response.get("Error", {}).get("Code", "")
        # Embargoed Dandisets list their `draft` manifest publicly but deny anonymous reads
        # (AccessDenied); a manifest can also be deleted between listing and fetching
        # (NoSuchKey). Both are expected upstream states, not pipeline failures, so skip.
        if error_code in ("AccessDenied", "NoSuchKey"):
            print(f"Skipping inaccessible manifest `{key}` ({error_code}).", flush=True)
            return None
        raise

    # The elements are counted off the response stream instead of being materialized: the
    # largest draft manifests are well over a hundred megabytes of JSON, which `json.loads`
    # would expand into gigabytes of Python objects -- once per concurrent worker. Streaming
    # keeps the memory per worker flat regardless of the manifest's size.
    with response["Body"] as body_stream:
        events = ijson.parse(body_stream)
        first_event = next(events, None)
        if first_event is None or first_event[1] != "start_array":
            message = (
                f"\nThe manifest `{key}` is not a JSON array of assets.\n"
                "The DANDI archive's manifest layout may have changed.\n"
            )
            raise ValueError(message)
        number_of_assets = sum(1 for prefix, event, _ in events if prefix == "item" and event in _ELEMENT_START_EVENTS)

    return dandiset_id, number_of_assets


def _load_previous_cache(cache_file_path: pathlib.Path) -> dict[str, dict[str, object]]:
    """Read the previous run's cache back into memory (empty on a bootstrap run)."""
    previous_cache: dict[str, dict[str, object]] = {}
    if not cache_file_path.exists():
        return previous_cache

    with cache_file_path.open() as file_stream:
        for line in file_stream:
            if stripped_line := line.strip():
                previous_cache.update(json.loads(stripped_line))
    return previous_cache


def _record_counts(
    dandiset_id_to_number_of_assets: dict[str, dict[str, object]],
    results: collections.abc.Iterable[tuple[str, int] | None],
    draft_manifests: dict[str, tuple[str, str]],
) -> int:
    """Fold the freshly counted manifests into the accumulated mapping, returning how many landed."""
    number_of_updates = 0
    for result in results:
        if result is None:
            continue
        dandiset_id, number_of_assets = result
        _, last_modified = draft_manifests[dandiset_id]
        dandiset_id_to_number_of_assets[dandiset_id] = {
            _NUMBER_OF_ASSETS_FIELD: number_of_assets,
            _LAST_MODIFIED_FIELD: last_modified,
        }
        number_of_updates += 1
    return number_of_updates


def _run(base_directory: pathlib.Path, max_workers: int, testing: bool) -> None:
    # ijson selects its parsing backend at import time and silently falls back to a pure-Python
    # one when the compiled `yajl2_c` extension is unavailable, which would turn a run of tens of
    # seconds into one of many minutes. Log the selected backend so such a regression is visible.
    print(f"Counting with the ijson `{ijson.backend}` backend.", flush=True)

    s3_client = _build_s3_client(max_pool_connections=max_workers)

    draft_manifests = _list_draft_manifests(s3_client)
    if len(draft_manifests) == 0:
        message = (
            f"\nNo draft asset manifests found under `s3://{_BUCKET}/{_DANDISETS_PREFIX}`.\n"
            "The DANDI archive bucket may be unreachable or its layout may have changed.\n"
        )
        raise RuntimeError(message)

    if testing:
        # Testing run: keep only the first few Dandisets, so the run is fast but still exercises
        # the real processing logic end to end.
        draft_manifests = dict(itertools.islice(draft_manifests.items(), _TESTING_LIMIT))

    derivatives_directory = base_directory / "derivatives"
    derivatives_directory.mkdir(parents=True, exist_ok=True)
    # Testing runs read from and write to their own designated file, so the real cache is
    # never touched.
    output_file_path = derivatives_directory / (_TESTING_FILE_NAME if testing else _CACHE_FILE_NAME)

    # The cache is accumulative: the pipeline runs on a clone of the persistent `derivatives`
    # branch, so the previous run's cache is already present here. Seed the mapping with it, so
    # a Dandiset's last known count is retained if it later becomes embargoed, is deleted, or is
    # otherwise unreadable, rather than being dropped from the map.
    dandiset_id_to_number_of_assets = _load_previous_cache(output_file_path)

    # Only the Dandisets whose draft manifest was rewritten since the previous run are fetched;
    # the rest keep the entry they already have. A full pass over the archive reads roughly a
    # gigabyte of manifests, of which the vast majority is unchanged from one day to the next.
    # A Dandiset whose manifest has never been readable has no recorded modification time and so
    # is retried on every run, which is what picks an embargoed Dandiset up once it is released;
    # the retry costs only an immediately denied request. Testing runs always fetch, so that a
    # smoke test exercises the download and counting path even when its slice is unchanged.
    to_fetch: list[tuple[str, str]] = []
    for dandiset_id, (key, last_modified) in draft_manifests.items():
        previous_entry = dandiset_id_to_number_of_assets.get(dandiset_id, {})
        if not testing and previous_entry.get(_LAST_MODIFIED_FIELD) == last_modified:
            continue
        to_fetch.append((dandiset_id, key))
    print(
        f"{len(draft_manifests)} draft manifests listed; {len(draft_manifests) - len(to_fetch)} unchanged since the "
        f"previous run; fetching {len(to_fetch)}.",
        flush=True,
    )

    count_assets = functools.partial(_count_assets, s3_client)
    if testing:
        # Testing run: fetch the manifests one at a time, so the smoke test stays as simple as
        # the slice it covers.
        number_of_updates = _record_counts(
            dandiset_id_to_number_of_assets, map(count_assets, to_fetch), draft_manifests
        )
    else:
        # Full run: fetch the changed manifests concurrently.
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            number_of_updates = _record_counts(
                dandiset_id_to_number_of_assets, executor.map(count_assets, to_fetch), draft_manifests
            )
    print(f"Recorded asset counts for {number_of_updates} Dandisets.", flush=True)

    if len(dandiset_id_to_number_of_assets) == 0:
        message = (
            f"\nNo asset counts could be read under `s3://{_BUCKET}/{_DANDISETS_PREFIX}`.\n"
            "Every listed draft manifest was inaccessible.\n"
        )
        raise RuntimeError(message)

    # One JSON value per line:
    # `{"<dandiset_id>": {"number_of_assets": <count>, "manifest_last_modified": "<timestamp>"}}`.
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
