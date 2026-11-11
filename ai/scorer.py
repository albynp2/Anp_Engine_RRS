from openai import OpenAI
from dotenv import load_dotenv

import os
import json


load_dotenv()


client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY")
)


def score_stories(topics):

    candidates = []

    for i, topic in enumerate(
        topics,
        start=1
    ):

        candidates.append({

            "id": i,

            "title":
                topic["title"],

            "source":
                topic["source"],

            "published":
                topic["published"],

            "research_popularity":
                topic["popularity_score"],

            "coverage_count":
                topic["coverage_count"],

            "unique_source_count":
                topic["unique_source_count"],

            "query_count":
                topic["query_count"],
            "source_content":
                (topic.get("source_content") or "")[:2000]
        })

    prompt = f"""
Kamu adalah Content Researcher sekaligus
Content Quality Gate untuk channel
cerita horror / misteri Indonesia.

Saya sudah melakukan:

- Google News research
- filtering
- deduplication
- TF-IDF clustering
- popularity analysis

secara lokal.

Kamu TIDAK perlu melakukan research internet.

Tugas kamu adalah memilih TOP 10 topik yang
PALING LAYAK dijadikan konten horror/misteri
YouTube Shorts dan Facebook Reels.

==================================================
PRINSIP UTAMA
==================================================

Jangan hanya memilih artikel karena memiliki
kata:

- horror
- mistis
- misteri
- gaib
- kesurupan
- angker

Yang paling penting adalah:

APAKAH TOPIK TERSEBUT MEMILIKI CERITA
YANG CUKUP KUAT UNTUK DIJADIKAN VIDEO?

==================================================
QUALITY GATE
==================================================

Sebelum memberi skor, lakukan pemeriksaan:

1. APAKAH ADA PERISTIWA / MISTERI YANG BISA
   DICERITAKAN?

2. APAKAH TOPIK MEMILIKI UNSUR HORROR,
   MISTIS, MISTERI, ATAU KEANEHAN YANG KUAT?

3. APAKAH TOPIK BISA MENJADI NARASI
   60-90 DETIK?

4. APAKAH PENONTON AKAN MEMILIKI RASA
   PENASARAN?

5. APAKAH INFORMASINYA CUKUP UNTUK WRITER?

Jika jawabannya sebagian besar TIDAK,
berikan skor rendah walaupun popularity tinggi.

==================================================
TOPIK YANG HARUS DITURUNKAN NILAINYA
==================================================

Turunkan skor secara signifikan untuk:

1. Sinopsis film.

2. Review film.

3. Trailer film.

4. Jadwal tayang.

5. Promosi film.

6. Berita artis yang hanya menyebut kata
   "mistis" tetapi tidak memiliki kejadian
   yang bisa diceritakan.

7. Kostum, properti, atau benda yang disebut
   mistis tetapi tidak memiliki cerita yang kuat.

8. Berita entertainment yang tidak memiliki
   pengalaman atau kejadian misterius yang
   jelas.

9. Artikel yang terlalu minim informasi.

10. Topik yang hanya menjelaskan legenda secara
    umum tanpa cerita, kejadian, atau misteri
    spesifik.

==================================================
TOPIK YANG DIPRIORITASKAN
==================================================

Prioritaskan:

🔥 Pengalaman mistis seseorang.

🔥 Kesaksian tentang kejadian aneh.

🔥 Tempat yang memiliki cerita horor kuat.

🔥 Urban legend dengan cerita spesifik.

🔥 Kejadian misterius yang baru diberitakan.

🔥 Penampakan yang dilaporkan.

🔥 Pengalaman kru / pekerja / pengunjung
   di lokasi tertentu.

🔥 Misteri yang memiliki detail cukup untuk
   dibuat menjadi storytelling.

🔥 Cerita lokal Indonesia yang unik dan
   tidak terlalu generik.

==================================================
ENTERTAINMENT FILTER
==================================================

Konten entertainment TIDAK otomatis ditolak.

Contoh:

"Artis mengalami kejadian mistis saat
syuting di lokasi tertentu."

BISA dipilih jika kejadian mistisnya
jelas dan memiliki story potential.

Namun:

"Artis memakai kostum yang disebut memiliki
kisah mistis."

tetapi tidak ada kejadian atau pengalaman
yang jelas,

MAKA beri skor rendah.

==================================================
FACT VS STORY POTENTIAL
==================================================

Jangan mengarang fakta.

Nilai berdasarkan informasi yang tersedia
dari kandidat.

Jika sebuah topik hanya memiliki satu klaim
mistis yang sangat singkat, jangan memberi
Story Potential tinggi hanya karena judulnya
terdengar menyeramkan.

==================================================
SCORING
==================================================

Berikan skor 0-100:

horror_strength
story_potential
curiosity
uniqueness
freshness

Tambahkan juga:

content_quality

Content Quality berarti:

0-39  = sangat lemah
40-59  = lemah
60-69  = cukup
70-79  = bagus
80-89  = sangat bagus
90-100 = sangat kuat

==================================================
BOBOT FINAL
==================================================

Source Coverage    : 40%
Search Relevance   : 30%
Recency            : 20%
Source Quality     : 10%

Namun:

Jika content_quality < 50,
overall_score HARUS dibatasi maksimal 49.

Jika content_quality < 60,
overall_score HARUS dibatasi maksimal 59.

Dengan demikian popularity tinggi tidak bisa
mengangkat topik yang sebenarnya buruk.

==================================================
CONTOH
==================================================

Contoh kandidat:

"Misteri Kostum Mahadewi Yura Yunita"

Jika hanya diketahui bahwa Yura menyebut
ada pengalaman bernuansa mistis tetapi tidak
ada kejadian spesifik yang dapat diceritakan:

content_quality:
rendah

story_potential:
rendah

horror_strength:
sedang atau rendah

Topik seperti ini tidak boleh mengalahkan
cerita pengalaman mistis yang memiliki
kejadian lebih jelas.

==================================================
SOURCE COVERAGE
==================================================

Source Coverage dihitung secara lokal dari jumlah
sumber/media yang membahas cerita yang sama.

JANGAN menganggap angka coverage sebagai
jumlah views atau traffic media sosial.

==================================================
PENTING
==================================================

- Jangan melakukan research internet.
- Jangan mengarang fakta.
- Jangan menganggap film sebagai kejadian nyata.
- Jangan memberi skor tinggi hanya karena
  judul terlihat horror.
- Prioritaskan story potential.
- Prioritaskan content quality.
- Pilih topik yang benar-benar bisa dibuat
  menjadi video horror menarik.
- Pilih tepat 10 kandidat terbaik jika tersedia
  minimal 10 kandidat.
- Jika kandidat kurang dari 10, pilih semua
  kandidat yang layak.
- Jangan memasukkan kandidat dengan kualitas
  sangat rendah hanya untuk memenuhi jumlah 10.

==================================================
PERHITUNGAN
==================================================

overall_score =
(source_coverage * 0.40)
+
(search_relevance * 0.30)
+
(recency * 0.20)
+
(source_quality * 0.10)

Kemudian terapkan Content Quality Gate:

Jika content_quality < 50:
overall_score maksimal 49.

Jika content_quality < 60:
overall_score maksimal 59.

==================================================
KANDIDAT
==================================================

{json.dumps(
    candidates,
    ensure_ascii=False,
    indent=2
)}

==================================================
OUTPUT
==================================================

Balas HANYA JSON valid.

Format:

{{
    "top_10": [
        {{
            "id": 1,
            "source_coverage": 0,
            "search_relevance": 0,
            "recency": 0,
            "source_quality": 0,
            "horror_strength": 0,
            "story_potential": 0,
            "content_quality": 0,
            "overall_score": 0,
            "reason": "alasan singkat"
        }}
    ]
}}
"""

    print(
        "\n🧠 AI sedang melakukan "
        "FINAL SCORING + QUALITY GATE..."
    )

    response = client.responses.create(
        model="gpt-5.6",
        input=prompt
    )

    result = json.loads(
        response.output_text
    )

    return result