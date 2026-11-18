"""Core engine tests. Run with:  python -m unittest discover -s tests -v"""
from __future__ import annotations

import csv
import hashlib
import io
import os
import random
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image, ImageChops, ImageCms

from core.batch_runner import BatchRunner
from core.compression import ConflictPolicy, ConversionSettings, compute_target_size
from core.converter import Status, convert_item, encode_webp
from core.folder_scanner import scan_sources
from core.image_validator import InvalidImageError
from core.output_planner import (PlanAction, default_output_dir, plan_outputs,
                                 prepare_output_dir, validate_job)
from core.report_generator import build_text, write_csv
from utils.file_utils import sanitize_stem
from utils.size_formatter import format_size


def noisy(size=(120, 90), mode="RGB", seed=1):
    rng = random.Random(seed)
    img = Image.new("RGB", size)
    img.putdata([(rng.randrange(256), rng.randrange(256), rng.randrange(256)) for _ in range(size[0] * size[1])])
    return img.convert(mode) if mode != "RGB" else img


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="webptest_"))
        self.src = self.tmp / "Gallery"
        self.src.mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def decode(self, data: bytes) -> Image.Image:
        img = Image.open(io.BytesIO(data))
        img.load()
        return img


class TestSettings(unittest.TestCase):
    def test_validation(self):
        ConversionSettings().validate()
        for bad in (dict(quality=0), dict(quality=101), dict(method=7), dict(method=-1),
                    dict(resize_enabled=True, max_width=0, max_height=0)):
            with self.assertRaises(ValueError):
                ConversionSettings(**bad).validate()

    def test_target_size(self):
        self.assertEqual(compute_target_size(4000, 3000, 1000, 1000), (1000, 750))
        self.assertEqual(compute_target_size(800, 600, 1920, 1080), (800, 600))       # no upscale
        self.assertEqual(compute_target_size(4000, 2000, 0, 500), (1000, 500))        # one axis only
        self.assertEqual(compute_target_size(10, 10000, 5, 0), (5, 5000))

    def test_format_size(self):
        self.assertEqual(format_size(0), "0 B")
        self.assertEqual(format_size(1536), "1.50 KB")
        self.assertEqual(format_size(5 * 1024 ** 2), "5.00 MB")


