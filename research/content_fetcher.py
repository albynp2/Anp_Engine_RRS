from html.parser import HTMLParser
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
import re

class _ArticleParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts=[]
        self.skip=0
    def handle_starttag(self, tag, attrs):
        if tag.lower() in {"script","style","noscript","svg","nav","footer","header","aside","form"}:
            self.skip += 1
    def handle_endtag(self, tag):
        if tag.lower() in {"script","style","noscript","svg","nav","footer","header","aside","form"} and self.skip:
            self.skip -= 1
    def handle_data(self, data):
        if self.skip:
            return
        value=re.sub(r"\s+"," ",data).strip()
        if value:
            self.parts.append(value)
    def text(self):
        return "\n".join(self.parts)

def fetch_article_content(url):
    if not url:
        raise ValueError("URL sumber kosong.")
    request=Request(url,headers={
        "User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36",
        "Accept":"text/html,application/xhtml+xml"
    })
    try:
        with urlopen(request,timeout=20) as response:
            raw=response.read()
            charset=response.headers.get_content_charset() or "utf-8"
    except HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code} saat mengambil artikel.") from exc
    except URLError as exc:
        raise RuntimeError(f"Gagal mengambil artikel: {exc.reason}") from exc
    except TimeoutError as exc:
        raise RuntimeError("Timeout 20 detik saat mengambil artikel.") from exc
    html=raw.decode(charset,errors="replace")
    parser=_ArticleParser()
    parser.feed(html)
    text=re.sub(r"\n{3,}","\n\n",parser.text()).strip()
    if len(text)<300:
        raise ValueError("Konten utama artikel tidak terdeteksi atau terlalu pendek.")
    return text[:30000]
