from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit, parse_qs, unquote, urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
import re
import json


class _ArticleParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag.lower() in {"script", "style", "noscript", "svg", "nav", "footer", "header", "aside", "form"}:
            self.skip += 1

    def handle_endtag(self, tag):
        if tag.lower() in {"script", "style", "noscript", "svg", "nav", "footer", "header", "aside", "form"} and self.skip:
            self.skip -= 1

    def handle_data(self, data):
        if self.skip:
            return
        value = re.sub(r"\s+", " ", data).strip()
        if value:
            self.parts.append(value)

    def text(self):
        return "\n".join(self.parts)


class _MetadataParser(HTMLParser):
    """Extract canonical/og:url metadata from a page."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.candidates = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "meta":
            return
        data = {str(k).lower(): str(v).strip() for k, v in attrs if k and v}
        prop = data.get("property", "").lower()
        name = data.get("name", "").lower()
        content = data.get("content", "").strip()
        if content and (prop in {"og:url", "og:url:url"} or name in {"canonical", "og:url"}):
            self.candidates.append(content)


def _is_google_news_url(url):
    try:
        return "news.google.com" in (urlsplit(url).netloc or "").lower()
    except Exception:
        return False


def _extract_embedded_target(url):
    """Handle common wrapped URLs that contain the publisher URL in a query parameter."""
    try:
        query = parse_qs(urlsplit(url).query)
        for key in ("url", "u", "q", "target", "dest", "destination"):
            for value in query.get(key, []):
                candidate = unquote(value).strip()
                if candidate.startswith(("http://", "https://")) and not _is_google_news_url(candidate):
                    return candidate
    except Exception:
        pass
    return None


def _request(url, timeout=20):
    request = Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
    })
    with urlopen(request, timeout=timeout) as response:
        raw = response.read()
        charset = response.headers.get_content_charset() or "utf-8"
        return raw, charset, getattr(response, "status", 200), response.geturl()


def _google_article_id(url):
    try:
        path = urlsplit(url).path.rstrip("/")
        if "/articles/" in path or "/read/" in path:
            return path.split("/")[-1]
    except Exception:
        pass
    return None


def _resolve_google_news_rpc(url):
    """Resolve current Google News RSS article IDs using Google's Fbv4je RPC."""
    gid = _google_article_id(url)
    if not gid:
        return None

    cookie = "CONSENT=YES+cb; SOCS=CAI"
    article_url = f"https://news.google.com/rss/articles/{gid}"
    req = Request(article_url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36",
        "Cookie": cookie,
        "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
    })
    with urlopen(req, timeout=20) as response:
        html = response.read().decode(response.headers.get_content_charset() or "utf-8", errors="replace")
        final_url = response.geturl()

    if final_url and not _is_google_news_url(final_url):
        return final_url

    sg_match = re.search(r'data-n-a-sg="([^"]+)"', html)
    ts_match = re.search(r'data-n-a-ts="([^"]+)"', html)
    if not sg_match or not ts_match:
        raise RuntimeError("Google News tidak memberikan signature/timestamp untuk resolusi artikel.")

    sg = sg_match.group(1)
    ts = ts_match.group(1)
    inner = (
        '["garturlreq",[["X","X",["X","X"],null,null,1,1,"ID:id",null,1,'
        'null,null,null,null,null,0,1],"X","X",1,[1,1,1],1,1,null,0,0,null,0],'
        f'"{gid}",{ts},"{sg}"]'
    )
    payload = json.dumps([[["Fbv4je", inner, None, "generic"]]], separators=(",", ":"))
    body = urlencode({"f.req": payload}).encode()
    rpc_url = "https://news.google.com/_/DotsSplashUi/data/batchexecute"
    rpc_req = Request(rpc_url, data=body, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36",
        "Cookie": cookie,
        "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
        "Accept": "*/*",
    })
    with urlopen(rpc_req, timeout=20) as response:
        raw = response.read().decode(response.headers.get_content_charset() or "utf-8", errors="replace")

    try:
        row_text = raw.split("\n\n", 1)[1]
        row = json.loads(row_text)[0][2]
    except Exception as exc:
        raise RuntimeError(f"Google News RPC response tidak dikenali: {exc}") from exc
    if not row:
        raise RuntimeError("Google News RPC tidak mengembalikan URL publisher.")
    try:
        resolved = json.loads(row)[1]
    except Exception as exc:
        raise RuntimeError(f"Google News RPC URL tidak valid: {exc}") from exc
    if not resolved or _is_google_news_url(resolved):
        raise RuntimeError("Google News RPC gagal menghasilkan URL publisher.")
    return resolved


