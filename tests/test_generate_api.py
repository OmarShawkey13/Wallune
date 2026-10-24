import base64
import binascii
import contextlib
import io
import json
import os
import struct
import sys
import tempfile
import unittest
import zlib
from datetime import datetime
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import generate_api as generator


def write_png(path, width=100, height=200, marker=b""):
    path.parent.mkdir(parents=True, exist_ok=True)
    seed = sum(marker) % 256

    def chunk(name, data):
        payload = name + data
        return struct.pack(">I", len(data)) + payload + struct.pack(">I", binascii.crc32(payload) & 0xFFFFFFFF)

    rows = bytearray()
    for y in range(height):
        rows.append(0)
        for x in range(width):
            rows.extend(((seed + x + y) % 256, (seed + x * 2) % 256, (seed + y * 3) % 256))
    image = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">II5B", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(rows))
        + chunk(b"IEND", b"")
    )
    path.write_bytes(image)


def add_png_text(path, value):
    contents = path.read_bytes()
    payload = b"Comment\x00" + value
    chunk_data = b"tEXt" + payload
    chunk = (
        struct.pack(">I", len(payload))
        + chunk_data
        + struct.pack(">I", binascii.crc32(chunk_data) & 0xFFFFFFFF)
    )
    iend = contents.rfind(b"\x00\x00\x00\x00IEND\xaeB`\x82")
    if iend < 0:
        raise AssertionError("PNG is missing its IEND chunk")
    path.write_bytes(contents[:iend] + chunk + contents[iend:])


