import hashlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ddtool.updates import Release, asset_names, download_release, parse_release


class UpdateTests(unittest.TestCase):
    def test_release_selection_prefers_installer_and_compares_numeric_versions(self):
        setup, portable = asset_names("win32", "AMD64", installed=True)
        data = {"tag_name": "v1.10.0", "assets": [{"name": portable, "size": 12}, {"name": setup, "size": 18}]}
        self.assertEqual(parse_release(data, "1.9.0", (setup, portable)).name, setup)
        self.assertEqual(parse_release(data, "1.9.0", (portable,)).name, portable)
        self.assertIsNone(parse_release(data, "1.10.0", (setup,)))
        self.assertIsNone(parse_release({**data, "prerelease": True}, "1.9.0", (setup,)))
        with self.assertRaises(ValueError):
            parse_release(data, "1.9.0", asset_names("darwin", "arm64"))

    def test_download_checks_digest_and_publishes_only_complete_files(self):
        content = b"sample ddtool package"
        name = asset_names("win32", "AMD64", installed=True)[0]
        release = Release("v1.10.0", name, len(content), hashlib.sha256(content).hexdigest())
        with tempfile.TemporaryDirectory() as directory, patch("ddtool.updates._open") as open_url:
            open_url.return_value = io.BytesIO(content[::-1])
            with self.assertRaises(ValueError):
                download_release(release, Path(directory))
            self.assertEqual(list((Path(directory) / release.tag).iterdir()), [])
            open_url.return_value = io.BytesIO(content)
            self.assertEqual(download_release(release, Path(directory)).read_bytes(), content)
