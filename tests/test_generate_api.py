import json
import os
import struct
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import generate_api as generator


def write_png(path, width=100, height=200, marker=b""):
    path.parent.mkdir(parents=True, exist_ok=True)
    header = (
        b"\x89PNG\r\n\x1a\n"
        + struct.pack(">I", 13)
        + b"IHDR"
        + struct.pack(">II", width, height)
        + b"\x08\x02\x00\x00\x00"
    )
    path.write_bytes(header + marker)


class GeneratorFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=str(ROOT / "tests"))
        self.cwd = os.getcwd()
        os.chdir(self.temp.name)
        Path("images").mkdir()
        self.patches = [
            mock.patch.object(generator, "IMAGE_DIR", "images"),
            mock.patch.object(generator, "API_DIR", "api/v1"),
            mock.patch.object(generator, "GITHUB_USERNAME", "OmarShawkey13"),
            mock.patch.object(generator, "GITHUB_REPO_NAME", "Wallune"),
            mock.patch.object(generator, "BRANCH", "main"),
        ]
        for patcher in self.patches:
            patcher.start()

    def tearDown(self):
        for patcher in reversed(self.patches):
            patcher.stop()
        os.chdir(self.cwd)
        self.temp.cleanup()

    def generate(self):
        return generator.process_images()

    def records(self):
        records = []
        for page in sorted(Path("api/v1/wallpapers").glob("page_*.json")):
            records.extend(json.loads(page.read_text(encoding="utf-8"))["data"])
        return records

    def config(self):
        return json.loads(Path("api/v1/config.json").read_text(encoding="utf-8"))


