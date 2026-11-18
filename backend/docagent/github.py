"""Read-only GitHub API client. Credentials never enter URLs or git subprocesses."""

import io
import re
import stat
import time
import zipfile
from pathlib import Path, PurePosixPath
from urllib.parse import quote, urlparse

import httpx

from docagent.config import settings


class GitHubError(Exception):
    def __init__(self, message: str, status: int = 502):
        self.status = status
        super().__init__(message)


class GitHub:
    def __init__(self, token: str = "", transport=None):
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "repo-documentation-agent",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self.client = httpx.Client(
            base_url="https://api.github.com",
            headers=headers,
            timeout=40,
            follow_redirects=False,
            transport=transport,
        )

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.client.close()

    def request(self, path, params=None):
        for attempt in range(3):
            try:
                response = self.client.get(path, params=params)
            except httpx.HTTPError:
                if attempt < 2:
                    time.sleep(0.5 * 2**attempt)
                    continue
                raise GitHubError("GitHub could not be reached. Please retry.") from None
            if response.status_code in {429, 500, 502, 503, 504} and attempt < 2:
                delay = response.headers.get("retry-after", "1")
                time.sleep(min(float(delay) if delay.isdigit() else 1, 5))
                continue
            if response.status_code in {403, 429}:
                raise GitHubError(
                    "GitHub denied access or its rate limit was reached. Check permissions and retry later.",
                    429 if response.headers.get("x-ratelimit-remaining") == "0" else 403,
                )
            if response.status_code == 401:
                raise GitHubError("GitHub credentials are invalid or expired.", 401)
            if response.status_code == 404:
                raise GitHubError("Repository or reference was not found, or access is not granted.", 404)
            if response.status_code >= 400:
                raise GitHubError("GitHub request failed.")
            return response
        raise GitHubError("GitHub unavailable")

    def user(self):
        return self.request("/user").json()

    def repositories(self, page=1):
        response = self.request(
            "/user/repos",
            {
                "per_page": 100,
                "page": page,
                "sort": "updated",
                "affiliation": "owner,collaborator,organization_member",
            },
        )
        return {
            "items": [self.metadata(r) for r in response.json()],
            "has_next": 'rel="next"' in response.headers.get("link", ""),
        }

    @staticmethod
    def metadata(repo):
        return {
            "name": repo["name"],
            "owner": repo["owner"]["login"],
            "full_name": repo["full_name"],
            "private": repo["private"],
            "description": repo.get("description") or "",
            "default_branch": repo["default_branch"],
            "language": repo.get("language"),
            "updated_at": repo["updated_at"],
            "url": repo["html_url"],
        }

    def repository(self, full_name):
        return self.metadata(self.request(f"/repos/{full_name}").json())

    def refs(self, full_name, kind="branches", page=1):
        response = self.request(f"/repos/{full_name}/{kind}", {"per_page": 100, "page": page})
        return {
            "items": [{"name": r["name"], "sha": r["commit"]["sha"]} for r in response.json()],
            "has_next": 'rel="next"' in response.headers.get("link", ""),
        }

    def resolve(self, full_name, ref):
        value = self.request(f"/repos/{full_name}/commits/{quote(ref, safe='')}").json()["sha"]
        if not re.fullmatch(r"[a-f0-9]{40}", value):
            raise GitHubError("GitHub returned an invalid commit identifier")
        return value

    def download(self, full_name, commit, destination):
        response = self.request(f"/repos/{full_name}/zipball/{commit}")
        if response.status_code not in {301, 302, 307}:
            raise GitHubError("GitHub did not return an archive redirect")
        location = response.headers.get("location", "")
        parsed = urlparse(location)
        if (
            parsed.scheme != "https"
            or parsed.hostname != "codeload.github.com"
            or parsed.username
            or parsed.port not in {None, 443}
        ):
            raise GitHubError("Unexpected archive host")
        # New client: NEVER forward the Authorization header to a redirect host.
        cfg = settings()
        archive = io.BytesIO()
        try:
            with httpx.stream("GET", location, timeout=90, follow_redirects=False) as stream:
                if stream.status_code != 200:
                    raise GitHubError("Repository archive could not be downloaded")
                for chunk in stream.iter_bytes():
                    if archive.tell() + len(chunk) > cfg.max_archive_bytes:
                        raise GitHubError("Repository archive exceeds the configured size limit", 413)
                    archive.write(chunk)
        except httpx.HTTPError:
            raise GitHubError("Repository download interrupted") from None
        archive.seek(0)
        safe_extract(archive, destination, cfg.max_expanded_bytes, cfg.max_archive_files)


def safe_extract(archive, destination: Path, max_bytes: int, max_files: int):
    """Reject archive traversal, symlinks, Windows device/ADS paths, duplicates and zip bombs."""
    destination.mkdir(parents=True, exist_ok=True)
    root = destination.resolve()
    total = 0
    seen = set()
    with zipfile.ZipFile(archive) as z:
        members = z.infolist()
        if len(members) > max_files:
            raise ValueError("Archive has too many entries")
        prefixes = {PurePosixPath(m.filename).parts[0] for m in members if PurePosixPath(m.filename).parts}
        if len(prefixes) != 1:
            raise ValueError("Expected a single repository archive root")
        for entry in members:
            parts = PurePosixPath(entry.filename).parts
            # ZipInfo normalizes separators on Windows; orig_filename preserves the archive input.
            if (
                not parts
                or entry.orig_filename.startswith(("/", "\\"))
                or "\\" in entry.orig_filename
                or any(
                    p in {"..", "."}
                    or ":" in p
                    or p.endswith((".", " "))
                    or any(ord(c) < 32 for c in p)
                    or re.fullmatch(r"(?i)(con|prn|aux|nul|com[0-9]|lpt[0-9])(?:\..*)?", p)
                    for p in parts
                )
            ):
                raise ValueError("Unsafe archive path")
            if stat.S_ISLNK(entry.external_attr >> 16):
                raise ValueError("Archive symlinks are not allowed")
            total += entry.file_size
            if total > max_bytes or (
                entry.file_size > 1_000_000 and entry.file_size > max(entry.compress_size, 1) * 500
            ):
                raise ValueError("Archive expansion exceeds the configured limit")
            if len(parts) == 1 or entry.is_dir():
                continue
            relative = PurePosixPath(*parts[1:]).as_posix()
            if relative.casefold() in seen:
                raise ValueError("Duplicate archive path")
            seen.add(relative.casefold())
            target = root.joinpath(*parts[1:])
            if not target.resolve().is_relative_to(root):
                raise ValueError("Archive path escaped workspace")
            target.parent.mkdir(parents=True, exist_ok=True)
            # ZipFile.read verifies CRC; declared uncompressed size has already been bounded.
            target.write_bytes(z.read(entry))
