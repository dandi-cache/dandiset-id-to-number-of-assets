---
name: setup-cache
description: First-time setup of a new DANDI cache repository generated from dandi-cache/cache-template. Use when asked to set up, initialize, or specialize this cache from the template — replacing placeholders, choosing an input mode, implementing update.py, and removing the template scaffolding.
---

# Setting up a new DANDI cache from the template

Work through all of these steps in a single setup PR. `<cache-name>` is the hyphenated
repository name (e.g., `my-cache`); `<cache_name>` is the underscored form used for file
and variable names (e.g., `my_cache`).

Before starting, read the README's **How it works** section — it explains the
`main` / `derivatives` / `dist` branch layout and the container-based provenance that
the pipeline relies on. (It is part of the scaffolding removed in step 4, so it only
exists before setup.)

`code/update_pipeline.sh` retries both publish pushes (`derivatives` and `dist`) on
transient GitHub push errors (e.g. `fatal error in commit_refs`), and the runtime image
`docker pull` on a transient ghcr.io `denied: denied` right after a successful login, via
a shared `retry_with_backoff` helper (`push_with_retry` wraps it for git). That's pipeline
infrastructure, not per-cache configuration — leave it as-is unless you're deliberately
changing the pipeline's retry behavior.

## 1. Replace placeholders and resolve TODO markers

- Replace every `<cache-name>` / `<cache_name>` occurrence across the repository
  (README, `code/`, `containers/`, `.github/workflows/`).
- Resolve every `TODO` marker: the update schedule (cron in
  `.github/workflows/update.yml`), the input dataset, and the notification recipients.
- Fill in the placeholder fields in `dataset_description.json` (`Name`, `Authors`;
  `License` defaults to `CC-BY-4.0` — change it if this cache uses a different license).
- Write a short description of what the cache contains and how it is derived at the top
  of the README.

## 2. Choose the input mode

Select one of the three input modes; the `INPUT_SUBDATASET_URL` / `INPUT_SUBDATASET_PATH`
/ `INPUT_SUBDATASET_BRANCH` variables in `code/update_pipeline.sh` (the input-mode TODO)
drive the choice, and `code/update.py` reads accordingly:

1. **Upstream DataLad dataset.** Set `INPUT_SUBDATASET_URL` to register an upstream
   dataset as an input subdataset. It is cloned into the `derivatives` dataset and
   pinned via `--input` in the provenance of every run, so each result records the
   exact input commit it was computed from. `INPUT_SUBDATASET_BRANCH` selects which
   branch of the input dataset to track: dandi-cache datasets publish their data on a
   dedicated branch (their default branch holds only code), so it defaults to
   `derivatives` — set it to whatever branch the upstream cache publishes to (e.g.
   `min`). It is recorded in `.gitmodules` so `submodule update --remote` follows that
   branch on every run.
2. **Local `sourcedata` directory.** Inputs live under the dataset's own `sourcedata/`
   (e.g. committed fixtures). Leave `INPUT_SUBDATASET_URL` empty; optionally declare the
   relevant paths as `--input` in the `containers-run` call to pin them in provenance.
3. **First-in-chain / no input dataset.** The cache fetches its own inputs over the
   network at run time (e.g. it queries a remote API or archive). Leave
   `INPUT_SUBDATASET_URL` empty: there is no input dataset to pin, so no `--input`
   provenance is declared. Because the inputs are pulled at run time, the processing
   container requires outbound network access — the runtime environment must allow the
   container to reach the upstream source, and the `--call-fmt` in `update_pipeline.sh`
   must not isolate the container's network. If the inputs come from the public DANDI
   S3 bucket, read the `dandi-s3-network-inputs` skill before writing that code.

## 3. Implement the cache logic

- Implement `_run` in `code/update.py`: read the inputs, compute the cache, and write the
  result into `derivatives/<cache_name>.jsonl` as JSON Lines.
- Give `_run` a `--testing` flag: when set, process only a handful of items
  (`_TESTING_LIMIT`, e.g. 10) and write to `derivatives/testing.jsonl` instead of
  `derivatives/<cache_name>.jsonl`, so a manual dispatch can exercise the real processing
  logic end to end — including the container build, `datalad containers-run` provenance,
  and the S3/API calls if this cache fetches network inputs — without ever overwriting the
  real cache. Thread it through `update_pipeline.sh` (a `TESTING` env var, `"true"` →
  `--testing`) and `update.yml` (a `workflow_dispatch.inputs.testing` checkbox). Slice
  however fits how this cache's items are structured (e.g. slice each category separately
  if entries fall into distinct cases, as in
  [content-id-to-usage-dandiset-path](https://github.com/dandi-cache/content-id-to-usage-dandiset-path/blob/main/code/update.py)).
- Decide whether to also add a `--limit` flag, separate from `--testing`: a batch size that
  caps a real (non-testing) run to processing at most N new items, skipping those already
  recorded in the derivatives. This is only needed when the update is so heavy per item that
  a single invocation cannot complete the full backlog in one run — e.g.
  [qualifying-aind-content-ids](https://github.com/dandi-cache/qualifying-aind-content-ids),
  where each run intentionally advances only a small number of items. Most caches don't need
  it: design `_run` to be idempotent and incremental on its own — skip items already
  recorded in the derivatives and compute only what's new or changed since the last run —
  rather than reprocessing the full backlog from scratch every time.
- Add the processing dependencies to `envs/pyproject.toml`.
- The container image is the authoritative runtime, but recreate the environment
  locally with [uv](https://docs.astral.sh/uv/) to debug and verify:
  `uv run --project envs python code/update.py --testing`. Run with `--testing` first — it
  is fast and never touches the real cache — before a full local run without the flag.
- Before merging, do a smoke run through the real pipeline: manually dispatch the `Update`
  workflow with `testing: true` (or run `code/update_pipeline.sh` locally with
  `TESTING=true`) and confirm it completes, writes `derivatives/testing.jsonl`, and leaves
  `derivatives/<cache_name>.jsonl` untouched.

## 4. Remove the template scaffolding

These pieces document the template itself, not the generated cache — delete them in this
same setup PR:

- The README **How it works** section — the generated cache's README should describe
  only the cache itself and how to consume it.
- The README **Repository setup** section (including its **With Claude Code**
  subsection).
- `.claude/skills/setup-cache/` — this skill has no purpose once setup is done.
- `.claude/skills/dandi-s3-network-inputs/` — only if this cache does **not** fetch
  inputs from the DANDI S3 bucket; keep it when input mode 3 uses that bucket. If
  nothing remains under `.claude/`, remove the directory entirely.
