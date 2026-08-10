import argparse
import itertools
import json
import pathlib

# Testing mode processes only this many items and writes to its own designated file
# (`derivatives/testing.jsonl`), leaving the real cache untouched.
_TESTING_LIMIT = 10
_CACHE_FILE_NAME = "<cache_name>.jsonl"
_TESTING_FILE_NAME = "testing.jsonl"


def _run(base_directory: pathlib.Path, testing: bool) -> None:
    # TODO: implement the update logic for this cache.
    # Read the inputs, compute the cache, and write the result into
    # `base_directory / "derivatives"` as JSON Lines (one JSON value per line).
    #
    # The setup checklist — input modes, whether to keep `--testing`, and lessons for
    # fetching inputs from the public DANDI S3 bucket — lives in the plain-Markdown
    # skills .claude/skills/setup-cache/SKILL.md and
    # .claude/skills/dandi-s3-network-inputs/SKILL.md.

    records: list = []

    if testing:
        # Testing run: keep only the first few items, so the run is fast but still
        # exercises the real processing logic end to end.
        records = list(itertools.islice(records, _TESTING_LIMIT))

    derivatives_directory = base_directory / "derivatives"
    derivatives_directory.mkdir(parents=True, exist_ok=True)

    # Testing runs write to their own designated file, so the real cache is never touched.
    output_file_path = derivatives_directory / (_TESTING_FILE_NAME if testing else _CACHE_FILE_NAME)
    with output_file_path.open(mode="w") as file_stream:
        file_stream.writelines(f"{json.dumps(record)}\n" for record in records)


if __name__ == "__main__":
    default_base_directory = pathlib.Path(__file__).parent.parent

    parser = argparse.ArgumentParser(description="Update the <cache-name> DANDI cache.")
    parser.add_argument(
        "--base-directory",
        type=pathlib.Path,
        default=default_base_directory,
        help=(
            "The directory containing the `sourcedata` and `derivatives` directories. "
            "Set to the mounted dataset path when run inside the pipeline container; "
            "defaults to the repository root."
        ),
    )
    parser.add_argument(
        "--testing",
        action="store_true",
        help=(
            f"Run in testing mode: process only the first {_TESTING_LIMIT} items and write "
            f"`derivatives/{_TESTING_FILE_NAME}` instead of the real cache, leaving it "
            "untouched. Omit for a complete update."
        ),
    )
    args = parser.parse_args()

    _run(base_directory=args.base_directory, testing=args.testing)
