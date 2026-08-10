# DANDI Cache: `<cache-name>`

`<A short description of what this cache contains and how it is derived.>`

Updated frequently.

Primarily for use by developers.

> **Note:** Throughout this template, `<cache-name>` refers to the hyphenated repository name (e.g., `my-cache`) and `<cache_name>` refers to the underscored form used for file and variable names (e.g., `my_cache`).



## One-time use

If you only plan to use this cache infrequently or from disparate locations, you can directly download the latest version of the cache as a compressed [JSON Lines](https://jsonlines.org/) file from the `dist` branch:

### Python API (recommended)

```python
import gzip
import json

import requests

url = "https://raw.githubusercontent.com/dandi-cache/<cache-name>/refs/heads/dist/derivatives/<cache_name>.jsonl.gz"
response = requests.get(url)
lines = gzip.decompress(data=response.content).decode("utf-8").splitlines()
<cache_name> = [json.loads(line) for line in lines]
```

### Save to file

```bash
curl https://raw.githubusercontent.com/dandi-cache/<cache-name>/refs/heads/dist/derivatives/<cache_name>.jsonl.gz -o <cache_name>.jsonl.gz
```



## Repeated use

If you plan on using this cache regularly, clone the `derivatives` branch of this repository:

```bash
git clone --branch derivatives https://github.com/dandi-cache/<cache-name>.git
```

Or, if you prefer [DataLad](https://www.datalad.org/):

```bash
datalad clone https://github.com/dandi-cache/<cache-name>.git --branch derivatives
```

Then set up a CRON on your system to pull the latest version of the cache at your desired frequency.

For example, through `crontab -e`, add:

```bash
0 0 * * * git -C /path/to/<cache-name> pull
```

This will minimize data overhead by only loading the most recent changes.



## How it works

This cache template demonstrates how generated results of the code branch and records every update with full provenance.

It uses three branches:

- **`main`** holds only the code of the update logic, the runtime container definition, and the CI workflows (including building and distributing the container images).
- [**`derivatives`**](https://github.com/dandi-cache/cache-template/tree/derivatives) is a persistent [DataLad](https://www.datalad.org/) dataset on its own branch. Each update is recorded there with `datalad containers-run`, so every revision carries full provenance of the exact command, the input subdataset commit, the output diff, and the runtime container image digest.
- **`dist`** is the lightweight publication artifact consumed by downstream users and preferred for one-time downloads.

The processing runs inside a published container image (`ghcr.io/dandi-cache/<cache-name>:latest`) that holds only the pinned runtime environment.

The orchestration lives in [`code/update_pipeline.sh`](code/update_pipeline.sh); the actual cache logic lives in [`code/update.py`](code/update.py).

The repository is described as a [BIDS study dataset](https://bids-specification.readthedocs.io/en/stable/common-principles.html#study-dataset) via [`dataset_description.json`](dataset_description.json) (`DatasetType: "study"`). Future enhancements may improve the provenance tracking through this mechanism in line with BEP028.



## Repository setup

After generating a repository from this template, the full setup checklist lives in [`.claude/skills/setup-cache/SKILL.md`](.claude/skills/setup-cache/SKILL.md): replacing the placeholders, choosing an input mode, implementing the cache logic, and removing the template scaffolding (this section and the **How it works** section above included).

### With Claude Code

Open a [Claude Code](https://claude.com/claude-code) session in the freshly generated repository and start from a prompt like:

> Set up this new DANDI cache using the setup-cache skill. The cache should `<describe what this cache computes, where its inputs come from, and how often it should update>`. Open the result as a single setup PR.
