from openai import OpenAI
from dotenv import load_dotenv

import os
import json


load_dotenv()


client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY")
)


def score_stories(topics, mode="horror", custom_query=""):

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

    if mode == "custom":
        prompt_intro = f"""
Kamu adalah Content Researcher sekaligus Trend Researcher.

MODE: CUSTOM QUERY
QUERY USER: {custom_query}

Tujuan utama mode ini adalah menemukan berita/topik yang
SEDANG BERKEMBANG, RAMAI DIBERITAKAN, DAN RELEVAN dengan
query user.

Jangan memaksakan topik menjadi cerita horror/misteri.
Query user adalah konteks utama. Topik politik, kriminal,
teknologi, tokoh publik, peristiwa nasional, atau kategori
lain harus dinilai sesuai query-nya.

Yang lebih penting:
- recency
- jumlah sumber yang membahas cerita/topik yang sama
- relevansi terhadap query
- kualitas sumber
- perkembangan terbaru

Story potential tetap dinilai, tetapi hanya sebagai sinyal
sekunder. Jangan menurunkan topik hanya karena tidak punya
narasi pengalaman panjang.

"""
    else:
        prompt_intro = """
Kamu adalah Content Researcher sekaligus
Content Quality Gate untuk channel
cerita horror / misteri Indonesia.

MODE: HORROR / MYSTERY

Tujuan utama mode ini adalah menemukan BAHAN CERITA
yang kuat untuk dijadikan video narasi 60-90 detik.

Story potential, curiosity, horror/mystery strength,
content quality, dan detail kejadian lebih penting daripada
jumlah media yang meliput.

"""

    prompt = f"""
{prompt_intro}

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
PRINSIP PENILAIAN SESUAI MODE
==================================================

HORROR / MYSTERY:
Nilai utama adalah kekuatan cerita:
- story_potential
- curiosity
- horror_strength
- content_quality
- uniqueness
- detail kejadian
Coverage dan recency tetap dipakai, tetapi bukan tujuan utama.

CUSTOM QUERY:
Nilai utama adalah kekuatan tren/topik:
- source_coverage
- recency
- search_relevance
- source_quality
- perkembangan berita terbaru
Story potential hanya sinyal sekunder.

Jangan menerapkan quality gate horror/mystery
kepada Custom Query.

==================================================
QUALITY GATE HORROR / MYSTERY
==================================================

Hanya untuk MODE HORROR / MYSTERY, periksa:

1. APAKAH ADA PERISTIWA / MISTERI YANG BISA DICERITAKAN?
2. APAKAH ADA UNSUR HORROR, MISTIS, MISTERI, ATAU KEANEHAN?
3. APAKAH BISA MENJADI NARASI 60-90 DETIK?
4. APAKAH MEMBUAT PENONTON PENASARAN?
5. APAKAH INFORMASINYA CUKUP UNTUK WRITER?

Jika sebagian besar TIDAK, beri skor rendah walaupun coverage tinggi.

Untuk CUSTOM QUERY, jangan menurunkan skor hanya karena
artikel tidak memiliki pengalaman pribadi atau narasi panjang.

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

MODE HORROR / MYSTERY:
Story Potential     : 25%
Curiosity           : 20%
Horror Strength     : 15%
Content Quality     : 15%
Uniqueness          : 10%
Recency             : 5%
Source Coverage     : 5%
Source Quality      : 5%

MODE CUSTOM QUERY:
Source Coverage     : 30%
Recency              : 25%
Search Relevance     : 25%
Source Quality       : 10%
Story Potential      : 5%
Uniqueness           : 5%

CATATAN:
Bobot Custom Query menekankan TREND SIGNAL.
Coverage berarti jumlah sumber/media yang membahas
topik yang sama, bukan views atau traffic.

HORROR / MYSTERY QUALITY GATE:
Jika content_quality < 50,
overall_score maksimal 49.

Jika content_quality < 60,
overall_score maksimal 59.

CUSTOM QUERY:
JANGAN menerapkan cap content_quality horror/mystery.
Content quality tetap dinilai sebagai kualitas
informasi yang tersedia.

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
HORROR / MYSTERY:
- Prioritaskan story potential.
- Prioritaskan content quality.
- Pilih topik yang benar-benar bisa dibuat menjadi video horror menarik.

CUSTOM QUERY:
- Prioritaskan tren dan perkembangan terbaru.
- Prioritaskan coverage, recency, query relevance, dan source quality.
- Jangan memaksa topik menjadi cerita horror.
- Story potential hanya menjadi bonus sekunder.
- Pilih tepat 10 kandidat terbaik jika tersedia
  minimal 10 kandidat.
- Jika kandidat kurang dari 10, pilih semua
  kandidat yang layak.
- Jangan memasukkan kandidat dengan kualitas
  sangat rendah hanya untuk memenuhi jumlah 10.

==================================================
PERHITUNGAN
==================================================

Jika MODE = HORROR / MYSTERY:
overall_score =
(story_potential * 0.25)
+
(curiosity * 0.20)
+
(horror_strength * 0.15)
+
(content_quality * 0.15)
+
(uniqueness * 0.10)
+
(recency * 0.05)
+
(source_coverage * 0.05)
+
(source_quality * 0.05)

Kemudian terapkan Content Quality Gate horror.

Jika MODE = CUSTOM QUERY:
overall_score =
(source_coverage * 0.30)
+
(recency * 0.25)
+
(search_relevance * 0.25)
+
(source_quality * 0.10)
+
(story_potential * 0.05)
+
(uniqueness * 0.05)

Jangan menerapkan cap content_quality horror/mystery
pada Custom Query.

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
        f"\n🧠 AI sedang melakukan FINAL SCORING — MODE: {mode.upper()}..."
    )

    response = client.responses.create(
        model="gpt-5.6",
        input=prompt
    )

    result = json.loads(
        response.output_text
    )

    return result