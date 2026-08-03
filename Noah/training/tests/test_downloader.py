import io
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import ClassVar
from unittest.mock import patch

from Noah.training.download_dataset import (
    DownloadLimitError,
    _copy_response,
    _next_page_url,
    _validate_repo_path,
    create_manifest,
    list_dataset_files,
    verify_manifest,
)


class DownloaderTests(unittest.TestCase):
    def test_stream_is_written_atomically(self) -> None:
        with TemporaryDirectory() as directory:
            destination = Path(directory) / "nested" / "data.bin"
            size = _copy_response(
                io.BytesIO(b"cs2"),
                destination,
                max_bytes=10,
                already_downloaded=0,
            )
            self.assertEqual(size, 3)
            self.assertEqual(destination.read_bytes(), b"cs2")
            self.assertFalse(destination.with_name("data.bin.part").exists())

    def test_stream_rejects_budget_and_removes_partial_file(self) -> None:
        with TemporaryDirectory() as directory:
            destination = Path(directory) / "data.bin"
            with self.assertRaises(DownloadLimitError):
                _copy_response(
                    io.BytesIO(b"too-large"),
                    destination,
                    max_bytes=3,
                    already_downloaded=0,
                )
            self.assertFalse(destination.exists())
            self.assertFalse(destination.with_name("data.bin.part").exists())

    def test_repository_paths_cannot_escape_output_directory(self) -> None:
        self.assertEqual(_validate_repo_path("data/file.parquet").parts, ("data", "file.parquet"))
        with self.assertRaises(ValueError):
            _validate_repo_path("../outside.dem")

    def test_next_page_url_is_extracted(self) -> None:
        header = '<https://example.test/page-2>; rel="next", <https://example.test/page-1>; rel="prev"'
        self.assertEqual(_next_page_url(header), "https://example.test/page-2")

    def test_dataset_listing_uses_data_tree_and_follows_pages(self) -> None:
        class Response:
            def __init__(self, payload, link=None):
                self.headers = {"Link": link} if link else {}
                self._payload = payload

            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def read(self, *_):
                return b""

            def json(self):
                return self._payload

        # json.load calls read(), so use a real byte response for the mock.
        import json
        from io import BytesIO

        class JsonResponse(Response):
            def read(self, *_):
                return BytesIO(json.dumps(self._payload).encode()).read()

        first = JsonResponse(
            [{"type": "file", "path": "data/a.parquet"}],
            '<https://example.test/page-2>; rel="next"',
        )
        second = JsonResponse([{"type": "file", "path": "data/b.parquet"}])
        with patch("training.download_dataset.urllib.request.urlopen", side_effect=[first, second]) as open_url:
            self.assertEqual(list_dataset_files("org/dataset"), ["data/a.parquet", "data/b.parquet"])
        first_url = open_url.call_args_list[0].args[0].full_url
        self.assertIn("/tree/main/data?", first_url)

    def test_dataset_listing_can_include_the_repository_root(self) -> None:
        class Response:
            headers: ClassVar[dict[str, str]] = {}

            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def read(self, *_):
                return b'[{"type":"file","path":"demos/a.dem"}]'

        with patch("training.download_dataset.urllib.request.urlopen", return_value=Response()) as open_url:
            self.assertEqual(
                list_dataset_files("org/dataset", path_in_repo=""),
                ["demos/a.dem"],
            )
        self.assertIn("/tree/main?", open_url.call_args.args[0].full_url)

    def test_manifest_records_and_verifies_exact_files(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory) / "sidecars"
            (root / "demos" / "match").mkdir(parents=True)
            (root / "demos" / "match" / "one.analysis.json").write_bytes(b"one")
            manifest_path = Path(directory) / "manifest.json"
            manifest = create_manifest(root, manifest_path, dataset_id="org/dataset")

            self.assertEqual(manifest["total_bytes"], 3)
            self.assertEqual(verify_manifest(root, manifest_path), [])

            (root / "demos" / "match" / "one.analysis.json").write_bytes(b"changed")
            self.assertEqual(
                verify_manifest(root, manifest_path),
                ["size mismatch: demos/match/one.analysis.json (expected 3, got 7)"],
            )

    def test_manifest_verification_rejects_unexpected_files(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory) / "data"
            root.mkdir()
            (root / "a.json").write_bytes(b"a")
            manifest_path = Path(directory) / "manifest.json"
            create_manifest(root, manifest_path)
            (root / "extra.json").write_bytes(b"extra")
            self.assertEqual(verify_manifest(root, manifest_path), ["unexpected: extra.json"])
