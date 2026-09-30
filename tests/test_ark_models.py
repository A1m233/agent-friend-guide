from __future__ import annotations

import hashlib
import http.client
import importlib.util
import io
import json
import os
import ssl
import sys
import tempfile
import unittest
import urllib.error
import urllib.parse
from email.message import Message
from pathlib import Path, PurePosixPath
from types import SimpleNamespace
from unittest.mock import call, patch

SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "skills"
    / "agent-friend-guide"
    / "scripts"
    / "ark-models.py"
)
SPEC = importlib.util.spec_from_file_location("ark_models", SCRIPT)
assert SPEC and SPEC.loader
ark_models = importlib.util.module_from_spec(SPEC)
PREVIOUS_DONT_WRITE_BYTECODE = sys.dont_write_bytecode
sys.dont_write_bytecode = True
try:
    SPEC.loader.exec_module(ark_models)
finally:
    sys.dont_write_bytecode = PREVIOUS_DONT_WRITE_BYTECODE


def binary_string(value: str) -> bytes:
    payload = value.encode("utf-8")
    number = len(payload) + 1
    encoded = bytearray()
    while True:
        byte = number & 0x7F
        number >>= 7
        if number:
            byte |= 0x80
        encoded.append(byte)
        if not number:
            break
    return bytes(encoded) + payload


COMMIT = "3745e5c6e10b5252b2a5e1f1841ebef62b7ef15b"
SLUG = "1038_whitw2_sale#15"
STEM = f"build_char_{SLUG}"


class FakeResponse:
    def __init__(
        self,
        payload: bytes = b"",
        *,
        headers: dict[str, str] | None = None,
        chunks: list[bytes | Exception] | None = None,
    ) -> None:
        self.headers = Message()
        for key, value in (headers or {}).items():
            self.headers[key] = value
        self.stream = io.BytesIO(payload)
        self.chunks = iter(chunks) if chunks is not None else None
        self.closed = False

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *args: object) -> None:
        self.closed = True

    def read(self, size: int = -1) -> bytes:
        if self.chunks is None:
            return self.stream.read(size)
        value = next(self.chunks, b"")
        if isinstance(value, Exception):
            raise value
        return value


def http_error(
    status: int, *, headers: dict[str, str] | None = None, message: str = "failure"
) -> urllib.error.HTTPError:
    response_headers = Message()
    for key, value in (headers or {}).items():
        response_headers[key] = value
    return urllib.error.HTTPError(
        "https://api.github.com/test",
        status,
        "failure",
        response_headers,
        io.BytesIO(json.dumps({"message": message}).encode()),
    )


def raw_response(payload: bytes) -> FakeResponse:
    return FakeResponse(
        payload,
        headers={
            "Content-Type": "application/vnd.github.raw+json",
            "Content-Length": str(len(payload)),
        },
    )


def model_files() -> dict[str, bytes]:
    catalog = {
        "storageDirectory": {"Operator": "models"},
        "data": {
            SLUG: {
                "type": "Operator",
                "name": "荒芜拉普兰德",
                "appellation": "Lappland the Decadenza",
                "skinGroupName": "忒斯特收藏/XVII",
                "style": "BuildingSkin",
                "assetList": {".atlas": f"{STEM}.atlas", ".skel": f"{STEM}.skel"},
            }
        },
    }
    return {
        "models_data.json": json.dumps(catalog, ensure_ascii=False).encode(),
        f"models/{SLUG}/{STEM}.atlas": f"{STEM}.png\nsize: 1,1\n".encode(),
        f"models/{SLUG}/{STEM}.skel": binary_string("hash") + binary_string("3.8.99") + b"skeleton",
        f"models/{SLUG}/{STEM}.png": b"fake texture bytes",
    }


