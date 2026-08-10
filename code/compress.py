import argparse
import gzip
import pathlib
import shutil


def _compress(file_path: pathlib.Path, /) -> None:
    compressed_file_path = file_path.parent / f"{file_path.name}.gz"
    # `mtime=0` keeps the gzip header timestamp-free, so unchanged input compresses to a
    # byte-identical artifact run after run.
    with (
        file_path.open(mode="rb") as source_stream,
        compressed_file_path.open(mode="wb") as raw_target_stream,
        gzip.GzipFile(fileobj=raw_target_stream, mode="wb", mtime=0) as target_stream,
    ):
        shutil.copyfileobj(fsrc=source_stream, fdst=target_stream)


if __name__ == "__main__":
    default_base_directory = pathlib.Path(__file__).parent.parent

    parser = argparse.ArgumentParser(description="Compress the <cache-name> JSON Lines derivatives for distribution.")
    parser.add_argument(
        "--base-directory",
        type=pathlib.Path,
        default=default_base_directory,
        help=(
            "The directory containing the `derivatives` directory. Set to the dataset "
            "clone when run from the pipeline; defaults to the repository root."
        ),
    )
    args = parser.parse_args()

    derivatives_dir = args.base_directory / "derivatives"
    for jsonl_file_path in derivatives_dir.glob("*.jsonl"):
        _compress(jsonl_file_path)
