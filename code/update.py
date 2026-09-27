"""Count the assets in every Dandiset's draft version.

Each Dandiset's `assets.jsonld` is a JSON array with one entry per asset, so its length is the
count. The manifests are read straight from the public archive bucket: no DANDI API, no download.

The cache is accumulative rather than a rebuild, which is the detail that matters here. A
Dandiset's count is refreshed whenever its draft manifest is readable, and its last known count is
kept when the Dandiset later becomes embargoed or is otherwise unreadable. Seeding the published
records from what is already there is what preserves that; returning only the fresh counts would
silently drop every Dandiset the archive has stopped exposing.

The work a run does is one manifest read per Dandiset, and `limit` is how many of those it does.
It does not bind at the archive's present size -- a run reads every Dandiset -- and exists so that
an archive several times larger is spread across crons rather than outgrowing one. What decides
the order is `<stem>_checked_at`, a side output recording when each Dandiset was last attempted:
never-attempted first, then oldest-attempt first, so a bounded run still cycles through all of
them. Whatever a run reads, it publishes the complete cache.

Everything shared -- the argument parsing, the logging, the output paths, testing mode, the JSON
Lines writing, the unsigned S3 client, the listing and the manifest reader -- comes from
`dandi_cache_utils`, which the runtime image carries.
"""

import datetime

import dandi_cache_utils as dandi_cache

#: The side output: when each Dandiset was last *attempted*, read or not, which is what
#: orders the batch once there are more Dandisets than one run reads. Stamping the
#: unreadable ones too is what stops an embargoed Dandiset occupying the batch every run.
CHECKED_AT = "dandiset_id_to_number_of_assets_checked_at.jsonl"

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

    records = dataset.read_output_lookup()
    checked_at = dataset.read_output_lookup(CHECKED_AT)

    def build() -> list[dict]:
        dandiset_ids = list(dandi_cache.s3.dandiset_ids(client))

        # The limit bounds the reads, not the results. A Dandiset never attempted comes first, so
        # a new one is picked up promptly; the rest follow oldest-attempt first, so a run that
        # cannot reach all of them still cycles through every one over successive runs.
        limit = dataset.limit(arguments.limit)
        batch = dandi_cache.select_new(dandiset_ids, checked_at, limit=limit)
        if limit is None or len(batch) < limit:
            batch += dandi_cache.select_stale(
                [dandiset_id for dandiset_id in dandiset_ids if dandiset_id in checked_at],
                checked_at,
                limit=None if limit is None else limit - len(batch),
            )
        dandi_cache.logger.info("Reading %d of %d Dandisets this run.", len(batch), len(dandiset_ids))

        results = dandi_cache.s3.concurrent_map(count_assets, batch, max_workers=WORKERS)
        counts = dict(result for result in results if result)
        if not counts:
            message = (
                f"No draft asset manifests could be read under `s3://{dandi_cache.s3.BUCKET}/"
                f"{dandi_cache.s3.DANDISETS_PREFIX}`. The archive bucket may be unreachable or its "
                "layout may have changed."
            )
            raise RuntimeError(message)

        # Everything already published, updated with what this run read, so a Dandiset that has
        # become unreadable -- or that this run simply did not reach -- keeps its last known
        # count rather than disappearing from the cache.
        today = datetime.datetime.now(tz=datetime.UTC).date().isoformat()
        records.update(counts)
        # Every Dandiset this run attempted, not only the ones that answered: an unreadable one is
        # still done for now, and stamping it is what lets the batch move past it next run.
        checked_at.update(dict.fromkeys(batch, today))
        return [{dandiset_id: records[dandiset_id]} for dandiset_id in sorted(records)]

    dandi_cache.run_full_rebuild(dataset, build=build)
    dataset.write_output_lookup(checked_at, CHECKED_AT)


if __name__ == "__main__":
    main()
