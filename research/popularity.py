
import re

from collections import defaultdict

from tqdm import tqdm

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


# ==========================================================
# BASIC STOPWORDS
# ==========================================================
# Kata terlalu umum yang tidak banyak membantu
# dalam menentukan similarity antar judul.

BASIC_STOPWORDS = {

    "yang",
    "dan",
    "di",
    "ke",
    "dari",
    "ini",
    "itu",
    "dengan",
    "saat",
    "karena",
    "para",
    "sebuah",
    "ada",
    "dalam",
    "untuk",
    "hingga",
    "oleh",
    "tentang",
    "asal",
    "indonesia"
}


# ==========================================================
# CLEAN TITLE
# ==========================================================

def clean_title(title):

    title = title.lower()

    title = re.sub(
        r"[^a-z0-9\s]",
        " ",
        title
    )

    title = re.sub(
        r"\s+",
        " ",
        title
    ).strip()

    words = []

    for word in title.split():

        if word in BASIC_STOPWORDS:
            continue

        if len(word) < 3:
            continue

        words.append(word)

    return " ".join(words)


# ==========================================================
# BUILD SIMILARITY MATRIX
# ==========================================================

def build_similarity_matrix(stories):

    print("\n🧠 Membuat TF-IDF vectors...")

    documents = []

    for story in tqdm(
        stories,
        desc="🔤 Processing titles",
        unit="article"
    ):

        documents.append(
            clean_title(
                story["title"]
            )
        )

    vectorizer = TfidfVectorizer(
        ngram_range=(1, 2),
        min_df=1,
        max_df=0.90
    )

    matrix = vectorizer.fit_transform(
        documents
    )

    vocabulary_size = len(
        vectorizer.get_feature_names_out()
    )

    print(
        f"✅ Vocabulary: "
        f"{vocabulary_size} terms"
    )

    print(
        "🔗 Menghitung similarity matrix..."
    )

    similarity_matrix = cosine_similarity(
        matrix
    )

    return similarity_matrix


# ==========================================================
# CLUSTER STORIES
# ==========================================================

def cluster_stories(
    stories,
    similarity_matrix,
    threshold=0.35
):

    print("\n🧩 Membentuk topic clusters...")

    clusters = []

    assigned = set()

    for i in tqdm(
        range(len(stories)),
        desc="🧩 Clustering",
        unit="article"
    ):

        if i in assigned:
            continue

        cluster_indexes = [i]

        assigned.add(i)

        for j in range(
            i + 1,
            len(stories)
        ):

            if j in assigned:
                continue

            similarity = similarity_matrix[
                i,
                j
            ]

            if similarity >= threshold:

                cluster_indexes.append(j)

                assigned.add(j)

        cluster = [
            stories[index]
            for index in cluster_indexes
        ]

        clusters.append(
            cluster
        )

    return clusters


# ==========================================================
# CALCULATE POPULARITY
# ==========================================================

def calculate_popularity(cluster):

    coverage_count = len(
        cluster
    )

    sources = set()

    queries = set()

    for story in cluster:

        source = story.get(
            "source",
            ""
        ).strip().lower()

        query = story.get(
            "query",
            ""
        ).strip().lower()

        if source:

            sources.add(
                source
            )

        if query:

            queries.add(
                query
            )

    unique_source_count = len(
        sources
    )

    query_count = len(
        queries
    )

    # ======================================================
    # POPULARITY SCORE
    # ======================================================

    # Coverage:
    # semakin banyak artikel membahas topik
    # semakin tinggi score.
    #
    # Maximum = 40

    coverage_score = min(
        coverage_count * 8,
        40
    )

    # Sources:
    # semakin banyak media berbeda
    # semakin tinggi score.
    #
    # Maximum = 40

    source_score = min(
        unique_source_count * 10,
        40
    )

    # Queries:
    # semakin banyak query yang menemukan
    # topik tersebut.
    #
    # Maximum = 20

    query_score = min(
        query_count * 7,
        20
    )

    popularity_score = (
        coverage_score
        + source_score
        + query_score
    )

    popularity_score = min(
        popularity_score,
        100
    )

    return {

        "coverage_count":
            coverage_count,

        "unique_source_count":
            unique_source_count,

        "query_count":
            query_count,

        "coverage_score":
            coverage_score,

        "source_score":
            source_score,

        "query_score":
            query_score,

        "popularity_score":
            popularity_score
    }


# ==========================================================
# PRINT TOP POPULARITY
# ==========================================================

def print_top_popularity(
    popularity_results,
    limit=10
):

    print("\n")
    print("=" * 70)
    print("        🔥 TOP RESEARCH POPULARITY")
    print("=" * 70)

    if not popularity_results:

        print("\nTidak ada topic popularity.\n")

        return

    top_results = popularity_results[
        :limit
    ]

    for index, result in enumerate(
        top_results,
        start=1
    ):

        print(
            f"\n#{index} "
            f"{result['title']}"
        )

        print(
            f"   🔥 Popularity : "
            f"{result['popularity_score']:.1f}"
        )

        print(
            f"   📰 Coverage   : "
            f"{result['coverage_count']} articles"
        )

        print(
            f"   🏢 Sources    : "
            f"{result['unique_source_count']} media"
        )

        print(
            f"   🔎 Queries    : "
            f"{result['query_count']}"
        )

        print(
            f"   ├─ Coverage Score : "
            f"{result['coverage_score']}"
        )

        print(
            f"   ├─ Source Score   : "
            f"{result['source_score']}"
        )

        print(
            f"   └─ Query Score    : "
            f"{result['query_score']}"
        )

        print("-" * 70)


# ==========================================================
# ANALYZE POPULARITY
# ==========================================================

def analyze_popularity(stories):

    print("\n")
    print("=" * 70)
    print("        🔥 POPULARITY ENGINE")
    print("=" * 70)

    print(
        f"\n📊 Menganalisis "
        f"{len(stories)} artikel..."
    )

    if len(stories) == 0:

        return []


    # ======================================================
    # TF-IDF
    # ======================================================

    similarity_matrix = build_similarity_matrix(
        stories
    )


    # ======================================================
    # CLUSTERING
    # ======================================================

    clusters = cluster_stories(
        stories,
        similarity_matrix,
        threshold=0.35
    )

    print(
        f"\n🧩 Topic clusters: "
        f"{len(clusters)}"
    )


    # ======================================================
    # POPULARITY CALCULATION
    # ======================================================

    popularity_results = []

    for cluster in tqdm(
        clusters,
        desc="🔥 Calculating popularity",
        unit="topic"
    ):

        popularity = calculate_popularity(
            cluster
        )

        # Artikel pertama digunakan
        # sebagai representative topic.

        representative = cluster[0]

        popularity_results.append({

            "title":
                representative["title"],

            "url":
                representative["url"],

            "source":
                representative["source"],

            "published":
                representative["published"],

            "stories":
                cluster,

            **popularity
        })


    # ======================================================
    # SORT BY POPULARITY
    # ======================================================

    popularity_results.sort(
        key=lambda x:
            x["popularity_score"],
        reverse=True
    )


    # ======================================================
    # PRINT TOP RESULTS
    # ======================================================

    print_top_popularity(
        popularity_results,
        limit=10
    )


    # ======================================================
    # RETURN
    # ======================================================

    return popularity_results
