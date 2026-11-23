from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import sys
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from ddtool.resources import app_base_dir


REPO = "AddBean/DDTool"
RELEASE_API = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASE_PAGE = f"https://github.com/{REPO}/releases/latest"
VERSION = re.compile(r"(?:v)?(\d{1,6})\.(\d{1,6})\.(\d{1,6})\Z")
DOWNLOAD_LIMIT = 512 * 1024 * 1024


@dataclass(frozen=True)
class Release:
    tag: str
    name: str
    size: int | None
    digest: str

    @property
    def url(self) -> str:
        return f"https://github.com/{REPO}/releases/download/{self.tag}/{self.name}"


def current_version() -> str:
    try:
        return (app_base_dir() / "ddtool-version.txt").read_text(encoding="utf-8").strip()
    except OSError:
        return "0.0.0"


def version_tuple(value: str) -> tuple[int, ...]:
    match = VERSION.fullmatch(value)
    if not match:
        raise ValueError("无法识别发行版版本号。")
    return tuple(map(int, match.groups()))


def asset_names(system: str, machine: str, installed: bool = False) -> tuple[str, ...]:
    if system == "win32" and machine.lower() in {"amd64", "x86_64"}:
        portable = "DDTool-Windows-x64.zip"
        return ("DDTool-Windows-x64-Setup.exe", portable) if installed else (portable,)
    if system == "darwin" and machine.lower() in {"arm64", "aarch64"}:
        return ("DDTool-macOS-arm64.pkg", "DDTool-macOS-arm64.dmg") if installed else ("DDTool-macOS-arm64.dmg",)
    return ()


def _open(url: str, *hosts: str):
    response = urlopen(Request(url, headers={"User-Agent": "DDTool-Updater"}), timeout=8)
    target = urlsplit(response.geturl())
    if target.scheme != "https" or target.hostname not in hosts:
        response.close()
        raise ValueError("下载地址不属于 GitHub 发布服务。")
    return response


def _metadata(url: str, limit: int, *hosts: str) -> bytes:
    with _open(url, *hosts) as response:
        data = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError("发行版元数据超出大小限制。")
    return data


def parse_release(data: dict, current: str, names: tuple[str, ...]) -> Release | None:
    if data.get("draft") or data.get("prerelease"):
        return None
    tag = data.get("tag_name", "")
    if not isinstance(tag, str) or not tag.startswith("v"):
        raise ValueError("发行版标签不受支持。")
    if version_tuple(tag) <= version_tuple(current):
        return None
    for name in names:
        for asset in data.get("assets", []):
            if asset.get("name") != name:
                continue
            size = asset.get("size")
            if type(size) is not int or not 0 < size <= DOWNLOAD_LIMIT:
                raise ValueError("发行包大小无效。")
            digest = asset.get("digest") or ""
            valid = re.fullmatch(r"sha256:([0-9a-fA-F]{64})", digest)
            return Release(tag, name, size, valid[1].lower() if valid else "")
    raise ValueError("正式版不包含适用于当前平台的安装包。")


def check_release() -> Release | None:
    executable = Path(sys.executable)
    installed = (executable.parent / "unins000.exe").is_file() if sys.platform == "win32" else str(executable).startswith("/Applications/")
    names = asset_names(sys.platform, platform.machine(), installed)
    if not names:
        raise ValueError("当前系统或架构没有可用的更新包。")
    return find_release(current_version(), names)


def find_release(current: str, names: tuple[str, ...]) -> Release | None:
    try:
        data = json.loads(_metadata(RELEASE_API, 512 * 1024, "api.github.com"))
    except HTTPError as error:
        if error.code not in {403, 429}:
            raise
        error.close()
        try:
            return _find_public_release(current, names)
        except (OSError, ValueError) as fallback_error:
            raise ValueError("GitHub API 限流或拒绝访问，备用检查也未成功；请打开发布页手动下载。") from fallback_error
    return parse_release(data, current, names)


def _find_public_release(current: str, names: tuple[str, ...]) -> Release | None:
    with _open(RELEASE_PAGE, "github.com") as response:
        path = urlsplit(response.geturl()).path
    match = re.fullmatch(rf"/{re.escape(REPO)}/releases/tag/(v[0-9]+\.[0-9]+\.[0-9]+)/?", path, re.IGNORECASE)
    if not match:
        raise ValueError("公开发布页没有返回可识别的正式版标签。")
    tag = match[1].lower()
    if version_tuple(tag) <= version_tuple(current):
        return None
    checksums = _manifest_digests(tag)
    for name in names:
        if name in checksums:
            return Release(tag, name, None, checksums[name])
    raise ValueError("未找到适用于当前平台且有校验值的安装包。")


def _manifest_digests(tag: str) -> dict[str, str]:
    url = f"https://github.com/{REPO}/releases/download/{tag}/SHA256SUMS.txt"
    data = _metadata(url, 64 * 1024, "github.com", "release-assets.githubusercontent.com").decode("utf-8")
    found = {}
    for line in data.splitlines():
        match = re.fullmatch(r"([a-fA-F0-9]{64}) [ *](?:release-assets/)?(.+)", line)
        if match:
            if match[2] in found:
                raise ValueError("发行包校验清单中包含重复的文件名。")
            found[match[2]] = match[1].lower()
    return found


def _checksum_manifest(release: Release) -> str:
    digest = _manifest_digests(release.tag).get(release.name)
    if not digest:
        raise ValueError("未找到唯一的发行包 SHA-256 校验值。")
    return digest


def download_release(release: Release, directory: Path, cancelled: Callable[[], bool] | None = None) -> Path:
    if not VERSION.fullmatch(release.tag) or release.name not in {
        *asset_names("win32", "amd64", True), *asset_names("darwin", "arm64", True),
    } or (release.size is not None and not 0 < release.size <= DOWNLOAD_LIMIT):
        raise ValueError("发行包参数无效。")
    expected = release.digest or _checksum_manifest(release)
    directory = directory / release.tag
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / release.name
    temporary = None
    try:
        with _open(release.url, "github.com", "release-assets.githubusercontent.com") as response, \
                tempfile.NamedTemporaryFile(dir=directory, suffix=".part", delete=False) as stream:
            temporary = Path(stream.name)
            digest = hashlib.sha256()
            count = 0
            deadline = time.monotonic() + 600
            while chunk := response.read(256 * 1024):
                if cancelled is not None and cancelled():
                    raise ValueError("下载已取消。")
                count += len(chunk)
                if count > (release.size or DOWNLOAD_LIMIT) or time.monotonic() > deadline:
                    raise ValueError("下载超出声明的大小或时间上限。")
                digest.update(chunk)
                stream.write(chunk)
        if (release.size is not None and count != release.size) or digest.hexdigest() != expected:
            raise ValueError("下载包完整性校验失败，文件未保留。")
        os.replace(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return destination