class FileServer:
    """Serve only fixture files at the exact pinned repository and commit."""

    def __init__(self, files: dict[str, bytes], *, fallback: bool = False) -> None:
        self.files = files
        self.fallback = fallback
        self.requests: list[object] = []
        self.fail_path: str | None = None

    def __call__(self, request: object, *, timeout: int) -> FakeResponse:
        self.requests.append(request)
        url = request.full_url
        raw_prefix = f"{ark_models.RAW_ROOT}/{COMMIT}/"
        contents_prefix = f"{ark_models.API_ROOT}/contents/"
        if url.startswith(raw_prefix):
            relative = urllib.parse.unquote(url[len(raw_prefix) :])
            if self.fallback:
                raise TimeoutError("raw fixture transport timed out")
        elif url.startswith(contents_prefix):
            parsed = urllib.parse.urlsplit(url)
            if urllib.parse.parse_qs(parsed.query) != {"ref": [COMMIT]}:
                raise AssertionError(f"request lost pinned commit: {url}")
            relative = urllib.parse.unquote(
                parsed.path.removeprefix("/repos/isHarryh/Ark-Models/contents/")
            )
            if request.get_header("Accept") != "application/vnd.github.raw+json":
                raise AssertionError("Contents API must request raw bytes")
        else:
            raise AssertionError(f"unexpected repository or commit lookup: {url}")
        if "#" in url:
            raise AssertionError("model slug must be URL-encoded")
        if relative == self.fail_path:
            raise http_error(404)
        if relative not in self.files:
            raise AssertionError(f"unexpected asset request: {relative}")
        return raw_response(self.files[relative])


