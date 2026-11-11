
import feedparser

from urllib.parse import quote
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from datetime import datetime, timedelta


# ==========================================================
# RESEARCH CONFIGURATION
# ==========================================================

# Pilihan:
# "AUTO"   = otomatis mengambil bulan berjalan
# "MANUAL" = menggunakan tanggal yang kita tentukan sendiri

RESEARCH_MODE = "AUTO"


# ==========================================================
# MANUAL DATE CONFIGURATION
# ==========================================================
# Digunakan hanya jika:
#
# RESEARCH_MODE = "MANUAL"
#
# Format:
# YYYY-MM-DD

MANUAL_START_DATE = "2026-09-01"

MANUAL_END_DATE = "2026-09-30"


# ==========================================================
# RESEARCH DATE RANGE
# ==========================================================

def get_research_date_range():

    # ------------------------------------------------------
    # MANUAL MODE
    # ------------------------------------------------------

    if RESEARCH_MODE == "MANUAL":

        if not MANUAL_START_DATE or not MANUAL_END_DATE:

            raise ValueError(
                "RESEARCH_MODE='MANUAL' membutuhkan "
                "MANUAL_START_DATE dan MANUAL_END_DATE."
            )

        try:

            start_datetime = datetime.strptime(
                MANUAL_START_DATE,
                "%Y-%m-%d"
            )

            end_datetime = datetime.strptime(
                MANUAL_END_DATE,
                "%Y-%m-%d"
            )

        except ValueError:

            raise ValueError(
                "Format tanggal harus YYYY-MM-DD. "
                "Contoh: 2026-09-01"
            )

        if start_datetime > end_datetime:

            raise ValueError(
                "MANUAL_START_DATE tidak boleh lebih besar "
                "dari MANUAL_END_DATE."
            )

        # Google News menggunakan BEFORE sebagai exclusive.
        #
        # Contoh:
        # MANUAL_END_DATE = 2026-09-14
        #
        # menjadi:
        # before:2026-09-15
        #
        # sehingga tanggal 14 September tetap ikut.

        end_datetime += timedelta(days=1)

        start_date = start_datetime.strftime(
            "%Y-%m-%d"
        )

        end_date = end_datetime.strftime(
            "%Y-%m-%d"
        )

        return start_date, end_date


    # ------------------------------------------------------
    # AUTO MODE
    # ------------------------------------------------------

    if RESEARCH_MODE == "AUTO":

        now = datetime.now()

        # Hari pertama bulan berjalan
        start_datetime = now.replace(
            day=1,
            hour=0,
            minute=0,
            second=0,
            microsecond=0
        )

        # Hari pertama bulan berikutnya
        if now.month == 12:

            end_datetime = start_datetime.replace(
                year=now.year + 1,
                month=1
            )

        else:

            end_datetime = start_datetime.replace(
                month=now.month + 1
            )

        start_date = start_datetime.strftime(
            "%Y-%m-%d"
        )

        end_date = end_datetime.strftime(
            "%Y-%m-%d"
        )

        return start_date, end_date


    # ------------------------------------------------------
    # INVALID MODE
    # ------------------------------------------------------

    raise ValueError(
        "RESEARCH_MODE harus 'AUTO' atau 'MANUAL'."
    )


# ==========================================================
# GOOGLE NEWS SEARCH
# ==========================================================

def search_google_news(query, start_date=None, end_date=None):

    if start_date is None or end_date is None:
        start_date, end_date = get_research_date_range()


    # ------------------------------------------------------
    # BUILD GOOGLE NEWS QUERY
    # ------------------------------------------------------

    search_query = (
        f"{query} "
        f"after:{start_date} "
        f"before:{end_date}"
    )


    # ------------------------------------------------------
    # GOOGLE NEWS RSS URL
    # ------------------------------------------------------

    url = (
        "https://news.google.com/rss/search?"
        f"q={quote(search_query)}"
        f"&hl=id"
        f"&gl=ID"
        f"&ceid=ID:id"
    )


    # ------------------------------------------------------
    # FETCH RSS WITH TIMEOUT + HTTP DIAGNOSTICS
    # ------------------------------------------------------

    request = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36",
            "Accept": "application/rss+xml, application/xml, text/xml, */*",
        },
    )

    try:
        with urlopen(request, timeout=20) as response:
            status_code = getattr(response, "status", 200)
            payload = response.read()
    except HTTPError as exc:
        raise RuntimeError(f"Google News RSS HTTP {exc.code} untuk query: {query}") from exc
    except URLError as exc:
        raise RuntimeError(f"Gagal menghubungi Google News RSS: {exc.reason}") from exc
    except TimeoutError as exc:
        raise RuntimeError("Timeout 20 detik saat mengambil Google News RSS.") from exc

    if status_code >= 400:
        raise RuntimeError(f"Google News RSS mengembalikan HTTP {status_code}.")

    feed = feedparser.parse(payload)
    if getattr(feed, "bozo", False) and not feed.entries:
        detail = str(getattr(feed, "bozo_exception", "RSS tidak dapat diparse"))
        raise RuntimeError(f"RSS tidak valid/kosong: {detail}")


    # ------------------------------------------------------
    # PARSE RESULTS
    # ------------------------------------------------------

    results = []

    for item in feed.entries:

        results.append({

            "title":
                item.get(
                    "title",
                    ""
                ),

            "url":
                item.get(
                    "link",
                    ""
                ),

            "published":
                item.get(
                    "published",
                    ""
                ),

            "source":
                item.get(
                    "source",
                    {}
                ).get(
                    "title",
                    ""
                ),

            "query":
                query
        })


    return results