def replace_png_text(path, old_value, new_value):
    if len(old_value) != len(new_value):
        raise AssertionError("Replacement PNG text must have the same length")
    contents = path.read_bytes()
    old_chunk_data = b"tEXtComment\x00" + old_value
    offset = contents.find(old_chunk_data)
    if offset < 4:
        raise AssertionError("PNG text chunk was not found")
    new_payload = b"Comment\x00" + new_value
    new_chunk_data = b"tEXt" + new_payload
    new_chunk = (
        struct.pack(">I", len(new_payload))
        + new_chunk_data
        + struct.pack(">I", binascii.crc32(new_chunk_data) & 0xFFFFFFFF)
    )
    chunk_start = offset - 4
    chunk_end = offset + len(old_chunk_data) + 4
    path.write_bytes(contents[:chunk_start] + new_chunk + contents[chunk_end:])


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

    def test_rename_preserves_content_id_and_new_image_gets_its_own_id(self):
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
        with mock.patch.object(generator, "_write_thumbnail", wraps=generator._write_thumbnail) as write_thumb:
            self.generate()
        self.assertEqual(write_thumb.call_count, 1)
        current = {item["title"]: item["id"] for item in self.records()}
        self.assertEqual(current["Renamed"], initial["Old Name"])
        self.assertNotEqual(current["New"], initial["To Delete"])
        self.assertEqual(len(list(Path("api/v1/thumbnails").rglob("*.webp"))), 2)
        self.assertFalse(Path("api/v1/wallpaper_ids.json").exists())

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
        self.assertEqual(
            set(search[0]),
            {"id", "title", "category", "image_path", "thumbnail_path", "width", "height"},
        )
        self.assertTrue(search[0]["image_path"].startswith("../../images/My%20Category/"))
        self.assertTrue(search[0]["image_path"].endswith("a%2Bb%20%28wall%29.jpg"))
        self.assertTrue(search[0]["thumbnail_path"].startswith("thumbnails/My%20Category/"))
        self.assertEqual(first_config["search_schema_version"], generator.SEARCH_SCHEMA_VERSION)
        self.assertEqual(first_config["thumbnail_version"], generator.THUMBNAIL_VERSION)
        self.assertEqual(first_config["wallpaper_id_version"], generator.WALLPAPER_ID_VERSION)
        self.assertIn("thumbnail_url", self.records()[0])
        thumbnail = Path("api/v1") / generator._thumbnail_relative(self.records()[0]["category"], self.records()[0]["id"])
        self.assertTrue(thumbnail.is_file())
        thumbnail_dimensions = generator.get_image_size(str(thumbnail))
        self.assertTrue(thumbnail_dimensions)
        self.assertLessEqual(thumbnail_dimensions[0], generator.THUMBNAIL_MAX_SIZE[0])
        self.assertLessEqual(thumbnail_dimensions[1], generator.THUMBNAIL_MAX_SIZE[1])
        self.generate()
        self.assertEqual(self.config()["content_version"], first_config["content_version"])
        self.assertEqual(self.config()["generated_at"], first_config["generated_at"])

    def test_v2_can_be_generated_and_validated_without_changing_v1(self):
        write_png(Path("images/Nature/one.jpg"))
        self.generate()
        v1_snapshot = self.api_snapshot()
        v1_id = self.records()[0]["id"]

        summary = generator.process_images("api/v2", 2)
        self.assertEqual(summary["total_items"], 1)
        v2_config = json.loads(Path("api/v2/config.json").read_text(encoding="utf-8"))
        v2_page = json.loads(Path("api/v2/wallpapers/page_1.json").read_text(encoding="utf-8"))
        v2_search = json.loads(Path("api/v2/search_index.json").read_text(encoding="utf-8"))
        self.assertEqual(v2_config["api_version"], 2)
        self.assertEqual(v2_config["wallpaper_id_version"], generator.WALLPAPER_ID_VERSION)
        self.assertEqual(v2_page["data"][0]["id"], v1_id)
        self.assertIn("/api/v2/thumbnails/", v2_page["data"][0]["thumbnail_url"])
        self.assertEqual(
            set(v2_search[0]),
            {"id", "title", "category", "image_path", "width", "height", "thumbnail_path"},
        )
        self.assertEqual(generator.validate_generated_api("api/v2", 2)["total_items"], 1)
        self.assertEqual(self.api_snapshot(), v1_snapshot)

    def test_existing_thumbnails_are_reused_and_only_new_images_are_generated(self):
        write_png(Path("images/Nature/first.jpg"), marker=b"first")
        self.generate()

        with mock.patch.object(generator, "_write_thumbnail", wraps=generator._write_thumbnail) as write_thumb:
            self.generate()
        write_thumb.assert_not_called()

        write_png(Path("images/Nature/second.jpg"), marker=b"second")
        with mock.patch.object(generator, "_write_thumbnail", wraps=generator._write_thumbnail) as write_thumb:
            self.generate()
        self.assertEqual(write_thumb.call_count, 1)
        self.assertEqual(len(list(Path("api/v1/thumbnails").rglob("*.webp"))), 2)

    def test_corrupt_cached_thumbnail_is_regenerated(self):
        write_png(Path("images/Nature/one.jpg"))
        self.generate()
        record = self.records()[0]
        thumbnail = Path("api/v1") / generator._thumbnail_relative(record["category"], record["id"])
        thumbnail.write_bytes(b"not a webp")

        with mock.patch.object(generator, "_write_thumbnail", wraps=generator._write_thumbnail) as write_thumb:
            self.generate()

        write_thumb.assert_called_once()
        self.assertTrue(generator._thumbnail_is_valid(thumbnail))

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

    def test_replacing_bytes_at_same_path_gets_a_new_content_id(self):
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
        self.assertEqual(current["id"], generator._wallpaper_id(generator._sha256(path)))
        self.assertFalse(Path("api/v1/wallpaper_ids.json").exists())
        generator.validate_generated_api()

    def test_generator_does_not_create_wallpaper_id_ledger(self):
        image = Path("images/Nature/one.jpg")
        write_png(image)
        self.generate()
        self.assertFalse(Path("api/v1/wallpaper_ids.json").exists())
        self.assertEqual(
            self.records()[0]["id"],
            generator._wallpaper_id(generator._sha256(image)),
        )

    def test_legacy_migration_refreshes_timestamp_when_bytes_change_but_thumbnail_does_not(self):
        image = Path("images/Nature/one.jpg")
        write_png(image)
        old_marker = b"old-tag1"
        new_marker = b"new-tag2"
        add_png_text(image, old_marker)
        previous_timestamp = "2025-03-04T05:06:07Z"
        current_timestamp = "2026-04-05T06:07:08Z"
        with mock.patch.object(generator, "utc_iso", return_value=previous_timestamp):
            self.generate()

        page_path = Path("api/v1/wallpapers/page_1.json")
        page = json.loads(page_path.read_text(encoding="utf-8"))
        previous = page["data"][0]
        previous_id = previous["id"]
        previous_hash = generator._sha256(image)
        previous_thumbnail_path = Path("api/v1") / generator._thumbnail_relative(
            previous["category"], previous_id
        )
        previous_thumbnail = previous_thumbnail_path.read_bytes()

        replace_png_text(image, old_marker, new_marker)
        os.utime(image, (1, 1))
        self.assertEqual(image.stat().st_size, previous["size"])
        self.assertEqual(
            generator.get_image_size(str(image)),
            (previous["width"], previous["height"]),
        )
        self.assertNotEqual(generator._sha256(image), previous_hash)
        self.assertEqual(generator._render_thumbnail_bytes(image), previous_thumbnail)

        legacy_id = "123e4567-e89b-42d3-a456-426614174000"
        legacy_thumbnail_path = Path("api/v1") / generator._thumbnail_relative(
            previous["category"], legacy_id
        )
        legacy_thumbnail_path.parent.mkdir(parents=True, exist_ok=True)
        previous_thumbnail_path.rename(legacy_thumbnail_path)
        previous["id"] = legacy_id
        previous["thumbnail_url"] = generator._thumbnail_url(previous["category"], legacy_id)
        page_path.write_text(json.dumps(page), encoding="utf-8")
        config = self.config()
        config.pop("wallpaper_id_version")
        Path("api/v1/config.json").write_text(json.dumps(config), encoding="utf-8")

        with mock.patch.object(generator, "utc_iso", return_value=current_timestamp):
            self.generate()

        current = self.records()[0]
        self.assertEqual(current["id"], generator._wallpaper_id(generator._sha256(image)))
        self.assertNotEqual(current["updated_at"], previous_timestamp)
        self.assertEqual(current["updated_at"], current_timestamp)
        current_thumbnail_path = Path("api/v1") / generator._thumbnail_relative(
            current["category"], current["id"]
        )
        self.assertEqual(current_thumbnail_path.read_bytes(), previous_thumbnail)

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

    def test_validation_rejects_incorrect_image_metadata_and_content_id(self):
        source = Path("images/Nature/one.jpg")
        write_valid_image(source, ".jpg")
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
        write_png(source, marker=b"different bytes")
        with self.assertRaisesRegex(ValueError, "ID does not match the image content"):
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
        calls = 0

        def validate_then_fail(api_dir=None, *args, **kwargs):
            nonlocal calls
            calls += 1
            raise ValueError("validation after replacement")

        with mock.patch.object(generator, "validate_generated_api", side_effect=validate_then_fail):
            with self.assertRaisesRegex(ValueError, "validation after replacement"):
                self.generate()
        self.assertEqual(self.api_snapshot(), before)
        self.assertEqual(calls, 1)
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
