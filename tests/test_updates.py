import hashlib
import io
import tempfile
import unittest
from pathlib import Path
from urllib.error import HTTPError
from unittest.mock import patch

from ddtool.updates import RELEASE_API, RELEASE_PAGE, Release, asset_names, download_release, find_release, parse_release


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

    def test_rate_limit_uses_public_release_and_verified_download_without_api_size(self):
        setup, portable = asset_names("win32", "AMD64", installed=True)
        content = b"release contents"
        digest = hashlib.sha256(content).hexdigest()
        page = io.BytesIO()
        page.geturl = lambda: RELEASE_PAGE.replace("latest", "tag/v1.10.0")
        manifest = f"{digest}  release-assets/{portable}\n{digest}  release-assets/{setup}\n".encode()
        with patch("ddtool.updates._metadata", side_effect=[HTTPError(RELEASE_API, 403, "rate limit exceeded", {}, None), manifest]), \
                patch("ddtool.updates._open", return_value=page):
            release = find_release("1.9.0", (setup, portable))
        self.assertEqual(release, Release("v1.10.0", setup, None, digest))
        with tempfile.TemporaryDirectory() as directory, patch("ddtool.updates._open") as open_url:
            open_url.return_value = io.BytesIO(content[:-1])
            with self.assertRaisesRegex(ValueError, "完整性校验失败"):
                download_release(release, Path(directory))
            open_url.return_value = io.BytesIO(content)
            self.assertEqual(download_release(release, Path(directory)).read_bytes(), content)

    def test_rate_limit_rejects_unrelated_redirect(self):
        page = io.BytesIO()
        page.geturl = lambda: "https://github.com/another/repo/releases/tag/v1.10.0"
        with patch("ddtool.updates._metadata", side_effect=HTTPError(RELEASE_API, 429, "rate limit exceeded", {}, None)) as metadata, \
                patch("ddtool.updates._open", return_value=page), self.assertRaisesRegex(ValueError, "手动下载"):
            find_release("1.9.0", asset_names("win32", "AMD64"))
        metadata.assert_called_once()
