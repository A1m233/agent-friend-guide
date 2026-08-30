from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

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
