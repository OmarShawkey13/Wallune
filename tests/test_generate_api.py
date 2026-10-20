import base64
import contextlib
import io
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


VALID_IMAGE_BYTES = {
    ".png": base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAIAAAADCAIAAAA2iEnWAAAAFElEQVR4nGPkUbJgYGBgYgADKAUAB7oAbH+xUAEAAAAASUVORK5CYII="
    ),
    ".jpg": base64.b64decode(
        "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/2wBDAQkJCQwLDBgNDRgyIRwhMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjL/wAARCAADAAIDASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwDx2iiiu04z/9k="
    ),
    ".webp": base64.b64decode(
        "UklGRjAAAABXRUJQVlA4ICQAAABQAQCdASoCAAMAAUAmJQBOgC6gAP77LkvF3YjjJ4dVU9ffoAA="
    ),
}


def write_valid_image(path, extension):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(VALID_IMAGE_BYTES[extension])


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

    def api_snapshot(self):
        root = Path("api/v1")
        return {
            path.relative_to(root).as_posix(): path.read_bytes()
            for path in root.rglob("*")
            if path.is_file()
        }

    def metadata(self):
        return json.loads(Path("api/v1/wallpaper_ids.json").read_text(encoding="utf-8"))["wallpapers"]


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

    def test_generation_does_not_emit_dart_models(self):
        write_png(Path("images/Nature/one.jpg"))
        self.generate()
        self.assertFalse(Path("api/v1/models.dart").exists())

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

    def test_valid_jpeg_png_and_webp_fixtures_have_dimensions(self):
        for extension in (".jpg", ".png", ".webp"):
            path = Path("images/Fixtures") / f"valid{extension}"
            write_valid_image(path, extension)
            self.assertEqual(generator.get_image_size(str(path)), (2, 3))
        self.generate()
        self.assertEqual(len(self.records()), 3)

    def test_replacing_bytes_at_same_path_retires_old_identity(self):
        path = Path("images/Nature/replaced.jpg")
        write_png(path, marker=b"first")
        self.generate()
        old = self.records()[0]
        old_timestamp = old["updated_at"]
        write_png(path, marker=b"second")
        with mock.patch.object(generator, "utc_iso", return_value="2026-01-02T03:04:05Z"):
            self.generate()
        current = self.records()[0]
        self.assertNotEqual(current["id"], old["id"])
        self.assertNotEqual(current["updated_at"], old_timestamp)
        retired = [item for item in self.metadata() if item["id"] == old["id"]][0]
        self.assertTrue(retired["retired"])
        generator.validate_generated_api()

    def test_existing_identity_metadata_is_authoritative_after_legacy_migration(self):
        path = Path("images/Nature/replaced.jpg")
        write_png(path, marker=b"first")
        self.generate()
        old = self.records()[0]
        metadata_path = Path("api/v1/wallpaper_ids.json")
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        for record in metadata["wallpapers"]:
            record.pop("updated_at", None)
        metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
        write_png(path, marker=b"second")
        with mock.patch.object(generator, "utc_iso", return_value="2026-01-02T03:04:05Z"):
            self.generate()
        current = self.records()[0]
        self.assertNotEqual(current["id"], old["id"])
        self.assertTrue([item for item in self.metadata() if item["id"] == old["id"]][0]["retired"])

    def test_legacy_migration_preserves_valid_timestamp_and_has_fixed_fallback(self):
        path = Path("images/Nature/legacy.jpg")
        write_png(path, marker=b"legacy")
        legacy_id = "123e4567-e89b-42d3-a456-426614174000"
        legacy = {
            "id": legacy_id,
            "title": "Legacy",
            "category": "Nature",
            "image_url": generator._url("Nature", "legacy.jpg"),
            "size": path.stat().st_size,
            "updated_at": "2024-01-02T03:04:05Z",
            "width": 100,
            "height": 200,
        }
        Path("api/v1/wallpapers").mkdir(parents=True)
        Path("api/v1/wallpapers/page_1.json").write_text(
            json.dumps({"data": [legacy]}), encoding="utf-8"
        )
        self.generate()
        migrated = [item for item in self.metadata() if item["id"] == legacy_id][0]
        self.assertEqual(migrated["updated_at"], "2024-01-02T03:04:05Z")

        metadata_path = Path("api/v1/wallpaper_ids.json")
        metadata_path.unlink()
        legacy["updated_at"] = "not-a-timestamp"
        Path("api/v1/wallpapers/page_1.json").write_text(
            json.dumps({"data": [legacy]}), encoding="utf-8"
        )
        self.generate()
        migrated = [item for item in self.metadata() if item["id"] == legacy_id][0]
        self.assertEqual(migrated["updated_at"], "2000-01-01T00:00:00Z")

    def test_timestamp_survives_mtime_changes_and_copy_like_regeneration(self):
        path = Path("images/Nature/stable.jpg")
        write_png(path, marker=b"stable")
        self.generate()
        first = self.records()[0]
        first_config = self.config()
        os.utime(path, (1, 1))
        self.generate()
        second = self.records()[0]
        self.assertEqual(second["id"], first["id"])
        self.assertEqual(second["updated_at"], first["updated_at"])
        self.assertEqual(self.config()["content_version"], first_config["content_version"])

    def test_content_version_changes_for_pagination_setting_then_stabilizes(self):
        write_png(Path("images/Nature/one.jpg"), marker=b"one")
        write_png(Path("images/Nature/two.jpg"), marker=b"two")
        self.generate()
        first = self.config()["content_version"]
        with mock.patch.object(generator, "ITEMS_PER_PAGE", 1):
            self.generate()
            second = self.config()["content_version"]
            self.generate()
            third = self.config()["content_version"]
        self.assertNotEqual(first, second)
        self.assertEqual(second, third)

    def test_corrupt_identity_metadata_fails_without_resetting_ids(self):
        write_png(Path("images/Nature/one.jpg"))
        self.generate()
        page_before = Path("api/v1/wallpapers/page_1.json").read_bytes()
        Path("api/v1/wallpaper_ids.json").write_text(
            json.dumps({"schema_version": 2, "wallpapers": [{"id": self.records()[0]["id"]}]}),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ValueError, "missing required fields"):
            self.generate()
        self.assertEqual(Path("api/v1/wallpapers/page_1.json").read_bytes(), page_before)

    def test_empty_identity_metadata_refuses_to_reset_existing_ids(self):
        write_png(Path("images/Nature/one.jpg"))
        self.generate()
        page_before = Path("api/v1/wallpapers/page_1.json").read_bytes()
        Path("api/v1/wallpaper_ids.json").write_text(
            json.dumps({"schema_version": 2, "wallpapers": []}), encoding="utf-8"
        )
        with self.assertRaisesRegex(ValueError, "refusing to reset wallpaper IDs"):
            self.generate()
        self.assertEqual(Path("api/v1/wallpapers/page_1.json").read_bytes(), page_before)

    def test_validation_rejects_incorrect_image_metadata_and_identity_hash(self):
        write_valid_image(Path("images/Nature/one.jpg"), ".jpg")
        self.generate()
        page_path = Path("api/v1/wallpapers/page_1.json")
        original_page = json.loads(page_path.read_text(encoding="utf-8"))
        for field, value in (("size", 1), ("width", 1), ("height", 1)):
            page = json.loads(json.dumps(original_page))
            page["data"][0][field] = value
            page_path.write_text(json.dumps(page), encoding="utf-8")
            with self.assertRaises(ValueError):
                generator.validate_generated_api()
        page_path.write_text(json.dumps(original_page), encoding="utf-8")
        metadata_path = Path("api/v1/wallpaper_ids.json")
        original_metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        original_metadata["wallpapers"][0]["content_hash"] = "0" * 64
        metadata_path.write_text(json.dumps(original_metadata), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "content hash"):
            generator.validate_generated_api()

    def test_validation_rejects_page_gaps_and_extra_search_records(self):
        for index in range(21):
            write_png(Path("images/Nature") / f"image_{index}.jpg", marker=bytes([index]))
        self.generate()
        page_two = Path("api/v1/wallpapers/page_2.json")
        page_three = Path("api/v1/wallpapers/page_3.json")
        page_two.rename(page_three)
        with self.assertRaisesRegex(ValueError, "page filenames"):
            generator.validate_generated_api()
        page_three.rename(page_two)
        search_path = Path("api/v1/search_index.json")
        search = json.loads(search_path.read_text(encoding="utf-8"))
        search.append(search[0])
        search_path.write_text(json.dumps(search), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "duplicate IDs"):
            generator.validate_generated_api()

    def test_validation_rejects_invalid_catalog_hash(self):
        write_png(Path("images/Nature/one.jpg"))
        self.generate()
        config_path = Path("api/v1/config.json")
        config = self.config()
        config["catalog_hash"] = "0" * 64
        config_path.write_text(json.dumps(config), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "catalog_hash"):
            generator.validate_generated_api()

    def test_write_failure_preserves_previous_output(self):
        write_png(Path("images/Nature/one.jpg"), marker=b"one")
        self.generate()
        before = self.api_snapshot()
        write_png(Path("images/Nature/two.jpg"), marker=b"two")
        with mock.patch.object(generator, "_write_json", side_effect=OSError("disk full")):
            with self.assertRaisesRegex(OSError, "disk full"):
                self.generate()
        self.assertEqual(self.api_snapshot(), before)
        self.assertEqual(list(Path("api").glob(".v1.staging-*")), [])

    def test_post_replace_validation_failure_rolls_back_previous_output(self):
        write_png(Path("images/Nature/one.jpg"), marker=b"one")
        self.generate()
        before = self.api_snapshot()
        write_png(Path("images/Nature/two.jpg"), marker=b"two")
        real_validate = generator.validate_generated_api
        calls = 0

        def validate_then_fail(api_dir=None):
            nonlocal calls
            calls += 1
            if calls == 1:
                return real_validate(api_dir)
            raise ValueError("validation after replacement")

        with mock.patch.object(generator, "validate_generated_api", side_effect=validate_then_fail):
            with self.assertRaisesRegex(ValueError, "validation after replacement"):
                self.generate()
        self.assertEqual(self.api_snapshot(), before)
        self.assertEqual(list(Path("api").glob(".v1.staging-*")), [])

    def test_validate_only_does_not_write_and_reports_failure(self):
        write_png(Path("images/Nature/one.jpg"))
        self.generate()
        before = self.api_snapshot()
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(generator.main(["--validate-only"]), 0)
        self.assertEqual(self.api_snapshot(), before)
        config_path = Path("api/v1/config.json")
        config = self.config()
        config["catalog_hash"] = "0" * 64
        config_path.write_text(json.dumps(config), encoding="utf-8")
        error = io.StringIO()
        with contextlib.redirect_stderr(error):
            self.assertEqual(generator.main(["--validate-only"]), 1)
        self.assertIn("validation failed", error.getvalue())


if __name__ == "__main__":
    unittest.main()
