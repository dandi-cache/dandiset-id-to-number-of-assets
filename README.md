# DANDI Cache: `dandiset-id-to-number-of-assets`

Maps each Dandiset ID to the number of assets in its `draft` version.

For every Dandiset, this cache counts the entries of the `draft` version's `assets.jsonld` manifest, read directly from the public DANDI archive S3 bucket -- the `draft` version always reflects a Dandiset's current contents, since changes to it apply immediately, while published versions are frozen snapshots taken at publish time.

The count comes from the asset manifest itself rather than from the `assetsSummary.numberOfFiles` field of the much smaller `dandiset.jsonld` metadata, because for `draft` versions that summary field is frequently stale or absent.

The cache is accumulative: a Dandiset's count is refreshed whenever its draft manifest is readable, and its last known count is retained if the Dandiset later becomes embargoed or otherwise unreadable, rather than being dropped from the map.

Updated every six hours, since the draft version of a Dandiset can gain or lose assets at any time.

Primarily for use by developers.

A second output, `derivatives/dandiset_id_to_number_of_assets_checked_at.zarr`, records the UTC date each Dandiset's manifest was last read, whether or not the read succeeded.
It is bookkeeping rather than data: it is what lets a run that cannot reach every Dandiset read the ones it has gone longest without, instead of the same prefix of the listing each time.
Every Dandiset is read on every run at the archive's present size, so in practice the dates move together.



## One-time use

`dist` publishes each output as a [Zarr](https://zarr.dev/) store: the cache itself is `derivatives/dandiset_id_to_number_of_assets.zarr/`, with the cache's other outputs beside it as stores of the same kind (`derivatives/dandiset_id_to_number_of_assets_checked_at.zarr/`).
A store is one array of [JSON Lines](https://jsonlines.org/) text cut into chunk files, each holding whole lines and gzip-compressed.
Where a key appears more than once, the last line is its current entry, and the published copy has no repeats.
It can be read with the standard library alone, or opened remotely with any Zarr library.

### Python API (recommended)

Fetch `stream/zarr.json` for the array's length and chunk size, then each chunk in order:

```python
import gzip
import json
import math
import urllib.request

store = "https://raw.githubusercontent.com/dandi-cache/dandiset-id-to-number-of-assets/refs/heads/dist/derivatives/dandiset_id_to_number_of_assets.zarr"


def fetch(path):
    with urllib.request.urlopen(f"{store}/{path}") as response:
        return response.read()


array = json.loads(fetch("stream/zarr.json"))
length = array["shape"][0]
chunk_bytes = array["chunk_grid"]["configuration"]["chunk_shape"][0]

dandiset_id_to_number_of_assets = {}
for index in range(math.ceil(length / chunk_bytes)):
    for line in gzip.decompress(fetch(f"stream/c/{index}")).decode("utf-8").splitlines():
        if line.strip():
            dandiset_id_to_number_of_assets.update(json.loads(line))
```

Each line is one JSON record mapping a Dandiset ID to its number of assets:

```json
{"<dandiset id>": <number of assets>}
```

An entry is not filed under its key: the chunks hold the entries in the order they were recorded, so looking up one means reading through them.
To look up many, read it once as above, or clone the `derivatives` branch.

### Remote Zarr store

Anything that opens Zarr can open the store over HTTP, reading only the chunks it needs.
The group's `zarr.json` carries the array's metadata, so opening it takes one request:

```bash
pip install "zarr>=3" fsspec aiohttp
```

```python
import json

import zarr

url = "https://raw.githubusercontent.com/dandi-cache/dandiset-id-to-number-of-assets/refs/heads/dist/derivatives/dandiset_id_to_number_of_assets.zarr"
stream = zarr.open_group(url, mode="r")["stream"]
print(stream.shape, stream.chunks)  # Bytes in all, and bytes per chunk.

# The first chunk, fetched and decompressed on its own: whole lines, each `{"<key>": <value>}`.
first_chunk = stream[: stream.chunks[0]].tobytes().decode("utf-8")
for line in first_chunk.splitlines():
    if line.strip():
        print(json.loads(line))
        break
```

Reading `stream[:]` returns the whole text; to read it in pieces, step through it by `stream.chunks[0]`, as each chunk is fetched whole.

### Save to file

A raw URL cannot be listed, so to fetch every chunk at once clone the `dist` branch, which holds nothing else:

```bash
git clone --branch dist --depth 1 https://github.com/dandi-cache/dandiset-id-to-number-of-assets.git
```



## Repeated use

If you plan on using this cache regularly, clone the `derivatives` branch of this repository:

```bash
git clone --branch derivatives https://github.com/dandi-cache/dandiset-id-to-number-of-assets.git
```

Or, if you prefer [DataLad](https://www.datalad.org/):

```bash
datalad clone https://github.com/dandi-cache/dandiset-id-to-number-of-assets.git --branch derivatives
```

Then set up a CRON on your system to pull the latest version of the cache at your desired frequency.

For example, through `crontab -e`, add:

```bash
0 0 * * * git -C /path/to/dandiset-id-to-number-of-assets pull
```

This will minimize data overhead by only loading the most recent changes.

Each output is a store on the `derivatives` branch, where it is the whole log, uncompacted, and plain text:

```python
import json
import pathlib

chunks = pathlib.Path("dandiset-id-to-number-of-assets/derivatives/dandiset_id_to_number_of_assets.zarr/stream/c")
dandiset_id_to_number_of_assets = {}
for chunk in sorted(chunks.iterdir(), key=lambda path: int(path.name)):
    for line in chunk.read_text().splitlines():
        if line.strip():
            dandiset_id_to_number_of_assets.update(json.loads(line))  # A later line for a key replaces an earlier one.
```