class TestEncoding(Base):
    def test_jpg_dimensions_preserved(self):
        p = self.src / "a.jpg"
        noisy((321, 123)).save(p, quality=92)
        enc = encode_webp(p, ConversionSettings())
        out = self.decode(enc.data)
        self.assertEqual(out.format, "WEBP")
        self.assertEqual(out.size, (321, 123))

    def test_png_transparency_preserved(self):
        p = self.src / "t.png"
        img = Image.new("RGBA", (64, 64), (255, 0, 0, 0))
        for x in range(32):
            for y in range(64):
                img.putpixel((x, y), (0, 255, 0, 255))
        img.save(p)
        out = self.decode(encode_webp(p, ConversionSettings(lossless=True)).data)
        self.assertIn("A", out.getbands())
        self.assertEqual(out.getpixel((5, 5))[3], 255)
        self.assertEqual(out.getpixel((60, 5))[3], 0)

    def test_palette_png_with_transparency_and_colour_key(self):
        pal = self.src / "pal.png"
        im = Image.new("P", (20, 20), 0)
        im.putpalette([255, 0, 0, 0, 255, 0] + [0] * 762)
        im.save(pal, transparency=0)
        out = self.decode(encode_webp(pal, ConversionSettings(lossless=True)).data)
        self.assertEqual(out.getpixel((1, 1))[3], 0)

        key = self.src / "key.png"
        Image.new("RGB", (10, 10), (1, 2, 3)).save(key, transparency=(1, 2, 3))
        out = self.decode(encode_webp(key, ConversionSettings(lossless=True)).data)
        self.assertEqual(out.getpixel((1, 1))[3], 0)

    def test_lossless_is_pixel_exact(self):
        p = self.src / "x.png"
        src = noisy((50, 40))
        src.save(p)
        out = self.decode(encode_webp(p, ConversionSettings(lossless=True)).data).convert("RGB")
        self.assertIsNone(ImageChops.difference(src, out).getbbox())

    def test_lossy_quality_changes_size(self):
        p = self.src / "n.jpg"
        noisy((200, 200)).save(p, quality=95)
        low = len(encode_webp(p, ConversionSettings(quality=20)).data)
        high = len(encode_webp(p, ConversionSettings(quality=95)).data)
        self.assertLess(low, high)

    def test_exif_orientation_applied(self):
        p = self.src / "rot.jpg"
        img = noisy((100, 40))
        exif = Image.Exif()
        exif[0x0112] = 6  # rotate 90 CW when displayed
        img.save(p, exif=exif.tobytes())
        enc = encode_webp(p, ConversionSettings())
        self.assertEqual(enc.source_size, (40, 100))
        self.assertEqual(self.decode(enc.data).size, (40, 100))

    def test_icc_profile_preserved(self):
        p = self.src / "icc.jpg"
        icc = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
        noisy().save(p, icc_profile=icc)
        enc = encode_webp(p, ConversionSettings())
        self.assertTrue(enc.icc_preserved)
        self.assertTrue(self.decode(enc.data).info.get("icc_profile"))

    def test_resize_keeps_aspect_and_never_upscales(self):
        big, small = self.src / "big.jpg", self.src / "small.jpg"
        noisy((400, 200)).save(big)
        noisy((50, 30)).save(small)
        s = ConversionSettings(resize_enabled=True, max_width=100, max_height=100)
        self.assertEqual(encode_webp(big, s).output_size, (100, 50))
        self.assertEqual(encode_webp(small, s).output_size, (50, 30))

    def test_color_modes(self):
        cases = {
            "gray.png": noisy((30, 30)).convert("L"),
            "la.png": noisy((30, 30)).convert("LA"),
            "bw.png": noisy((30, 30)).convert("1"),
            "rgba.png": noisy((30, 30)).convert("RGBA"),
            "cmyk.jpg": noisy((30, 30)).convert("CMYK"),
            "gray.jpg": noisy((30, 30)).convert("L"),
            "p.png": noisy((30, 30)).convert("P"),
        }
        for name, img in cases.items():
            p = self.src / name
            img.save(p)
            with self.subTest(name):
                out = self.decode(encode_webp(p, ConversionSettings()).data)
                self.assertEqual(out.size, (30, 30))

    def test_16bit_grayscale_png(self):
        p = self.src / "g16.png"
        img = Image.new("I;16", (16, 16), 40000)
        img.save(p)
        out = self.decode(encode_webp(p, ConversionSettings(lossless=True)).data).convert("L")
        self.assertTrue(120 <= out.getpixel((3, 3)) <= 190)   # 40000/256 ~ 156

    def test_wrong_content_and_corrupt_rejected(self):
        gif = self.src / "fake.jpg"
        Image.new("P", (5, 5)).save(gif, format="GIF")
        with self.assertRaises(InvalidImageError):
            encode_webp(gif, ConversionSettings())
        bad = self.src / "bad.png"
        bad.write_bytes(b"this is not an image")
        with self.assertRaises(Exception):
            encode_webp(bad, ConversionSettings())

    def test_truncated_jpeg_fails_cleanly(self):
        p = self.src / "trunc.jpg"
        buf = io.BytesIO()
        noisy((300, 300)).save(buf, "JPEG", quality=90)
        p.write_bytes(buf.getvalue()[: len(buf.getvalue()) // 2])
        plan = plan_outputs(scan_sources([p]).items, self.tmp / "out")
        res = convert_item(plan[0], ConversionSettings())
        self.assertEqual(res.status, Status.FAILED)
        self.assertFalse((self.tmp / "out").exists() and any((self.tmp / "out").iterdir()))


class TestPlanning(Base):
    def test_default_output_dir(self):
        self.assertEqual(default_output_dir([self.src]), self.tmp / "Gallery_Converted_WebP")
        f = self.src / "a.jpg"; noisy().save(f)
        self.assertEqual(default_output_dir([f]), self.src / "Converted_WebP")

    def test_validate_rejects_same_folder(self):
        self.assertTrue(validate_job([self.src], self.src))
        self.assertTrue(validate_job([], self.tmp / "o"))
        self.assertEqual(validate_job([self.src], self.tmp / "Gallery_Converted_WebP"), [])

    def test_sanitize(self):
        self.assertEqual(sanitize_stem('a<b>:c?'), "a_b__c_")
        self.assertEqual(sanitize_stem("CON"), "_CON")
        self.assertEqual(sanitize_stem("  ..  "), "image")
        self.assertEqual(sanitize_stem("日本語 photo"), "日本語 photo")

    def test_batch_duplicates_never_overwrite_each_other(self):
        for n in ("photo.jpg", "photo.png", "Photo.JPEG"):
            noisy().save(self.src / n)
        items = scan_sources([self.src]).items
        for policy in ConflictPolicy:
            with self.subTest(policy=policy):
                plan = plan_outputs(items, self.tmp / "out", policy)
                dests = [str(p.dest).casefold() for p in plan]
                self.assertEqual(len(set(dests)), 3, dests)

    def test_existing_file_policies(self):
        noisy().save(self.src / "a.jpg")
        out = self.tmp / "out"; out.mkdir()
        existing = out / "a.webp"; existing.write_bytes(b"old")
        items = scan_sources([self.src]).items

        plan = plan_outputs(items, out, ConflictPolicy.RENAME)
        self.assertEqual(plan[0].dest.name, "a (1).webp")
        self.assertEqual(plan[0].action, PlanAction.CONVERT)

        plan = plan_outputs(items, out, ConflictPolicy.SKIP)
        self.assertEqual(plan[0].action, PlanAction.SKIP)
        res = convert_item(plan[0], ConversionSettings())
        self.assertEqual(res.status, Status.SKIPPED)
        self.assertEqual(existing.read_bytes(), b"old")

        plan = plan_outputs(items, out, ConflictPolicy.OVERWRITE)
        self.assertEqual(plan[0].action, PlanAction.OVERWRITE)
        self.assertEqual(convert_item(plan[0], ConversionSettings()).status, Status.CONVERTED)
        self.assertNotEqual(existing.read_bytes(), b"old")

    def test_recursive_structure_and_exclusion(self):
        (self.src / "sub" / "deep").mkdir(parents=True)
        noisy().save(self.src / "a.jpg")
        noisy().save(self.src / "sub" / "b.png")
        noisy().save(self.src / "sub" / "deep" / "c.jpeg")
        (self.src / "notes.txt").write_text("x")
        flat = scan_sources([self.src], recursive=False)
        self.assertEqual([i.path.name for i in flat.items], ["a.jpg"])

        out = self.src / "Gallery_Converted_WebP"          # output INSIDE the source tree
        out.mkdir()
        noisy().save(out / "ignored.png")
        rec = scan_sources([self.src], recursive=True, exclude_dirs=[out])
        self.assertEqual(sorted(i.path.name for i in rec.items), ["a.jpg", "b.png", "c.jpeg"])
        plan = plan_outputs(rec.items, out)
        rel = sorted(str(p.dest.relative_to(out)).replace(os.sep, "/") for p in plan)
        self.assertEqual(rel, ["a.webp", "sub/b.webp", "sub/deep/c.webp"])

    def test_empty_folder(self):
        self.assertEqual(scan_sources([self.src]).items, [])
        self.assertEqual(BatchRunner([], ConversionSettings(), self.tmp / "o").run().stats.total, 0)

    def test_unwritable_output(self):
        blocker = self.tmp / "file.txt"; blocker.write_text("x")
        self.assertTrue(validate_job([self.src], blocker))
        self.assertIsNotNone(prepare_output_dir(blocker / "sub"))


class TestSkipLarger(Base):
    def test_skip_if_larger_keeps_output_clean(self):
        p = self.src / "lowq.jpg"
        noisy((200, 200)).save(p, quality=5)          # tiny, heavily compressed JPEG
        out = self.tmp / "out"
        for flag in (False, True):
            plan = plan_outputs(scan_sources([p]).items, out / str(flag))
            s = ConversionSettings(quality=100, skip_if_larger=flag)
            grew = len(encode_webp(p, s).data) > p.stat().st_size
            self.assertTrue(grew, "test image should grow as WebP at quality 100")
            res = convert_item(plan[0], s)
            if flag:
                self.assertEqual(res.status, Status.SKIPPED)
                self.assertIn("larger", res.message)
                self.assertFalse(plan[0].dest.exists())
            else:
                self.assertEqual(res.status, Status.CONVERTED)
                self.assertTrue(res.larger)


class TestBatch(Base):
    def make_mixed(self, n=60):
        (self.src / "sub").mkdir()
        for i in range(n):
            folder = self.src if i % 3 else self.src / "sub"
            ext = ("jpg", "jpeg", "png")[i % 3]
            noisy((64 + i % 5, 48), seed=i).save(folder / f"img{i:03d}.{ext}")
        (self.src / "corrupt.jpg").write_bytes(b"garbage")
        (self.src / "empty.png").write_bytes(b"")

    def test_full_folder_conversion_leaves_originals_untouched(self):
        self.make_mixed()
        before = {p: sha(p) for p in self.src.rglob("*") if p.is_file()}
        out = self.tmp / "Gallery_Converted_WebP"
        scan = scan_sources([self.src], recursive=True, exclude_dirs=[out])
        self.assertIsNone(prepare_output_dir(out))
        plan = plan_outputs(scan.items, out)
        report = BatchRunner(plan, ConversionSettings(workers=3, method=2, recursive=True), out).run()

        s = report.stats
        self.assertEqual((s.total, s.converted, s.failed), (62, 60, 2))
        self.assertEqual(s.processed, 62)
        self.assertFalse(report.cancelled)
        self.assertEqual(len(list(out.rglob("*.webp"))), 60)
        self.assertEqual(list(out.rglob("*.tmp")), [])                    # no temp leftovers
        self.assertEqual(before, {p: sha(p) for p in self.src.rglob("*") if p.is_file()})
        for w in out.rglob("*.webp"):                                      # each output opens
            with Image.open(w) as im:
                im.load()
        self.assertTrue(all(r.message for r in report.results if r.status is Status.FAILED))

    def test_cancel_stops_early_and_leaves_no_temp_files(self):
        for i in range(80):
            noisy((200, 200), seed=i).save(self.src / f"i{i}.jpg")
        out = self.tmp / "out"
        plan = plan_outputs(scan_sources([self.src]).items, out)
        runner = BatchRunner(plan, ConversionSettings(workers=2, method=6), out)

        def stop_after_5(stats, result, name):
            if stats.processed >= 5:
                runner.cancel()
        report = runner.run(stop_after_5)
        self.assertTrue(report.cancelled)
        self.assertLess(report.stats.processed, 80)
        self.assertEqual(list(out.rglob("*.tmp")), [])
        self.assertEqual(len(list(out.glob("*.webp"))), report.stats.converted)

    def test_pause_and_resume(self):
        import threading, time
        for i in range(12):
            noisy((80, 80), seed=i).save(self.src / f"p{i}.jpg")
        out = self.tmp / "out"
        runner = BatchRunner(plan_outputs(scan_sources([self.src]).items, out), ConversionSettings(workers=1), out)
        runner.pause()
        box = {}
        t = threading.Thread(target=lambda: box.update(r=runner.run()))
        t.start()
        time.sleep(0.5)
        self.assertEqual(len(list(out.glob("*.webp"))) if out.exists() else 0, 0)   # nothing while paused
        runner.resume()
        t.join(timeout=30)
        self.assertEqual(box["r"].stats.converted, 12)

    def test_reports_and_larger_flag(self):
        # tiny flat PNG: lossless WebP of a tiny flat image can be larger or smaller; just check reporting works
        Image.new("RGB", (4, 4), (1, 2, 3)).save(self.src / "tiny.png", optimize=True)
        noisy((100, 100)).save(self.src / "=evil.jpg")
        (self.src / "bad.jpg").write_bytes(b"nope")
        out = self.tmp / "out"
        report = BatchRunner(plan_outputs(scan_sources([self.src]).items, out), ConversionSettings(), out).run()
        text = build_text(report)
        self.assertIn("Failed images", text)
        self.assertIn("bad.jpg", text)
        csv_path = self.tmp / "r.csv"
        write_csv(report, csv_path)
        with open(csv_path, newline="", encoding="utf-8-sig") as fh:
            rows = list(csv.DictReader(fh))
        self.assertEqual(len(rows), 3)
        self.assertTrue(any(r["source"].startswith("'") is False for r in rows))
        self.assertFalse(any(r["source"].startswith("=") for r in rows))
        self.assertEqual(sorted(r["status"] for r in rows), ["converted", "converted", "failed"])


if __name__ == "__main__":
    unittest.main()
