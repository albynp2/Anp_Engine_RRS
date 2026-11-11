from tqdm import tqdm

from database.database import DB_PATH, get_connection


STATUS_CONFIG = {
    "SELECTED": {
        "icon": "🟡",
        "label": "SELECTED"
    },
    "WRITTEN": {
        "icon": "🟢",
        "label": "WRITTEN"
    },
    "RENDERED": {
        "icon": "🎬",
        "label": "RENDERED"
    },
    "PUBLISHED": {
        "icon": "🚀",
        "label": "PUBLISHED"
    },
    "FAILED": {
        "icon": "🔴",
        "label": "FAILED"
    }
}


def get_queue_summary():

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            status,
            COUNT(*)
        FROM production_queue
        GROUP BY status
        ORDER BY status
    """)

    rows = cursor.fetchall()

    conn.close()

    summary = {}

    for status, count in rows:

        summary[status] = count

    return summary


def get_queue_items(status):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT

            q.id,
            q.story_id,
            q.rank,
            q.research_popularity,
            q.overall_score,
            q.selected_at,
            q.status,

            s.title,
            s.source,
            s.published,

            CASE
                WHEN g.id IS NOT NULL
                THEN 1
                ELSE 0
            END AS has_generated_story

        FROM production_queue q

        JOIN stories s
            ON q.story_id = s.id

        LEFT JOIN generated_stories g
            ON q.story_id = g.story_id

        WHERE q.status = ?

        ORDER BY
            q.rank ASC,
            q.id ASC
    """, (
        status,
    ))

    rows = cursor.fetchall()

    conn.close()

    results = []

    for row in rows:

        results.append({

            "queue_id": row[0],

            "story_id": row[1],

            "rank": row[2],

            "research_popularity": row[3],

            "overall_score": row[4],

            "selected_at": row[5],

            "status": row[6],

            "title": row[7],

            "source": row[8],

            "published": row[9],

            "has_generated_story": row[10]
        })

    return results


def print_summary():

    print("\n")
    print("=" * 70)
    print("             HORROR CONTENT PIPELINE")
    print("=" * 70)

    summary = get_queue_summary()

    total = sum(
        summary.values()
    )

    print("\n📊 PIPELINE SUMMARY\n")

    for status in STATUS_CONFIG:

        icon = STATUS_CONFIG[
            status
        ]["icon"]

        label = STATUS_CONFIG[
            status
        ]["label"]

        count = summary.get(
            status,
            0
        )

        print(
            f"{icon} {label:<12}: "
            f"{count}"
        )

    print(
        f"\n📦 TOTAL QUEUE : {total}"
    )


def print_status_section(status):

    config = STATUS_CONFIG[
        status
    ]

    icon = config["icon"]

    label = config["label"]

    items = get_queue_items(
        status
    )

    print("\n")
    print("=" * 70)
    print(
        f"{icon} {label}"
    )
    print("=" * 70)

    if not items:

        print(
            "\n   Tidak ada story."
        )

        return

    print(
        f"\n📚 {len(items)} story\n"
    )

    for number, item in enumerate(
        tqdm(
            items,
            desc=f"📖 Loading {label}",
            unit="story"
        ),
        start=1
    ):

        print("\n")

        print(
            f"{number}. "
            f"{item['title']}"
        )

        print(
            f"   Queue ID          : "
            f"{item['queue_id']}"
        )

        print(
            f"   Story ID          : "
            f"{item['story_id']}"
        )

        print(
            f"   Rank              : "
            f"#{item['rank']}"
        )

        print(
            f"   Overall Score     : "
            f"{item['overall_score']}"
        )

        print(
            f"   Research Popularity: "
            f"{item['research_popularity']}"
        )

        print(
            f"   Source            : "
            f"{item['source']}"
        )

        print(
            f"   Published         : "
            f"{item['published']}"
        )

        print(
            f"   Selected At       : "
            f"{item['selected_at']}"
        )

        if item[
            "has_generated_story"
        ]:

            print(
                "   📝 Generated Story : YES"
            )

        else:

            print(
                "   📝 Generated Story : NO"
            )

        print(
            "-" * 70
        )


def main():

    print_summary()

    for status in STATUS_CONFIG:

        print_status_section(
            status
        )

    print("\n")
    print("=" * 70)
    print("             DASHBOARD COMPLETE")
    print("=" * 70)

    print(
        "\n💡 Jalankan lagi kapan saja dengan:"
    )

    print(
        "   python dashboard.py"
    )


if __name__ == "__main__":

    main()