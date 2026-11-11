from datetime import datetime
from email.utils import parsedate_to_datetime

from tqdm import tqdm

from research.researcher import (
    search_google_news,
    get_research_date_range
)

from database.database import (
    create_database,
    save_story,
    get_story_status,
    get_story_id_by_url,
    queue_selected_topic,
    get_queue_counts
)

from ai.scorer import score_stories

from research.popularity import analyze_popularity


QUERIES = [
    "kisah horor nyata Indonesia",
    "cerita mistis Indonesia",
    "kejadian misterius Indonesia",
    "pengalaman horor Indonesia",
    "urban legend Indonesia",
    "misteri Indonesia",
    "kejadian aneh Indonesia",
    "penampakan Indonesia"
]


EXCLUDED_KEYWORDS = [
    "film",
    "netflix",
    "bioskop",
    "rekomendasi",
    "rating",
    "tayang",
    "box office",
    "trailer",
    "jadwal tayang",
    "sinopsis"
]


def is_relevant(story):

    title = story["title"].lower()

    for keyword in EXCLUDED_KEYWORDS:

        if keyword in title:
            return False

    return True


def is_valid_date(story, start_date=None, end_date=None):
    published = story.get("published", "")
    if not published:
        return False
    try:
        published_date = parsedate_to_datetime(published).date()
        if start_date and end_date:
            start = datetime.strptime(start_date, "%Y-%m-%d").date()
            end_exclusive = datetime.strptime(end_date, "%Y-%m-%d").date()
            return start <= published_date < end_exclusive
        return published_date.year == datetime.now().year
    except Exception:
        return False


def print_section(title):

    print("\n")
    print("=" * 60)
    print(f"  {title}")
    print("=" * 60)


def build_ai_candidates(
    popularity_results,
    limit=30
):

    candidates = []

    selected_topics = popularity_results[:limit]

    for topic in tqdm(
        selected_topics,
        desc="🤖 Preparing topics",
        unit="topic"
    ):

        candidates.append({

            "title":
                topic["title"],

            "url":
                topic["url"],

            "source":
                topic["source"],

            "published":
                topic["published"],

            "popularity_score":
                topic["popularity_score"],

            "coverage_count":
                topic["coverage_count"],

            "unique_source_count":
                topic["unique_source_count"],

            "query_count":
                topic["query_count"],

            "stories":
                topic["stories"]
        })

    return candidates