class ArkModelsNetworkTests(unittest.TestCase):
    def test_full_commit_is_normalized_without_network(self) -> None:
        with patch.object(ark_models.urllib.request, "urlopen") as opened:
            for ref in (COMMIT, COMMIT.upper()):
                with self.subTest(ref=ref):
                    self.assertEqual(ark_models.resolve_commit(ref), COMMIT)
            opened.assert_not_called()

    def test_branch_and_short_commit_still_resolve_through_api(self) -> None:
        for ref in ("main", "feature/model#15", COMMIT[:12]):
            with (
                self.subTest(ref=ref),
                patch.object(
                    ark_models.urllib.request,
                    "urlopen",
                    return_value=FakeResponse(json.dumps({"sha": COMMIT}).encode()),
                ) as opened,
            ):
                self.assertEqual(ark_models.resolve_commit(ref), COMMIT)
                self.assertEqual(
                    opened.call_args.args[0].full_url,
                    f"{ark_models.API_ROOT}/commits/{urllib.parse.quote(ref, safe='')}",
                )

    def test_invalid_resolved_commit_is_not_used(self) -> None:
        with (
            patch.object(
                ark_models.urllib.request,
                "urlopen",
                return_value=FakeResponse(b'{"sha": "main"}'),
            ),
            self.assertRaises(ark_models.InstallerError) as raised,
        ):
            ark_models.resolve_commit("main")
        self.assertEqual(raised.exception.code, "invalid_commit")

    def test_successful_raw_download_encodes_each_path_segment(self) -> None:
        relative = PurePosixPath("models", SLUG, "textures", "中文 image#1.png")
        with (
            patch.object(
                ark_models.urllib.request, "urlopen", return_value=FakeResponse(b"asset")
            ) as opened,
            patch.object(ark_models.time, "sleep") as sleep,
        ):
            self.assertEqual(ark_models._request_file(COMMIT, relative, limit=50), b"asset")
        self.assertEqual(opened.call_count, 1)
        self.assertEqual(
            opened.call_args.args[0].full_url,
            f"{ark_models.RAW_ROOT}/{COMMIT}/models/1038_whitw2_sale%2315/"
            "textures/%E4%B8%AD%E6%96%87%20image%231.png",
        )
        sleep.assert_not_called()

    def test_raw_retry_success_does_not_use_contents(self) -> None:
        with (
            patch.object(
                ark_models.urllib.request,
                "urlopen",
                side_effect=[TimeoutError(), ConnectionResetError(), FakeResponse(b"ok")],
            ) as opened,
            patch.object(ark_models.time, "sleep") as sleep,
        ):
            self.assertEqual(
                ark_models._request_file(COMMIT, PurePosixPath("models_data.json"), limit=20),
                b"ok",
            )
        self.assertEqual(opened.call_count, 3)
        self.assertTrue(
            all("raw.githubusercontent.com" in c.args[0].full_url for c in opened.call_args_list)
        )
        self.assertEqual(sleep.call_args_list, [call(1), call(2)])

    def test_transient_failures_exhaust_raw_then_use_same_commit_contents(self) -> None:
        failures = (
            TimeoutError("timeout"),
            urllib.error.URLError(TimeoutError("timeout")),
            ConnectionResetError("reset"),
            http.client.RemoteDisconnected("remote closed"),
            http.client.IncompleteRead(b"partial", 100),
            ssl.SSLEOFError("TLS closed"),
        )
        for failure in failures:
            with (
                self.subTest(failure=type(failure).__name__),
                patch.object(
                    ark_models.urllib.request,
                    "urlopen",
                    side_effect=[failure, failure, failure, raw_response(b"ok")],
                ) as opened,
                patch.object(ark_models.time, "sleep") as sleep,
            ):
                self.assertEqual(
                    ark_models._request_file(
                        COMMIT, PurePosixPath("models", SLUG, f"{STEM}.atlas"), limit=20
                    ),
                    b"ok",
                )
                self.assertEqual(opened.call_count, 4)
                final_request = opened.call_args.args[0]
                self.assertEqual(
                    final_request.full_url,
                    f"{ark_models.API_ROOT}/contents/models/1038_whitw2_sale%2315/"
                    f"build_char_1038_whitw2_sale%2315.atlas?ref={COMMIT}",
                )
                self.assertEqual(
                    final_request.get_header("Accept"), "application/vnd.github.raw+json"
                )
                self.assertEqual(sleep.call_args_list, [call(1), call(2)])

    def test_contents_has_its_own_bounded_retries(self) -> None:
        with (
            patch.object(
                ark_models.urllib.request,
                "urlopen",
                side_effect=[TimeoutError()] * 5 + [raw_response(b"ok")],
            ) as opened,
            patch.object(ark_models.time, "sleep") as sleep,
        ):
            self.assertEqual(
                ark_models._request_file(COMMIT, PurePosixPath("models_data.json"), limit=20),
                b"ok",
            )
        self.assertEqual(opened.call_count, 6)
        self.assertEqual(sleep.call_args_list, [call(1), call(2), call(1), call(2)])

    def test_retry_budget_exhaustion_reports_network_error(self) -> None:
        with (
            patch.object(
                ark_models.urllib.request, "urlopen", side_effect=TimeoutError("fixture timeout")
            ) as opened,
            patch.object(ark_models.time, "sleep") as sleep,
            self.assertRaises(ark_models.InstallerError) as raised,
        ):
            ark_models._request_file(COMMIT, PurePosixPath("models_data.json"), limit=20)
        self.assertEqual(raised.exception.code, "network_error")
        self.assertTrue(raised.exception.retryable)
        self.assertEqual(opened.call_count, 6)
        self.assertEqual(sleep.call_args_list, [call(1), call(2), call(1), call(2)])

    def test_partial_read_is_discarded_on_retry(self) -> None:
        failures = (
            TimeoutError("timeout during read"),
            ConnectionResetError("reset during read"),
            http.client.RemoteDisconnected("closed during read"),
            http.client.IncompleteRead(b"discard also", 100),
            ssl.SSLEOFError("EOF during read"),
        )
        for failure in failures:
            partial = FakeResponse(chunks=[b"discard me", failure])
            with (
                self.subTest(failure=type(failure).__name__),
                patch.object(
                    ark_models.urllib.request,
                    "urlopen",
                    side_effect=[partial, FakeResponse(b"complete")],
                ) as opened,
                patch.object(ark_models.time, "sleep") as sleep,
            ):
                self.assertEqual(
                    ark_models._request_file(COMMIT, PurePosixPath("asset"), limit=100),
                    b"complete",
                )
                self.assertTrue(partial.closed)
                self.assertEqual(opened.call_count, 2)
                sleep.assert_called_once_with(1)

    def test_content_length_short_read_is_retried(self) -> None:
        with (
            patch.object(
                ark_models.urllib.request,
                "urlopen",
                side_effect=[
                    FakeResponse(b"short", headers={"Content-Length": "20"}),
                    FakeResponse(b"complete", headers={"Content-Length": "8"}),
                ],
            ) as opened,
            patch.object(ark_models.time, "sleep") as sleep,
        ):
            self.assertEqual(
                ark_models._request_file(COMMIT, PurePosixPath("asset"), limit=100), b"complete"
            )
        self.assertEqual(opened.call_count, 2)
        sleep.assert_called_once_with(1)

    def test_non_retryable_errors_never_retry_or_fallback(self) -> None:
        cases = (
            ("missing", http_error(404), "not_found"),
            ("forbidden", http_error(403), "http_error"),
            ("http_error", http_error(500), "http_error"),
            ("certificate", ssl.SSLCertVerificationError("invalid certificate"), "network_error"),
            (
                "wrapped_certificate",
                urllib.error.URLError(ssl.SSLCertVerificationError("invalid certificate")),
                "network_error",
            ),
        )
        for name, failure, code in cases:
            with (
                self.subTest(name=name),
                patch.object(ark_models.urllib.request, "urlopen", side_effect=failure) as opened,
                patch.object(ark_models.time, "sleep") as sleep,
            ):
                with self.assertRaises(ark_models.InstallerError) as raised:
                    ark_models._request_file(COMMIT, PurePosixPath("asset"), limit=100)
                self.assertEqual(raised.exception.code, code)
                self.assertFalse(raised.exception.retryable)
                self.assertEqual(opened.call_count, 1)
                sleep.assert_not_called()

    def test_rate_limits_stop_and_preserve_retry_hints(self) -> None:
        cases = (
            (
                403,
                {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "1874826000"},
                "failure",
                "1874826000",
            ),
            (429, {"Retry-After": "60"}, "failure", "60"),
            (403, {"Retry-After": "120"}, "You have exceeded a secondary rate limit.", "120"),
            (403, {}, "You have exceeded a secondary rate limit.", None),
        )
        for status, headers, message, hint in cases:
            with (
                self.subTest(status=status, headers=headers),
                patch.object(
                    ark_models.urllib.request,
                    "urlopen",
                    side_effect=http_error(status, headers=headers, message=message),
                ) as opened,
                patch.object(ark_models.time, "sleep") as sleep,
            ):
                with self.assertRaises(ark_models.InstallerError) as raised:
                    ark_models._request_file(COMMIT, PurePosixPath("asset"), limit=100)
                self.assertEqual(raised.exception.code, "github_rate_limited")
                self.assertFalse(raised.exception.retryable)
                if hint:
                    self.assertIn(hint, str(raised.exception))
                self.assertEqual(opened.call_count, 1)
                sleep.assert_not_called()

    def test_size_and_invalid_response_errors_do_not_fallback(self) -> None:
        cases = (
            (FakeResponse(b"", headers={"Content-Length": "101"}), "download_too_large"),
            (FakeResponse(b"a" * 101), "download_too_large"),
            (FakeResponse(b"", headers={"Content-Length": "unknown"}), "invalid_response"),
            (FakeResponse(b"", headers={"Content-Length": "-1"}), "invalid_response"),
            (FakeResponse(b"long", headers={"Content-Length": "3"}), "invalid_response"),
        )
        for response, code in cases:
            with (
                self.subTest(code=code, headers=response.headers),
                patch.object(ark_models.urllib.request, "urlopen", return_value=response) as opened,
                patch.object(ark_models.time, "sleep") as sleep,
            ):
                with self.assertRaises(ark_models.InstallerError) as raised:
                    ark_models._request_file(COMMIT, PurePosixPath("asset"), limit=100)
                self.assertEqual(raised.exception.code, code)
                self.assertFalse(raised.exception.retryable)
                self.assertEqual(opened.call_count, 1)
                sleep.assert_not_called()

    def test_contents_accepts_explicit_raw_media_markers(self) -> None:
        for headers in (
            {"Content-Type": "application/vnd.github.raw+json; charset=utf-8"},
            {"Content-Type": "application/vnd.github.v3.raw"},
            {
                "Content-Type": "application/octet-stream",
                "X-GitHub-Media-Type": "github.v3; format=raw",
            },
        ):
            with (
                self.subTest(headers=headers),
                patch.object(
                    ark_models.urllib.request,
                    "urlopen",
                    side_effect=[TimeoutError()] * 3 + [FakeResponse(b"raw", headers=headers)],
                ),
                patch.object(ark_models.time, "sleep"),
            ):
                self.assertEqual(
                    ark_models._request_file(COMMIT, PurePosixPath("asset"), limit=100), b"raw"
                )

    def test_contents_rejects_metadata_or_unmarked_responses_without_retry(self) -> None:
        for headers in (
            {"Content-Type": "application/json", "X-GitHub-Media-Type": "github.v3; format=json"},
            {"Content-Type": "text/html"},
            {},
        ):
            with (
                self.subTest(headers=headers),
                patch.object(
                    ark_models.urllib.request,
                    "urlopen",
                    side_effect=[TimeoutError()] * 3
                    + [FakeResponse(b'{"type":"file","content":"cmF3"}', headers=headers)],
                ) as opened,
                patch.object(ark_models.time, "sleep") as sleep,
            ):
                with self.assertRaises(ark_models.InstallerError) as raised:
                    ark_models._request_file(COMMIT, PurePosixPath("asset"), limit=100)
                self.assertEqual(raised.exception.code, "invalid_response")
                self.assertFalse(raised.exception.retryable)
                self.assertEqual(opened.call_count, 4)
                self.assertEqual(sleep.call_args_list, [call(1), call(2)])

    def test_contents_fallback_keeps_the_smaller_size_limit(self) -> None:
        self.assertEqual(ark_models.MAX_CONTENTS_BYTES, 100_000_000)
        for requested_limit, declared_size in ((200_000_000, 100_000_001), (20, 21)):
            response = FakeResponse(
                headers={
                    "Content-Type": "application/vnd.github.raw+json",
                    "Content-Length": str(declared_size),
                }
            )
            with (
                self.subTest(requested_limit=requested_limit),
                patch.object(
                    ark_models.urllib.request,
                    "urlopen",
                    side_effect=[TimeoutError()] * 3 + [response],
                ) as opened,
                patch.object(ark_models.time, "sleep"),
            ):
                with self.assertRaises(ark_models.InstallerError) as raised:
                    ark_models._request_file(COMMIT, PurePosixPath("asset"), limit=requested_limit)
                self.assertEqual(raised.exception.code, "download_too_large")
                self.assertFalse(raised.exception.retryable)
                self.assertEqual(opened.call_count, 4)


class ArkModelsInstallTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.files = model_files()
        self.server = FileServer(self.files, fallback=True)
        opener_patch = patch.object(ark_models.urllib.request, "urlopen", side_effect=self.server)
        self.opened = opener_patch.start()
        self.addCleanup(opener_patch.stop)
        sleep_patch = patch.object(ark_models.time, "sleep")
        self.sleep = sleep_patch.start()
        self.addCleanup(sleep_patch.stop)
        self.args = SimpleNamespace(
            ref=COMMIT.upper(),
            slug=SLUG,
            models_dir=str(self.root),
            folder_name="fixture-model",
            acknowledge_noncommercial=True,
            dry_run=False,
        )

    def assert_install_error(self, code: str) -> None:
        with self.assertRaises(ark_models.InstallerError) as raised:
            ark_models._install(self.args)
        self.assertEqual(raised.exception.code, code)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_install_falls_back_for_catalog_and_every_asset_and_records_hashes(self) -> None:
        result = ark_models._install(self.args)
        self.assertTrue(result["ok"])
        self.assertFalse(result["willOverwrite"])
        self.assertEqual(result["resolvedCommit"], COMMIT)
        self.assertEqual(result["spineVersion"], "3.8.99")
        self.assertEqual(result["runtimeValidation"], "pending-agent-friend")
        destination = self.root / "fixture-model"
        self.assertEqual(Path(result["destination"]), destination)
        source = json.loads((destination / "ARK_MODELS_SOURCE.json").read_text(encoding="utf-8"))
        self.assertEqual(source["repository"], ark_models.REPOSITORY)
        self.assertEqual(source["commit"], COMMIT)
        self.assertEqual(source["sourcePath"], f"models/{SLUG}")
        self.assertEqual(source["model"]["skin"], "忒斯特收藏/XVII")
        self.assertEqual(source["model"]["spineVersion"], "3.8.99")
        self.assertEqual(len(source["files"]), 3)
        for entry in source["files"]:
            payload = self.files[f"models/{SLUG}/{entry['path']}"]
            self.assertEqual((destination / entry["path"]).read_bytes(), payload)
            self.assertEqual(entry["bytes"], len(payload))
            self.assertEqual(entry["sha256"], hashlib.sha256(payload).hexdigest())
        notice = (destination / "ARK_MODELS_NOTICE.txt").read_text(encoding="utf-8")
        self.assertIn(COMMIT, notice)
        self.assertIn("must not be used commercially", notice)
        self.assertEqual(self.opened.call_count, 16)
        self.assertEqual(self.sleep.call_args_list, [call(1), call(2)] * 4)

    def test_dry_run_only_reads_catalog_and_never_creates_directory(self) -> None:
        self.args.dry_run = True
        self.args.acknowledge_noncommercial = False
        result = ark_models._install(self.args)
        self.assertTrue(result["ok"])
        self.assertTrue(result["dryRun"])
        self.assertFalse(result["willOverwrite"])
        self.assertEqual(result["model"]["slug"], SLUG)
        self.assertEqual(result["model"]["skin"], "忒斯特收藏/XVII")
        self.assertEqual(list(self.root.iterdir()), [])
        self.assertEqual(self.opened.call_count, 4)
        self.assertTrue(
            all("models_data.json" in request.full_url for request in self.server.requests)
        )

    def test_install_requires_noncommercial_ack_before_asset_download(self) -> None:
        self.args.acknowledge_noncommercial = False
        self.assert_install_error("noncommercial_ack_required")
        self.assertEqual(self.opened.call_count, 4)

    def test_non_operator_record_is_not_installable(self) -> None:
        catalog = json.loads(self.files["models_data.json"])
        catalog["data"][SLUG]["type"] = "Enemy"
        self.files["models_data.json"] = json.dumps(catalog).encode()
        self.assert_install_error("model_not_found")
        self.assertEqual(self.opened.call_count, 4)

    def test_selected_slug_does_not_fall_back_to_another_skin(self) -> None:
        self.args.slug = "1038_whitw2_different_skin"
        self.assert_install_error("model_not_found")
        self.assertEqual(self.opened.call_count, 4)

    def test_invalid_catalog_stops_without_downloading_assets(self) -> None:
        self.files["models_data.json"] = b"not JSON"
        self.assert_install_error("invalid_upstream_json")
        self.assertEqual(self.opened.call_count, 4)

    def test_unsupported_spine_version_leaves_no_model_or_partial_files(self) -> None:
        self.files[f"models/{SLUG}/{STEM}.skel"] = binary_string("hash") + binary_string("3.8.75")
        self.assert_install_error("unsupported_spine_version")
        self.assertFalse(any(".png" in request.full_url for request in self.server.requests))

    def test_atlas_path_escape_never_downloads_or_writes_outside_model(self) -> None:
        self.files[f"models/{SLUG}/{STEM}.atlas"] = b"../outside.png\nsize: 1,1\n"
        self.assert_install_error("unsafe_upstream_path")
        self.assertFalse(any("outside.png" in request.full_url for request in self.server.requests))

    def test_missing_atlas_texture_leaves_no_model_or_partial_files(self) -> None:
        self.server.fail_path = f"models/{SLUG}/{STEM}.png"
        self.assert_install_error("not_found")
        self.assertEqual(self.opened.call_count, 16)

    def test_total_model_limit_remains_enforced_after_fallback(self) -> None:
        with patch.object(ark_models, "MAX_MODEL_BYTES", 1):
            self.assert_install_error("model_too_large")

    def test_existing_destination_is_preserved_without_asset_download(self) -> None:
        destination = self.root / "fixture-model"
        destination.mkdir()
        marker = destination / "keep.txt"
        marker.write_bytes(b"existing model")
        with self.assertRaises(ark_models.InstallerError) as raised:
            ark_models._install(self.args)
        self.assertEqual(raised.exception.code, "destination_exists")
        self.assertEqual(marker.read_bytes(), b"existing model")
        self.assertEqual(list(destination.iterdir()), [marker])
        self.assertEqual(self.opened.call_count, 4)


