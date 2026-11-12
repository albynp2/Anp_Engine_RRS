"""Tes offline (tanpa internet). Jalankan: python -m tests.test_research"""
import base64
import os
import tempfile
from datetime import date

os.environ.setdefault("DATA_DIR", tempfile.mkdtemp())

from app import article_fetch, popularity, research, scorer  # noqa: E402

SAMPLE_RSS = b"""<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>
<item><title>Penampakan misterius di jembatan Cipularang bikin geger - Kompas.com</title>
<link>https://news.google.com/rss/articles/AAA1</link><pubDate>Wed, 11 Nov 2026 18:30:00 GMT</pubDate>
<source url="https://kompas.com">Kompas.com</source></item>
<item><title>Geger penampakan misterius jembatan Cipularang - Detik</title>
<link>https://news.google.com/rss/articles/AAA2</link><pubDate>Thu, 12 Nov 2026 01:00:00 GMT</pubDate>
<source url="https://detik.com">Detik</source></item>
<item><title>Warga heboh penampakan misterius di Jembatan Cipularang - Tribun</title>
<link>https://news.google.com/rss/articles/AAA3</link><pubDate>Thu, 12 Nov 2026 02:00:00 GMT</pubDate>
<source url="https://tribun.com">Tribun</source></item>
<item><title>Sinopsis film horor terbaru Netflix - CNN</title>
<link>https://news.google.com/rss/articles/AAA4</link><pubDate>Thu, 12 Nov 2026 03:00:00 GMT</pubDate>
<source url="https://cnn.com">CNN</source></item>
<item><title>Pembunuhan sadis di Bekasi terungkap - Liputan6</title>
<link>https://news.google.com/rss/articles/AAA5</link><pubDate>Mon, 02 Nov 2026 03:00:00 GMT</pubDate>
<source url="https://liputan6.com">Liputan6</source></item>
</channel></rss>"""


def test_dates():
    t = date(2026, 11, 12)
    assert research.resolve_dates(True, "2026-11-01", "2026-11-05", t) == (t, t)
    assert research.resolve_dates(False, "", "", t) == (t, t)
    assert research.resolve_dates(False, "2026-11-01", "2026-11-05", t) == (date(2026, 11, 1), date(2026, 11, 5))
    assert research.resolve_dates(False, "2026-11-01", "", t) == (date(2026, 11, 1), t)
    assert research.resolve_dates(False, "", "2026-11-05", t) == (date(2026, 11, 5), date(2026, 11, 5))
    assert research.resolve_dates(False, "2026-11-05", "2026-11-01", t) == (date(2026, 11, 1), date(2026, 11, 5))


def test_rss_and_filter():
    items = research.parse_rss(SAMPLE_RSS, "q")
    assert len(items) == 5
    assert items[0]["title"].endswith("bikin geger")  # suffix media dibuang
    # 11 Nov 18:30 GMT = 12 Nov 01:30 WIB -> harus masuk "hari ini" (12 Nov) di WIB
    assert items[0]["published_date"] == "2026-11-12"
    d = date(2026, 11, 12)
    out = research.filter_items(items, d, d, [])
    assert len(out) == 4  # yang 2 Nov terbuang
    out = research.filter_items(items, d, d, ["film", "netflix"])
    assert len(out) == 3
    out = research.filter_items(items, date(2026, 11, 1), date(2026, 11, 12), [])
    assert len(out) == 5


def test_popularity():
    items = research.parse_rss(SAMPLE_RSS, "q")
    res = popularity.analyze(items)
    top = res[0]
    assert top["coverage_count"] == 3 and top["unique_source_count"] == 3, top
    assert top["popularity_score"] > res[-1]["popularity_score"]
    assert popularity.score(1, 1, 1) < popularity.score(6, 4, 1) < popularity.score(12, 8, 3)
    assert popularity.analyze([]) == []
    assert len(popularity.analyze(items[:1])) == 1


def test_scorer_prompt_and_combine():
    sys_, usr = scorer.build_prompt([{"idx": 0, "title": "A", "source": "B", "coverage": 3, "sources": 2}],
                                    "horror", "")
    assert "0|A|B|3x2" == usr and "horor" in sys_
    assert scorer.combine(80, None) == 80.0
    assert scorer.combine(80, 60) == round(0.55 * 80 + 0.45 * 60, 1)


def test_old_style_decode():
    url = "https://www.contoh.com/berita/123"
    raw = b"\x08\x13\x22" + bytes([len(url)]) + url.encode() + b"\xd2\x01\x00"
    gid = base64.urlsafe_b64encode(raw).decode().rstrip("=")
    assert article_fetch._gid(f"https://news.google.com/rss/articles/{gid}") == gid
    assert article_fetch._decode_old_style(gid) == url


HTML = """<html><head><meta property="og:description" content="ringkasan"></head><body>
<nav><p>Menu navigasi panjang sekali yang seharusnya tidak ikut terambil oleh ekstraktor ya.</p></nav>
<div class="sidebar"><p>Baca juga: berita lain yang tidak relevan dan harus dibuang karena boilerplate</p></div>
<div class="detail-text">
<p>Warga Desa Sukamaju, Kabupaten Bogor, melaporkan adanya penampakan sosok putih di dekat jembatan pada Selasa malam.</p>
<p>Menurut keterangan saksi bernama Rudi, kejadian berlangsung sekitar pukul 22.00 WIB dan sempat direkam warga lain.</p>
<p>Baca juga: kasus lain yang tidak berhubungan sama sekali dengan berita ini ya</p>
<p>Kepala desa mengatakan pihaknya belum menemukan bukti pasti dan meminta warga tidak menyebarkan kabar yang belum jelas.</p>
<p>Polisi setempat mengaku telah menerima laporan dan akan melakukan pengecekan lokasi pada hari berikutnya.</p>
<p>Hingga berita ini diturunkan, belum ada keterangan resmi lain terkait video yang beredar di media sosial tersebut.</p>
</div></body></html>"""


def test_extract_text():
    t = article_fetch.extract_text(HTML)
    assert "Sukamaju" in t and "Kepala desa" in t
    assert "Menu navigasi" not in t and "Baca juga" not in t
    assert len(t.split("\n")) == 5, t


def test_cut():
    long = ("Kalimat panjang nomor satu. " * 400)
    c = article_fetch.cut(long)
    assert len(c) <= article_fetch.MAX_CHARS and c.endswith(".")


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("OK ", name)