def main(queries=None, excluded_keywords=None, top_candidates=30, progress_callback=None):

    global QUERIES, EXCLUDED_KEYWORDS
    if queries is not None:
        QUERIES = [q.strip() for q in queries if q and q.strip()]
    if excluded_keywords is not None:
        EXCLUDED_KEYWORDS = [k.strip().lower() for k in excluded_keywords if k and k.strip()]

    def report_stage(label, percent):
        print(f"\n[PROGRESS:{percent}] {label}")
        if progress_callback:
            progress_callback(label, percent)

    report_stage("Menyiapkan database dan konfigurasi", 5)
    print("\n")
    print("=" * 60)
    print("        HORROR CONTENT FACTORY")
    print("=" * 60)

    # ======================================================
    # DATABASE
    # ======================================================

    print_section("DATABASE")

    create_database()

    print(
        "✅ SQLite database ready"
    )

    # ======================================================
    # RESEARCH WINDOW
    # ======================================================

    start_date, end_date = (
        get_research_date_range()
    )

    report_stage("Menentukan rentang tanggal riset", 10)
    print_section("RESEARCH WINDOW")

    print(
        f"📅 Start : {start_date}"
    )

    print(
        f"📅 End   : {end_date}"
    )

    print(
        "\n💡 Research mengambil "
        "bulan sekarang + bulan sebelumnya."
    )

    # ======================================================
    # RESEARCH
    # ======================================================

    report_stage("Mengambil artikel dari Google News RSS", 20)
    print_section("RESEARCH")

    all_results = []

    progress = tqdm(
        QUERIES,
        desc="🔎 Researching",
        unit="query"
    )

    for query in progress:

        progress.set_postfix(
            query=query[:30]
        )

        try:

            results = search_google_news(
                query
            )

            all_results.extend(
                results
            )

        except Exception as e:

            print(
                f"\n❌ Error query: {query}"
            )

            print(
                f"   {e}"
            )

    print(
        f"\n📥 Total hasil research: "
        f"{len(all_results)}"
    )

    # ======================================================
    # DEDUPLICATE
    # ======================================================

    report_stage("Menghapus URL duplikat", 38)
    print_section("DEDUPLICATE")

    unique_results = {}

    for story in tqdm(
        all_results,
        desc="🧹 Deduplicating",
        unit="article"
    ):

        url = story["url"]

        if not url:
            continue

        unique_results[url] = story

    results = list(
        unique_results.values()
    )

    print(
        f"\n✅ Setelah deduplicate: "
        f"{len(results)}"
    )

    # ======================================================
    # FILTER
    # ======================================================

    report_stage("Memfilter artikel dan tanggal", 48)
    print_section("FILTER")

    filtered_results = []

    rejected_relevance = 0
    rejected_date = 0

    for story in tqdm(
        results,
        desc="🎯 Filtering",
        unit="article"
    ):

        if not is_relevant(story):

            rejected_relevance += 1

            continue

        if not is_valid_date(story, start_date, end_date):

            rejected_date += 1

            continue

        filtered_results.append(
            story
        )

    print(
        f"\n✅ Lolos filter     : "
        f"{len(filtered_results)}"
    )

    print(
        f"🚫 Bukan horror     : "
        f"{rejected_relevance}"
    )

    print(
        f"🚫 Tahun tidak valid: "
        f"{rejected_date}"
    )

    if len(filtered_results) == 0:

        print(
            "\n❌ Tidak ada artikel "
            "yang lolos filter."
        )

        return

    # ======================================================
    # POPULARITY
    # ======================================================

    report_stage("Analisis popularitas lokal dan clustering", 60)
    print_section("POPULARITY ENGINE")

    popularity_results = (
        analyze_popularity(
            filtered_results
        )
    )

    if len(popularity_results) == 0:

        print(
            "\n❌ Tidak ada topic cluster."
        )

        return

    print(
        "\n🔥 TOP RESEARCH POPULAR TOPICS\n"
    )

    for rank, item in enumerate(
        popularity_results[:10],
        start=1
    ):

        print(
            f"#{rank} — "
            f"{item['title']}"
        )

        print(
            f"   Popularity       : "
            f"{item['popularity_score']}"
        )

        print(
            f"   Coverage         : "
            f"{item['coverage_count']} artikel"
        )

        print(
            f"   Unique Sources   : "
            f"{item['unique_source_count']} media"
        )

        print(
            f"   Query Matches    : "
            f"{item['query_count']} query"
        )

        print(
            "-" * 60
        )

    # ======================================================
    # DATABASE SAVE
    # ======================================================

    report_stage("Menyimpan artikel ke database", 72)
    print_section("DATABASE SAVE")

    new_count = 0
    existing_count = 0

    for story in tqdm(
        filtered_results,
        desc="💾 Saving",
        unit="article"
    ):

        status = get_story_status(
            story["url"]
        )

        if status is None:

            save_story(story)

            new_count += 1

        else:

            existing_count += 1

    print(
        f"\n🆕 Data baru     : "
        f"{new_count}"
    )

    print(
        f"📚 Sudah ada     : "
        f"{existing_count}"
    )

    # ======================================================
    # BUILD AI CANDIDATES
    # ======================================================

    report_stage("Menyiapkan kandidat AI", 80)
    print_section("BUILD AI CANDIDATES")

    candidates = build_ai_candidates(
        popularity_results,
        limit=max(1, min(int(top_candidates), 100))
    )

    print(
        f"\n🤖 Kandidat topic untuk AI: "
        f"{len(candidates)}"
    )

    if len(candidates) == 0:

        print(
            "\n❌ Tidak ada kandidat "
            "untuk AI."
        )

        return

    print(
        "\n💡 AI hanya menerima "
        "TOP 30 topic hasil local ranking."
    )

    print(
        "💰 Token optimization: "
        "candidate dipangkas secara lokal."
    )

    # ======================================================
    # AI SCORING
    # ======================================================

    report_stage("Menilai kandidat dengan AI", 86)
    print_section("AI SCORING")

    print(
        f"🧠 Mengirim "
        f"{len(candidates)} topic ke GPT..."
    )

    print(
        "⏳ GPT melakukan final ranking..."
    )

    try:

        result = score_stories(
            candidates
        )

    except Exception as e:

        print(
            "\n❌ AI scoring gagal."
        )

        print(
            f"Error: {e}"
        )

        return

    # ======================================================
    # TOP HORROR
    # ======================================================

    print_section("TOP HORROR")

    top_10 = result.get(
        "top_10",
        []
    )

    if not top_10:

        print(
            "❌ AI tidak mengembalikan "
            "TOP 10."
        )

        return

    for rank, item in enumerate(
        top_10,
        start=1
    ):

        candidate_id = item["id"]

        if (
            candidate_id < 1
            or candidate_id > len(candidates)
        ):

            print(
                f"\n⚠️ ID AI tidak valid: "
                f"{candidate_id}"
            )

            continue

        topic = candidates[
            candidate_id - 1
        ]

        print(
            f"\n🏆 #{rank} — "
            f"{topic['title']}"
        )

        print(
            f"Source              : "
            f"{topic['source']}"
        )

        print(
            f"Published           : "
            f"{topic['published']}"
        )

        print(
            f"Research Popularity : "
            f"{topic['popularity_score']}"
        )

        print(
            f"Coverage            : "
            f"{topic['coverage_count']} artikel"
        )

        print(
            f"Unique Sources      : "
            f"{topic['unique_source_count']} media"
        )

        print(
            f"Query Matches       : "
            f"{topic['query_count']}"
        )

        print(
            f"Horror              : "
            f"{item['horror_strength']}"
        )

        print(
            f"Story Potential     : "
            f"{item['story_potential']}"
        )

        print(
            f"Curiosity           : "
            f"{item['curiosity']}"
        )

        print(
            f"Uniqueness          : "
            f"{item['uniqueness']}"
        )

        print(
            f"Freshness           : "
            f"{item['freshness']}"
        )

        print(
            f"Overall             : "
            f"{item['overall_score']}"
        )

        print(
            f"Reason              : "
            f"{item['reason']}"
        )

        print(
            f"URL                 : "
            f"{topic['url']}"
        )

        print(
            "-" * 70
        )

    # ======================================================
    # PRODUCTION QUEUE
    # ======================================================

    report_stage("Memasukkan topik terpilih ke antrean produksi", 96)
    print_section("PRODUCTION QUEUE")

    queued_count = 0
    already_queued_count = 0
    invalid_count = 0

    for rank, item in tqdm(
        enumerate(top_10, start=1),
        total=len(top_10),
        desc="📥 Queueing TOP 10",
        unit="topic"
    ):

        candidate_id = item["id"]

        # --------------------------------------------------
        # VALIDATE AI ID
        # --------------------------------------------------

        if (
            candidate_id < 1
            or candidate_id > len(candidates)
        ):

            invalid_count += 1

            continue

        # --------------------------------------------------
        # GET CANDIDATE
        # --------------------------------------------------

        topic = candidates[
            candidate_id - 1
        ]

        # --------------------------------------------------
        # GET STORY ID
        # --------------------------------------------------

        story_id = get_story_id_by_url(
            topic["url"]
        )

        if story_id is None:

            invalid_count += 1

            print(
                f"\n⚠️ Story tidak ditemukan DB:"
            )

            print(
                f"   {topic['title']}"
            )

            continue

        # --------------------------------------------------
        # INSERT QUEUE
        # --------------------------------------------------

        inserted = queue_selected_topic(

            story_id=story_id,

            rank=rank,

            research_popularity=
                topic["popularity_score"],

            overall_score=
                item["overall_score"]
        )

        if inserted:

            queued_count += 1

        else:

            already_queued_count += 1

    print(
        f"\n🆕 Masuk production queue : "
        f"{queued_count}"
    )

    print(
        f"♻️ Sudah ada di queue     : "
        f"{already_queued_count}"
    )

    print(
        f"⚠️ Invalid / tidak ditemukan: "
        f"{invalid_count}"
    )

    # ======================================================
    # QUEUE STATUS
    # ======================================================

    print_section("QUEUE STATUS")

    queue_counts = get_queue_counts()

    print(
        f"🟡 SELECTED  : "
        f"{queue_counts.get('SELECTED', 0)}"
    )

    print(
        f"🟢 WRITTEN   : "
        f"{queue_counts.get('WRITTEN', 0)}"
    )

    print(
        f"🎬 RENDERED  : "
        f"{queue_counts.get('RENDERED', 0)}"
    )

    print(
        f"🚀 PUBLISHED : "
        f"{queue_counts.get('PUBLISHED', 0)}"
    )

    print(
        f"🔴 FAILED    : "
        f"{queue_counts.get('FAILED', 0)}"
    )

    # ======================================================
    # COMPLETE
    # ======================================================

    print_section("PROCESS COMPLETE")

    print(
        "✅ Research selesai"
    )

    print(
        "✅ Filtering selesai"
    )

    print(
        "✅ TF-IDF clustering selesai"
    )

    print(
        "✅ Popularity ranking selesai"
    )

    print(
        "✅ Database selesai"
    )

    print(
        "✅ AI final scoring selesai"
    )

    print(
        f"🏆 {len(top_10)} topik berhasil dipilih"
    )

    print(
        "✅ Production queue updated"
    )
    report_stage("Pipeline selesai", 100)


if __name__ == "__main__":
    main()
