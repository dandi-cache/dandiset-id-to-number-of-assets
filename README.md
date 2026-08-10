# DANDI Cache: `dandiset-id-to-number-of-assets`

Maps each Dandiset ID to the number of assets in its `draft` version.

For every Dandiset, this cache counts the entries of the `draft` version's `assets.jsonld` manifest, read directly from the public DANDI archive S3 bucket -- the `draft` version always reflects a Dandiset's current contents, since changes to it apply immediately, while published versions are frozen snapshots taken at publish time.

The count comes from the asset manifest itself rather than from the `assetsSummary.numberOfFiles` field of the much smaller `dandiset.jsonld` metadata, because for `draft` versions that summary field is frequently stale or absent.

The manifest's S3 modification time is published alongside each count, so a consumer can tell how current the count is. It is also what makes the update incremental: a run only re-reads the manifests that have been rewritten since the previous run.

The cache is accumulative: a Dandiset's count is refreshed whenever its draft manifest is readable, and its last known count is retained if the Dandiset later becomes embargoed or otherwise unreadable, rather than being dropped from the map.

Updated daily, since the draft version of a Dandiset can gain or lose assets at any time.

Primarily for use by developers.



## One-time use

If you only plan to use this cache infrequently or from disparate locations, you can directly download the latest version of the cache as a compressed [JSON Lines](https://jsonlines.org/) file from the `dist` branch:

### Python API (recommended)

```python
import gzip
import json

import requests

url = "https://raw.githubusercontent.com/dandi-cache/dandiset-id-to-number-of-assets/refs/heads/dist/derivatives/dandiset_id_to_number_of_assets.jsonl.gz"
response = requests.get(url)
lines = gzip.decompress(data=response.content).decode("utf-8").splitlines()
dandiset_id_to_number_of_assets = {
    dandiset_id: entry["number_of_assets"]
    for line in lines
    for dandiset_id, entry in json.loads(line).items()
}
```

Each line is one JSON record mapping a Dandiset ID to its asset count and the S3 modification time of the manifest that count was read from:

```json
{"<dandiset id>": {"number_of_assets": <count>, "manifest_last_modified": "<timestamp>"}}
```

### Save to file

```bash
curl https://raw.githubusercontent.com/dandi-cache/dandiset-id-to-number-of-assets/refs/heads/dist/derivatives/dandiset_id_to_number_of_assets.jsonl.gz -o dandiset_id_to_number_of_assets.jsonl.gz
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