class StaticGeneratorTests(GeneratorFixture):
    def test_zero_images_generates_empty_catalog(self):
        summary = self.generate()
        self.assertEqual(summary["total_items"], 0)
        self.assertEqual(summary["total_pages"], 0)
        self.assertEqual(self.config()["total_pages"], 0)
        self.assertEqual(list(Path("api/v1/wallpapers").glob("page_*.json")), [])

    def test_one_image_pagination(self):
        write_png(Path("images/Nature/one.jpg"))
        self.generate()
        page = json.loads(Path("api/v1/wallpapers/page_1.json").read_text())
        self.assertEqual(len(page["data"]), 1)
        self.assertFalse(page["has_next"])
        self.assertFalse(page["has_prev"])

    def test_exactly_twenty_images(self):
        for index in range(20):
            write_png(Path("images/Nature") / f"image_{index}.jpg", marker=bytes([index]))
        self.generate()
        pages = sorted(Path("api/v1/wallpapers").glob("page_*.json"))
        self.assertEqual(len(pages), 1)
        self.assertEqual(len(self.records()), 20)
        self.assertFalse(json.loads(pages[0].read_text())["has_next"])

    def test_twenty_one_images_creates_two_pages(self):
        for index in range(21):
            write_png(Path("images/Nature") / f"image_{index}.jpg", marker=bytes([index]))
        self.generate()
        pages = sorted(Path("api/v1/wallpapers").glob("page_*.json"))
        self.assertEqual(len(pages), 2)
        self.assertEqual(len(json.loads(pages[0].read_text())["data"]), 20)
        self.assertEqual(len(json.loads(pages[1].read_text())["data"]), 1)

    def test_multiple_categories_duplicate_names_and_unsupported_extension(self):
        write_png(Path("images/Animals/shared.jpg"), marker=b"a")
        write_png(Path("images/Cars/shared.jpg"), marker=b"b")
        Path("images/Cars/ignored.gif").write_bytes(b"GIF89a")
        self.generate()
        records = self.records()
        self.assertEqual(len(records), 2)
        self.assertEqual(len({item["id"] for item in records}), 2)
        self.assertEqual(len({item["image_url"] for item in records}), 2)
        categories = json.loads(Path("api/v1/categories.json").read_text())
        self.assertEqual({item["name"] for item in categories}, {"Animals", "Cars"})
        self.assertEqual(len({item["id"] for item in categories}), 2)
        for category in categories:
            self.assertEqual(category["id"], generator._category_id(category["name"]))

    def test_duplicate_image_bytes_fail_generation(self):
        write_png(Path("images/Nature/first.jpg"), marker=b"same")
        write_png(Path("images/Nature/second.jpg"), marker=b"same")
        with self.assertRaisesRegex(ValueError, "Duplicate image bytes"):
            self.generate()

    def test_stale_page_cleanup(self):
        for index in range(21):
            write_png(Path("images/Nature") / f"image_{index}.jpg", marker=bytes([index]))
        self.generate()
        self.assertEqual(len(list(Path("api/v1/wallpapers").glob("page_*.json"))), 2)
        Path("api/v1/wallpapers/page_999.json").write_text("{}")
        (Path("images/Nature") / "image_20.jpg").unlink()
        self.generate()
        names = sorted(path.name for path in Path("api/v1/wallpapers").glob("page_*.json"))
        self.assertEqual(names, ["page_1.json"])
        self.assertFalse(Path("api/v1/wallpapers/page_999.json").exists())

    def test_id_survives_repository_and_branch_url_changes(self):
        write_png(Path("images/Nature/one.jpg"))
        self.generate()
        old = self.records()[0]
        with mock.patch.object(generator, "GITHUB_REPO_NAME", "OtherRepo"), mock.patch.object(generator, "BRANCH", "feature"):
            self.generate()
        current = self.records()[0]
        self.assertEqual(old["id"], current["id"])
        self.assertIn("/OtherRepo/feature/", current["image_url"])

    def test_rename_preserves_id_and_delete_does_not_reuse_id(self):
        first = Path("images/Nature/old_name.jpg")
        second = Path("images/Nature/to_delete.jpg")
        write_png(first, marker=b"first")
        write_png(second, marker=b"second")
        self.generate()
        initial = {item["title"]: item["id"] for item in self.records()}
        Path("images/Cars").mkdir(parents=True)
        first.rename(Path("images/Cars/renamed.jpg"))
        second.unlink()
        write_png(Path("images/Nature/new.jpg"), marker=b"new")
        self.generate()
        current = {item["title"]: item["id"] for item in self.records()}
        self.assertEqual(current["Renamed"], initial["Old Name"])
        self.assertNotEqual(current["New"], initial["To Delete"])
        metadata = json.loads(Path("api/v1/wallpaper_ids.json").read_text())["wallpapers"]
        retired = [item for item in metadata if item["id"] == initial["To Delete"]][0]
        self.assertTrue(retired["retired"])

    def test_utc_search_and_config_version(self):
        write_png(Path("images/My Category/a+b (wall).jpg"))
        self.generate()
        first_config = self.config()
        second_url = self.records()[0]["image_url"]
        self.assertIn("My%20Category", second_url)
        self.assertIn("a%2Bb%20%28wall%29.jpg", second_url)
        datetime.fromisoformat(first_config["generated_at"].replace("Z", "+00:00"))
        self.assertEqual(first_config["generated_at"][-1], "Z")
        search = json.loads(Path("api/v1/search_index.json").read_text())
        self.assertEqual(set(search[0]), {"id", "title", "category", "image_url", "size", "updated_at", "width", "height"})
        self.generate()
        self.assertEqual(self.config()["content_version"], first_config["content_version"])

    def test_validation_rejects_invalid_page(self):
        write_png(Path("images/Nature/one.jpg"))
        self.generate()
        page_path = Path("api/v1/wallpapers/page_1.json")
        page = json.loads(page_path.read_text())
        page["has_next"] = True
        page_path.write_text(json.dumps(page))
        with self.assertRaises(ValueError):
            generator.validate_generated_api()

    def test_invalid_dimensions_fail_generation(self):
        bad = Path("images/Nature/bad.jpg")
        bad.parent.mkdir(parents=True, exist_ok=True)
        bad.write_bytes(b"not-an-image")
        with self.assertRaises(ValueError):
            self.generate()


if __name__ == "__main__":
    unittest.main()
