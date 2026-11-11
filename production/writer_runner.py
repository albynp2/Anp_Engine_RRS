from tqdm import tqdm

from database.database import (
    create_database,
    get_queue_items,
    save_generated_story,
    mark_queue_status,
    story_already_written
)

from research.writer import generate_story


def print_header():

    print("\n")
    print("=" * 70)
    print("             HORROR STORY WRITER")
    print("=" * 70)


def print_story_list(stories):

    print("\n")
    print("=" * 70)
    print("             SELECTED STORIES")
    print("=" * 70)

    if not stories:

        print(
            "\n🎉 Tidak ada story SELECTED."
        )

        return

    print(
        f"\n📚 Total story tersedia: "
        f"{len(stories)}\n"
    )

    for index, story in enumerate(
        stories,
        start=1
    ):

        print(
            f"[{index}] "
            f"{story['title']}"
        )

        print(
            f"    Score      : "
            f"{story['overall_score']}"
        )

        print(
            f"    Popularity : "
            f"{story['research_popularity']}"
        )

        print(
            f"    Rank       : "
            f"#{story['rank']}"
        )

        print(
            f"    Source     : "
            f"{story['source']}"
        )

        print(
            "-" * 70
        )


def show_story_detail(story):

    print("\n")
    print("=" * 70)
    print("             STORY DETAIL")
    print("=" * 70)

    print(
        f"\n🏆 Rank              : "
        f"#{story['rank']}"
    )

    print(
        f"🆔 Queue ID          : "
        f"{story['queue_id']}"
    )

    print(
        f"🆔 Story ID          : "
        f"{story['story_id']}"
    )

    print(
        f"🎯 Overall Score     : "
        f"{story['overall_score']}"
    )

    print(
        f"🔥 Research Popularity: "
        f"{story['research_popularity']}"
    )

    print(
        f"📰 Source            : "
        f"{story['source']}"
    )

    print(
        f"📅 Published         : "
        f"{story['published']}"
    )

    print(
        f"🔗 URL               : "
        f"{story['url']}"
    )

    print(
        "\n📖 TITLE:"
    )

    print(
        story["title"]
    )


def generate_selected_story(story):

    print("\n")

    if story_already_written(
        story["story_id"]
    ):

        print(
            "⚠️ Story ini ternyata "
            "sudah memiliki generated story."
        )

        print(
            "♻️ Queue status akan "
            "diubah menjadi WRITTEN."
        )

        mark_queue_status(
            story["queue_id"],
            "WRITTEN"
        )

        return True

    print(
        "🚀 Memulai story generation..."
    )

    print(
        "💡 Hanya 1 story yang dikirim "
        "ke GPT."
    )

    print(
        "💰 Token usage tetap hemat."
    )

    with tqdm(
        total=1,
        desc="✍️ Generating story",
        unit="story"
    ) as progress:

        try:

            result = generate_story(
                story
            )

            progress.update(1)

        except Exception as e:

            print(
                "\n❌ Story generation gagal."
            )

            print(
                f"Error: {e}"
            )

            mark_queue_status(
                story["queue_id"],
                "FAILED"
            )

            print(
                "\n🔴 Queue status → FAILED"
            )

            return False

    print(
        "\n💾 Saving generated story..."
    )

    save_generated_story(

        story_id=
            story["story_id"],

        result=result
    )

    print(
        "✅ Generated story saved"
    )

    mark_queue_status(
        story["queue_id"],
        "WRITTEN"
    )

    print(
        "🟢 Queue status → WRITTEN"
    )

    print("\n")
    print("=" * 70)
    print("             GENERATED STORY")
    print("=" * 70)

    print(
        "\nTITLE:"
    )

    print(
        result.get(
            "title",
            ""
        )
    )

    print(
        "\nHOOK:"
    )

    print(
        result.get(
            "hook",
            ""
        )
    )

    print(
        "\nSCRIPT:"
    )

    print(
        result.get(
            "script",
            ""
        )
    )

    print(
        "\nENDING:"
    )

    print(
        result.get(
            "ending",
            ""
        )
    )

    print(
        "\nCAPTION:"
    )

    print(
        result.get(
            "caption",
            ""
        )
    )

    print(
        "\nHASHTAGS:"
    )

    hashtags = result.get(
        "hashtags",
        []
    )

    for hashtag in hashtags:

        print(
            f"  {hashtag}"
        )

    print("\n")

    print("=" * 70)
    print("             ✅ WRITING COMPLETE")
    print("=" * 70)

    return True


def main():

    print_header()

    print(
        "\n📂 Initializing database..."
    )

    create_database()

    print(
        "✅ Database ready"
    )

    while True:

        stories = get_queue_items(
            status="SELECTED",
            limit=100
        )

        print_story_list(
            stories
        )

        if not stories:

            print(
                "\n🎉 Semua story SELECTED "
                "sudah diproses."
            )

            break

        print("\n")

        print(
            "Pilihan:"
        )

        print(
            "  [1-{}] Generate story".format(
                len(stories)
            )
        )

        print(
            "  [R]     Refresh list"
        )

        print(
            "  [Q]     Keluar"
        )

        choice = input(
            "\n👉 Pilih story: "
        ).strip()

        if not choice:

            print(
                "\n⚠️ Pilihan tidak boleh kosong."
            )

            continue

        if choice.lower() == "q":

            print(
                "\n👋 Writer dihentikan."
            )

            break

        if choice.lower() == "r":

            print(
                "\n🔄 Refreshing queue..."
            )

            continue

        try:

            selected_number = int(
                choice
            )

        except ValueError:

            print(
                "\n❌ Input tidak valid."
            )

            print(
                "Masukkan nomor story "
                "atau Q."
            )

            continue

        if (
            selected_number < 1
            or selected_number > len(stories)
        ):

            print(
                "\n❌ Nomor story tidak valid."
            )

            continue

        selected_story = stories[
            selected_number - 1
        ]

        show_story_detail(
            selected_story
        )

        print("\n")

        confirmation = input(
            "🚀 Generate story ini? [Y/N]: "
        ).strip().lower()

        if confirmation != "y":

            print(
                "\n↩️ Kembali ke daftar story."
            )

            continue

        success = generate_selected_story(
            selected_story
        )

        if success:

            print("\n")
            print(
                "📋 Kembali ke SELECTED queue..."
            )

        else:

            print("\n")
            print(
                "⚠️ Story gagal diproses."
            )

    print("\n")
    print("=" * 70)
    print("             WRITER SESSION COMPLETE")
    print("=" * 70)


if __name__ == "__main__":

    main()