def _resolve_source_url(url):
    """Resolve a Google News wrapper to the publisher URL when possible."""
    if _is_google_news_url(url):
        try:
            resolved_rpc = _resolve_google_news_rpc(url)
            if resolved_rpc:
                return resolved_rpc, b"", "utf-8", 200, resolved_rpc
        except Exception as rpc_exc:
            rpc_error = rpc_exc
        else:
            rpc_error = None
    else:
        rpc_error = None

    raw, charset, status, final_url = _request(url)
    html = raw.decode(charset, errors="replace")
    candidates = []
    if final_url and not _is_google_news_url(final_url):
        candidates.append(final_url)
    if _is_google_news_url(final_url) or _is_google_news_url(url):
        parser = _MetadataParser()
        parser.feed(html)
        for candidate in parser.candidates:
            candidates.append(urljoin(final_url or url, candidate))
        embedded = _extract_embedded_target(url)
        if embedded:
            candidates.append(embedded)
        embedded = _extract_embedded_target(final_url)
        if embedded:
            candidates.append(embedded)

    seen = set()
    cleaned = []
    for candidate in candidates:
        candidate = (candidate or "").strip()
        if not candidate or _is_google_news_url(candidate) or candidate in seen:
            continue
        seen.add(candidate)
        cleaned.append(candidate)
    if cleaned:
        return cleaned[0], raw, charset, status, final_url
    if rpc_error:
        raise RuntimeError(f"Google News URL belum berhasil di-resolve: {rpc_error}")
    return final_url or url, raw, charset, status, final_url


def fetch_article_content(url):
    if not url:
        raise ValueError("URL sumber kosong.")

    last_error = None
    candidates = [url]

    # First resolve Google News redirect/wrapper.
    try:
        resolved_url, raw, charset, status, final_url = _resolve_source_url(url)
        if resolved_url and resolved_url not in candidates:
            candidates.insert(0, resolved_url)
    except Exception as exc:
        last_error = exc

    # Try resolved publisher URL first, then original URL as a fallback.
    for candidate in candidates:
        try:
            if candidate == url and last_error is not None:
                # The original request was already attempted by _resolve_source_url.
                # Avoid an unnecessary second request unless it is not a Google URL.
                if _is_google_news_url(url):
                    continue

            raw, charset, status, actual_url = _request(candidate)
            html = raw.decode(charset, errors="replace")

            parser = _ArticleParser()
            parser.feed(html)
            text = re.sub(r"\n{3,}", "\n\n", parser.text()).strip()

            if len(text) < 300:
                last_error = ValueError(
                    f"Konten utama artikel tidak terdeteksi atau terlalu pendek "
                    f"(URL akhir: {actual_url})."
                )
                continue

            return {
                "content": text[:30000],
                "resolved_url": actual_url,
                "http_status": status,
            }
        except HTTPError as exc:
            last_error = RuntimeError(f"HTTP {exc.code} saat mengambil artikel ({candidate}).")
        except URLError as exc:
            last_error = RuntimeError(f"Gagal mengambil artikel: {exc.reason} ({candidate}).")
        except TimeoutError:
            last_error = RuntimeError(f"Timeout 20 detik saat mengambil artikel ({candidate}).")
        except Exception as exc:
            last_error = exc

    if last_error:
        detail = []
        try:
            raw_probe, charset_probe, status_probe, final_probe = _request(url)
            detail.append(f"original_http={status_probe}")
            detail.append(f"final_url={final_probe}")
            detail.append(f"html_bytes={len(raw_probe)}")
            probe_html = raw_probe.decode(charset_probe, errors="replace")
            meta = _MetadataParser()
            meta.feed(probe_html)
            if meta.candidates:
                detail.append(f"metadata_url={meta.candidates[0]}")
            article_probe = _ArticleParser()
            article_probe.feed(probe_html)
            detail.append(f"extracted_chars={len(article_probe.text().strip())}")
        except Exception as probe_exc:
            detail.append(f"probe_error={str(probe_exc)[:180]}")
        raise RuntimeError(f"{last_error} | FETCH_DEBUG: {'; '.join(detail)}")
    raise RuntimeError("Gagal mengambil konten artikel.")