class ArkModelsTests(unittest.TestCase):
    def test_search_returns_name_and_skin_matches_without_guessing(self) -> None:
        records = [
            {
                "slug": "002_amiya",
                "name": "阿米娅",
                "appellation": "Amiya",
                "skin": "默认服装",
                "style": "BuildingDefault",
                "assets": {},
            },
            {
                "slug": "002_amiya_winter",
                "name": "阿米娅",
                "appellation": "Amiya",
                "skin": "报童",
                "style": "BuildingSkin",
                "assets": {},
            },
        ]
        matches = ark_models.search_records(records, "阿米娅", limit=20)
        self.assertEqual([item["slug"] for item in matches], ["002_amiya", "002_amiya_winter"])

    def test_spine_version_accepts_supported_binary_header(self) -> None:
        raw = binary_string("hash") + binary_string("3.8.99") + b"payload"
        self.assertEqual(ark_models.spine_version(raw), "3.8.99")

    def test_spine_version_rejects_unsupported_release(self) -> None:
        raw = binary_string("hash") + binary_string("3.8.75") + b"payload"
        with self.assertRaisesRegex(ark_models.InstallerError, "unsupported Spine runtime"):
            ark_models.spine_version(raw)

    def test_atlas_pages_reject_path_escape(self) -> None:
        with self.assertRaisesRegex(ark_models.InstallerError, "unsafe upstream path"):
            ark_models.atlas_texture_pages(b"../outside.png\nsize: 1,1\n")

    def test_destination_requires_absolute_existing_directory_and_no_collision(self) -> None:
        with self.assertRaisesRegex(ark_models.InstallerError, "absolute path"):
            ark_models._destination("relative", "model")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _, destination = ark_models._destination(str(root), "model")
            self.assertEqual(destination, root.resolve() / "model")
            destination.mkdir()
            with self.assertRaisesRegex(ark_models.InstallerError, "already exists"):
                ark_models._destination(str(root), "model")

    @unittest.skipUnless(
        os.environ.get("ARK_MODELS_LIVE_SMOKE") == "1",
        "set ARK_MODELS_LIVE_SMOKE=1 to download one model into a temporary directory",
    )
    def test_live_amiya_install_into_temporary_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            result = ark_models._install(
                SimpleNamespace(
                    ref="main",
                    slug="002_amiya",
                    models_dir=temporary,
                    folder_name="amiya-smoke",
                    acknowledge_noncommercial=True,
                    dry_run=False,
                )
            )
            self.assertTrue(result["ok"])
            self.assertEqual(result["runtimeValidation"], "pending-agent-friend")
            installed = Path(result["destination"])
            expected = {
                "build_char_002_amiya.atlas",
                "build_char_002_amiya.png",
                "build_char_002_amiya.skel",
                "ARK_MODELS_SOURCE.json",
                "ARK_MODELS_NOTICE.txt",
            }
            self.assertTrue(expected.issubset({path.name for path in installed.iterdir()}))
            source = json.loads((installed / "ARK_MODELS_SOURCE.json").read_text(encoding="utf-8"))
            self.assertRegex(source["commit"], r"^[0-9a-f]{40}$")
            self.assertTrue(source["model"]["spineVersion"].startswith("3.8."))


if __name__ == "__main__":
    unittest.main()
