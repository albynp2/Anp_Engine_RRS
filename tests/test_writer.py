from database.database import create_database, get_new_stories
from research.writer import generate_story


def main():

    create_database()

    # Ambil kandidat NEW
    stories = get_new_stories(30)

    if len(stories) == 0:
        print("❌ Tidak ada kandidat NEW di database.")
        return

    # Untuk testing, gunakan kandidat pertama
    story = stories[0]

    print("\n===================================")
    print("        SELECTED STORY")
    print("===================================\n")

    print(f"Title  : {story['title']}")
    print(f"Source : {story['source']}")
    print(f"Date   : {story['published']}")
    print(f"URL    : {story['url']}")

    # Generate story
    result = generate_story(story)

    print("\n")
    print("===================================")
    print("        📝 GENERATED STORY")
    print("===================================\n")

    print("TITLE:")
    print(result["title"])

    print("\nHOOK:")
    print(result["hook"])

    print("\nSCRIPT:")
    print(result["script"])

    print("\nENDING:")
    print(result["ending"])

    print("\nCAPTION:")
    print(result["caption"])

    print("\nHASHTAGS:")

    for tag in result["hashtags"]:
        print(tag)

    print("\n===================================")


if __name__ == "__main__":
    main()