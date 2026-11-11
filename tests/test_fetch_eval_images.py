"""抓取脚本的纯函数测试：解析、去重、落盘与核对页，全部不联网。"""
from __future__ import annotations

import io
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageOps

TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
sys.path.insert(0, str(TOOLS_DIR))

import fetch_eval_images as fei  # noqa: E402


def gradient_image(size=(800, 600), mode="RGB"):
    """快速生成二维渐变图：同图缩放后哈希接近，左右翻转后哈希明显不同。"""
    vertical = Image.linear_gradient("L").resize(size)
    horizontal = vertical.transpose(Image.Transpose.ROTATE_90).resize(size)
    base = Image.blend(vertical, horizontal, 0.5)
    if mode == "RGBA":
        alpha = Image.new("L", size, 255)
        return Image.merge("RGBA", (base, ImageOps.invert(base),
                                    base.point(lambda value: value // 2), alpha))
    return Image.merge("RGB", (base, ImageOps.invert(base),
                               base.point(lambda value: value // 2)))


def image_bytes(image, fmt="PNG", **kwargs):
    buffer = io.BytesIO()
    image.save(buffer, fmt, **kwargs)
    return buffer.getvalue()


class QueryPlanTest(unittest.TestCase):
    def test_plan_covers_knowledge_base(self):
        labels = {plan.label for plan in fei.CLASS_PLANS}
        self.assertEqual(labels, set(fei.PEST_CLASSES) | {"健康叶片", "健康果实", "非目标"})
        slugs = [plan.slug for plan in fei.CLASS_PLANS]
        self.assertEqual(len(slugs), len(set(slugs)))
        for plan in fei.CLASS_PLANS:
            self.assertRegex(plan.slug, r"^[a-z0-9_]+$")
            self.assertGreaterEqual(len(plan.queries), 5)

    def test_looper_uses_larva_stage(self):
        plan = fei.PLAN_BY_LABEL["荔枝尺蠖"]
        self.assertEqual(plan.inat_taxon, "Geometridae")
        self.assertIn(("term_value_id", "4"), plan.inat_params)

    def test_non_target_queries(self):
        plan = fei.PLAN_BY_LABEL["非目标"]
        self.assertGreaterEqual(len(plan.queries), 15)

    def test_resolve_aliases(self):
        self.assertEqual(fei.resolve_label("蒂蛀虫"), "荔枝蒂蛀虫")
        self.assertEqual(fei.resolve_label("healthy fruit"), "健康果实")
        self.assertEqual(fei.resolve_label("非目标"), "非目标")
        with self.assertRaises(KeyError):
            fei.resolve_label("无法判断")
        with self.assertRaises(KeyError):
            fei.resolve_label("不存在的类别")

    def test_source_tiers(self):
        lichun = fei.PLAN_BY_LABEL["荔枝蝽"]
        downy = fei.PLAN_BY_LABEL["荔枝霜疫霉病"]
        healthy = fei.PLAN_BY_LABEL["健康果实"]
        self.assertEqual(fei.tiers_for(lichun, "auto"), ("inat", "bing", "so_web", "so"))
        self.assertEqual(fei.tiers_for(downy, "auto"), ("bing", "so_web", "so"))
        self.assertEqual(fei.tiers_for(healthy, "auto"), ("bing", "so_web", "so", "inat"))
        self.assertEqual(fei.tiers_for(lichun, "bing"), ("bing",))
        self.assertEqual(fei.tiers_for(downy, "so_web"), ("so_web",))


class BingParserTest(unittest.TestCase):
    def test_murl_title_dedupe_and_thumbnail(self):
        text = r'''
        <div m="{&quot;murl&quot;:&quot;https:\/\/example.com\/a.jpg&quot;,&quot;t&quot;:&quot;荔枝蒂蛀虫防治&quot;,&quot;purl&quot;:&quot;https:\/\/site.example.com\/a&quot;,&quot;turl&quot;:&quot;https:\/\/ts.example.com\/a.jpg&quot;}"></div>
        <div m="{&quot;murl&quot;:&quot;https:\/\/example.com\/a.jpg&quot;,&quot;t&quot;:&quot;重复图&quot;}"></div>
        <div m="{&quot;murl&quot;:&quot;https:\/\/example.com\/b.jpg&quot;,&quot;t&quot;:&quot;荔枝蛀蒂虫&quot;}"></div>
        '''
        candidates = fei.parse_bing_html(text, "荔枝蒂蛀虫", "https://cn.bing.com/images/search?q=x")
        self.assertEqual([c.url for c in candidates],
                         ["https://example.com/a.jpg", "https://example.com/b.jpg"])
        self.assertEqual(candidates[0].title, "荔枝蒂蛀虫防治")
        self.assertEqual(candidates[0].fallbacks, ("https://ts.example.com/a.jpg",))
        self.assertEqual(candidates[0].page_url, "https://site.example.com/a")
        self.assertTrue(all(c.source == "bing" for c in candidates))

    def test_plan_keywords_require_specific_term(self):
        keywords = fei.plan_keywords(fei.PLAN_BY_LABEL["荔枝蒂蛀虫"])
        self.assertIn("蒂蛀虫", keywords)
        self.assertNotIn("荔枝", keywords)
        self.assertNotIn("litchi", keywords)
        # 健康类别没有病虫害词，允许用果实/叶片词
        self.assertIn("叶片", fei.plan_keywords(fei.PLAN_BY_LABEL["健康叶片"]))

    def test_keyword_filter_drops_unrelated_default_images(self):
        text = r'''
        <div m="{&quot;murl&quot;:&quot;https:\/\/example.com\/travel.jpg&quot;,&quot;t&quot;:&quot;全球十大旅游胜地&quot;}"></div>
        <div m="{&quot;murl&quot;:&quot;https:\/\/example.com\/news.jpg&quot;,&quot;t&quot;:&quot;杜特尔特就香港形势表态-荔枝网新闻&quot;}"></div>
        <div m="{&quot;murl&quot;:&quot;https:\/\/example.com\/pest.jpg&quot;,&quot;t&quot;:&quot;荔枝蒂蛀虫发生规律&quot;}"></div>
        '''
        keywords = fei.plan_keywords(fei.PLAN_BY_LABEL["荔枝蒂蛀虫"])
        candidates = fei.parse_bing_html(text, "荔枝蒂蛀虫", "page", keywords=keywords)
        self.assertEqual([c.url for c in candidates], ["https://example.com/pest.jpg"])

    def test_raw_single_quote_fallback(self):
        text = """<div m='{"murl":"https://example.com/b.jpg"}'></div>"""
        candidates = fei.parse_bing_html(text, "荔枝蝽", "page")
        self.assertEqual([c.url for c in candidates], ["https://example.com/b.jpg"])

    def test_empty_text(self):
        self.assertEqual(fei.parse_bing_html("", "x", ""), [])


class SoParserTest(unittest.TestCase):
    def test_url_priority_and_metadata(self):
        payload = {"list": [
            {
                "downurl_true": "https://cdn.example.com/a.jpg",
                "downurl": "https://cdn.example.com/b.jpg",
                "img": "https://cdn.example.com/c.jpg",
                "thumb": "https://cdn.example.com/t.jpg",
                "width": "800", "height": "600",
                "copyright_owner": "某农业站",
                "link": "https://site.example.com/page",
            },
            {"img": "https://other.example.com/d.jpg", "src": "other.example.com"},
            {"title": "没有图片"},
        ]}
        candidates = fei.parse_so_payload(payload, "荔枝霜疫霉病")
        self.assertEqual(len(candidates), 2)
        first = candidates[0]
        self.assertEqual(first.url, "https://cdn.example.com/a.jpg")
        self.assertEqual(first.fallbacks,
                         ("https://cdn.example.com/b.jpg",
                          "https://cdn.example.com/c.jpg",
                          "https://cdn.example.com/t.jpg"))
        self.assertEqual((first.width, first.height), (800, 600))
        self.assertEqual(first.attribution, "某农业站")
        self.assertEqual(first.page_url, "https://site.example.com/page")
        self.assertEqual(candidates[1].attribution, "other.example.com")

    def test_forbidden_payload(self):
        self.assertEqual(fei.parse_so_payload({"status": 1, "data": None}, "x"), [])


class SoWebParserTest(unittest.TestCase):
    def test_image_pack_and_dedupe(self):
        text = '''
        <a href="https://image.so.com/i?q=x" data-original="http://cdn.example.com/a.jpg"
           data-url="https://thumb.example.com/a.jpg" class="mh-img-link">
        <a href="https://image.so.com/i?q=x" data-original="http://cdn.example.com/a.jpg">
        <a data-original="javascript:void(0)">
        <a data-original="https://cdn.example.com/b.jpg?x=1&amp;y=2">
        '''
        candidates = fei.parse_so_web_html(text, "荔枝炭疽病")
        self.assertEqual([c.url for c in candidates],
                         ["http://cdn.example.com/a.jpg",
                          "https://cdn.example.com/b.jpg?x=1&y=2"])
        first = candidates[0]
        self.assertEqual(first.source, "360-web")
        self.assertEqual(first.title, "荔枝炭疽病")
        self.assertEqual(first.attribution, "cdn.example.com")
        self.assertEqual(first.fallbacks, ("https://thumb.example.com/a.jpg",))
        self.assertIn("image.so.com", first.page_url)

    def test_blocked_page_has_no_candidates(self):
        self.assertEqual(fei.parse_so_web_html("<title>360图片_访问异常出错</title>", "x"), [])


class InatParserTest(unittest.TestCase):
    def test_license_filter_and_sizes(self):
        payload = {"results": [
            {
                "id": 123,
                "user": {"login": "alice"},
                "photos": [
                    {
                        "license_code": "cc-by",
                        "url": "https://inaturalist-open-data.s3.amazonaws.com/photos/1/square.jpg",
                        "attribution": "(c) Alice, some rights reserved",
                        "original_dimensions": {"width": 2048, "height": 1536},
                    },
                    {
                        "license_code": "cc-by-nc",
                        "url": "https://inaturalist-open-data.s3.amazonaws.com/photos/2/square.jpg",
                    },
                ],
            },
            {
                "id": 456,
                "user": {"login": "bob"},
                "photos": [
                    {
                        "license_code": "cc0",
                        "url": "https://inaturalist-open-data.s3.amazonaws.com/photos/3/square.jpg",
                    },
                ],
            },
        ]}
        candidates = fei.parse_inat_payload(payload, "Tessaratoma papillosa")
        self.assertEqual(len(candidates), 2)
        first = candidates[0]
        self.assertEqual(first.license, "cc-by")
        self.assertTrue(first.url.endswith("/large.jpg"))
        self.assertEqual(first.fallbacks,
                         ("https://inaturalist-open-data.s3.amazonaws.com/photos/1/original.jpg",))
        self.assertEqual((first.width, first.height), (2048, 1536))
        self.assertIn("/observations/123", first.page_url)
        self.assertIn("Alice", first.attribution)
        self.assertEqual(candidates[1].license, "cc0")
        self.assertIn("@bob", candidates[1].attribution)

    def test_missing_observation_id_skipped(self):
        payload = {"results": [{"user": {"login": "x"}, "photos": [
            {"license_code": "cc0", "url": "https://x/1/square.jpg"}]}]}
        self.assertEqual(fei.parse_inat_payload(payload, "x"), [])


class ImagePipelineTest(unittest.TestCase):
    def test_average_hash_similar_and_different(self):
        base = gradient_image((320, 240))
        resized = base.resize((640, 480))
        hash_base = fei.average_hash(base)
        hash_resized = fei.average_hash(resized)
        self.assertLessEqual(fei.hamming(hash_base, hash_resized), fei.AHASH_DISTANCE)

        flipped = base.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
        self.assertGreater(fei.hamming(hash_base, fei.average_hash(flipped)),
                           fei.AHASH_DISTANCE)

    def test_prepare_rgb_png(self):
        prepared = fei.prepare_image(image_bytes(gradient_image((800, 600))))
        self.assertIsNotNone(prepared)
        self.assertEqual((prepared.width, prepared.height), (800, 600))
        with Image.open(io.BytesIO(prepared.jpeg)) as image:
            self.assertEqual(image.format, "JPEG")

    def test_prepare_downscales_large(self):
        prepared = fei.prepare_image(image_bytes(gradient_image((2400, 1800))))
        self.assertIsNotNone(prepared)
        self.assertLessEqual(max(prepared.width, prepared.height), fei.MAX_SIDE)

    def test_prepare_rejects_small_and_garbage(self):
        self.assertIsNone(fei.prepare_image(image_bytes(gradient_image((120, 120)))))
        self.assertIsNone(fei.prepare_image(b"<html>not an image</html>"))

    def test_prepare_alpha_bmp_gif(self):
        rgba = gradient_image((800, 600), "RGBA")
        self.assertIsNotNone(fei.prepare_image(image_bytes(rgba, "PNG")))
        self.assertIsNotNone(fei.prepare_image(image_bytes(gradient_image((800, 600)), "BMP")))
        self.assertIsNotNone(fei.prepare_image(image_bytes(gradient_image((800, 600)), "GIF")))

    def test_safe_referer_encodes_non_latin1(self):
        self.assertEqual(fei._safe_referer(""), "")
        self.assertEqual(fei._safe_referer("https://a.example.com/x"), "https://a.example.com/x")
        encoded = fei._safe_referer("https://cn.bing.com/images/search?q=荔枝")
        encoded.encode("latin-1")  # 不抛异常即可放进 HTTP 头
        self.assertNotIn("荔枝", encoded)

    def test_next_filename_resume(self):
        with tempfile.TemporaryDirectory() as tmp:
            image_dir = Path(tmp)
            (image_dir / "tichengchong_01.jpg").write_bytes(b"x")
            self.assertEqual(fei.next_filename(image_dir, "tichengchong", set()),
                             "tichengchong_02.jpg")
            self.assertEqual(fei.next_filename(image_dir, "tichengchong",
                                               {"tichengchong_02.jpg"}),
                             "tichengchong_03.jpg")


class ManifestAndSheetTest(unittest.TestCase):
    def test_manifest_roundtrip_and_prune(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            image_dir = root / "images"
            image_dir.mkdir()
            (image_dir / "a.jpg").write_bytes(b"x")
            path = root / "manifest.csv"
            rows = {
                "a.jpg": {"file": "a.jpg", "label": "荔枝蝽", "source": "inat"},
                "b.jpg": {"file": "b.jpg", "label": "荔枝蝽", "source": "bing"},
            }
            fei.save_manifest(path, rows)
            loaded = fei.load_manifest(path)
            self.assertEqual(set(loaded), {"a.jpg", "b.jpg"})
            kept, removed = fei.prune_manifest(loaded, image_dir)
            self.assertEqual(set(kept), {"a.jpg"})
            self.assertEqual(removed, ["b.jpg"])

    def test_contact_sheet_escapes_and_relative_src(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            image_dir = root / "images"
            image_dir.mkdir()
            (image_dir / "a.jpg").write_bytes(b"x")
            rows = {"a.jpg": {
                "file": "a.jpg", "label": "荔枝蝽",
                "query": "<script>alert(1)</script>",
                "source": "bing", "license": "search-only",
                "attribution": "<b>x</b>",
            }}
            out = root / "contact-sheet.html"
            fei.render_contact_sheet(rows, image_dir, out)
            text = out.read_text(encoding="utf-8")
            self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", text)
            self.assertNotIn("<script>alert(1)</script>", text)
            self.assertIn("src='images/a.jpg'", text)
            self.assertNotIn("http://", text)
            self.assertNotIn("https://", text)

    def test_labels_prune_and_prefill(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            image_dir = root / "images"
            image_dir.mkdir()
            (image_dir / "a.jpg").write_bytes(b"x")
            labels = root / "labels.csv"
            fei.save_label_rows(labels, [
                {"file": "a.jpg", "label": "", "model_guess": "", "model_confidence": "", "model_source": ""},
                {"file": "gone.jpg", "label": "荔枝蝽"},
            ])
            removed = fei.prune_labels_missing(labels, image_dir)
            self.assertEqual(removed, ["gone.jpg"])
            changed = fei.prefill_labels(labels, {
                "a.jpg": {"file": "a.jpg", "label": "荔枝蝽"},
            }, image_dir)
            self.assertEqual(changed, 1)
            rows = fei.load_label_rows(labels)
            self.assertEqual(rows[0]["label"], "荔枝蝽")

    def test_dry_run_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            image_dir = root / "images"
            manifest = root / "manifest.csv"
            labels = root / "labels.csv"
            code = fei.main([
                "--dry-run", "--class", "荔枝蝽", "--dir", str(image_dir),
                "--manifest", str(manifest), "--labels", str(labels),
            ])
            self.assertEqual(code, 0)
            self.assertFalse(image_dir.exists())
            self.assertFalse(manifest.exists())
            self.assertFalse(labels.exists())


if __name__ == "__main__":
    unittest.main()
