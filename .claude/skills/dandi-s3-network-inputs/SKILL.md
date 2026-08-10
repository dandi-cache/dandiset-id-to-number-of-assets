---
name: dandi-s3-network-inputs
description: Hard-won lessons for cache update logic that fetches inputs directly from the public DANDI S3 bucket (the first-in-chain / no-input-dataset mode). Use when implementing, debugging, or speeding up code in update.py that lists or downloads objects from the DANDI archive bucket — especially with boto3/botocore, a ThreadPoolExecutor, or manifest parsing.
---

# Fetching inputs from the public DANDI S3 bucket

Lessons earned while debugging and speeding up
[dandi-cache/content-id-to-dandiset-paths](https://github.com/dandi-cache/content-id-to-dandiset-paths)
(its PRs #9 and #10). They apply to any first-in-chain cache whose `update.py` pulls its
own inputs from the public DANDI S3 bucket at run time.

## Listed does not mean readable

Objects that appear in a bucket listing can still deny an anonymous `GetObject`:

- Embargoed Dandisets list their manifests publicly but return `AccessDenied`.
- An object can be deleted between listing and fetching, returning `NoSuchKey`.

Catch `botocore.exceptions.ClientError`, skip those two error codes per object with a log
line, and re-raise anything else. Do not let an expected upstream state fail the whole run.

## Size the connection pool to the worker count

When downloading with a `ThreadPoolExecutor`, botocore's default connection pool of 10
makes surplus workers redo the TCP/TLS handshake on every request. Configure the client
with a pool matched to the executor and standard retries:

```python
botocore.config.Config(
    signature_version=botocore.UNSIGNED,
    max_pool_connections=max_workers,
    retries={"mode": "standard"},
)
```

## Prefer JSON inputs over YAML

Parsing large YAML in pure Python is GIL-bound, orders of magnitude slower than
`json.loads`, and threads do not parallelize it — it can dominate the entire run time.
Wherever the source offers both formats, take the JSON: the DANDI archive publishes
`assets.jsonld` next to every `assets.yaml`.
