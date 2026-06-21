import io
from pathlib import Path
from PIL import Image
from scraper import crawl

class FakeResp:
    def __init__(self, ok, body): self._ok = ok; self._body = body
    @property
    def ok(self): return self._ok
    def body(self): return self._body

class FakeContext:
    def __init__(self, body): self.request = self; self._body = body
    def get(self, url, timeout=20000): return FakeResp(True, self._body)

def _png_bytes():
    buf = io.BytesIO()
    Image.new("RGB", (4, 4), (255, 0, 0)).save(buf, "PNG")
    return buf.getvalue()

def test_category_page_url():
    assert crawl.category_page_url(1) == crawl.CATEGORY_URL
    assert crawl.category_page_url(3) == crawl.CATEGORY_URL + "/3"

def test_already_scraped(tmp_path):
    (tmp_path / "1.json").write_text("{}")
    assert crawl.already_scraped(str(tmp_path), "1") is True
    assert crawl.already_scraped(str(tmp_path), "2") is False

def test_download_thumbnail_converts_to_jpeg(tmp_path):
    ctx = FakeContext(_png_bytes())
    p = crawl.download_thumbnail(ctx, "http://x/0.webp", str(tmp_path))
    assert p is not None and Path(p).exists()
    with Image.open(p) as im:
        assert im.format == "JPEG"
