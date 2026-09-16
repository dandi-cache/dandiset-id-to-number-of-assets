"""Count the assets in every Dandiset's draft version.

Each Dandiset's `assets.jsonld` is a JSON array with one entry per asset, so its length is the
count. The manifests are read straight from the public archive bucket: no DANDI API, no download.

The cache is accumulative rather than a rebuild, which is the detail that matters here. A
Dandiset's count is refreshed whenever its draft manifest is readable, and its last known count is
kept when the Dandiset later becomes embargoed or is otherwise unreadable. Seeding `build` from
what is already published is what preserves that; returning only the fresh counts would silently
drop every Dandiset the archive has stopped exposing.

Everything shared -- the argument parsing, the logging, the output paths, testing mode, the JSON
Lines writing, the unsigned S3 client, the listing and the manifest reader -- comes from
`dandi_cache_utils`, which the runtime image carries.
"""

import dandi_cache_utils as dandi_cache

#: One connection per worker. A smaller pool makes the surplus workers redo the TLS handshake on
#: every request, which is the single most common reason one of these caches is slow.
WORKERS = 16


def main() -> None:
    dataset, arguments = dandi_cache.open_dataset()
    client = dandi_cache.s3.anonymous_client(max_pool_connections=WORKERS)

    def count_assets(dandiset_id: str, /) -> tuple[str, int] | None:
        """The Dandiset's asset count, or `None` when its draft manifest cannot be read."""
        assets = dandi_cache.s3.dandiset_assets(client, dandiset_id)
        return None if assets is None else (dandiset_id, len(assets))

    def build() -> list[dict]:
        dandiset_ids = list(dandi_cache.s3.dandiset_ids(client))
        if dataset.testing:
            dandiset_ids = dandiset_ids[: dandi_cache.TESTING_LIMIT]

        results = dandi_cache.s3.concurrent_map(count_assets, dandiset_ids, max_workers=WORKERS)
        counts = dict(result for result in results if result)
        if not counts:
            message = (
                f"No draft asset manifests could be read under `s3://{dandi_cache.s3.BUCKET}/"
                f"{dandi_cache.s3.DANDISETS_PREFIX}`. The archive bucket may be unreachable or its "
                "layout may have changed."
            )
            raise RuntimeError(message)

        # Seeded with what is already published, so a Dandiset that has since become unreadable
        # keeps its last known count rather than disappearing from the cache.
        records = dataset.read_output_lookup()
        records.update(counts)
        return [{dandiset_id: records[dandiset_id]} for dandiset_id in sorted(records)]

    dandi_cache.run_full_rebuild(dataset, build=build, limit=arguments.limit)


if __name__ == "__main__":
    main()
