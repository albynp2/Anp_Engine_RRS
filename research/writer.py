from openai import OpenAI
from dotenv import load_dotenv

import os
import json


load_dotenv()


client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY")
)


def generate_story(story):

    prompt = f"""
Kamu adalah penulis konten horror profesional untuk
YouTube Shorts dan Facebook Reels Indonesia.

Kamu akan membuat cerita ORIGINAL berdasarkan
HASIL RESEARCH yang diberikan.

==================================================
SUMBER RESEARCH
==================================================

Judul:
{story["title"]}

Source:
{story["source"]}

Tanggal:
{story["published"]}

URL:
{story["url"]}

==================================================
ATURAN PALING PENTING
==================================================

1. JANGAN mengarang kejadian faktual baru.

2. Jangan menambahkan detail spesifik yang tidak
   terdapat dalam sumber research.

Contoh detail yang DILARANG dibuat sendiri:

- ada bayangan di kamera
- ada suara tertentu
- ada sosok berdiri di lorong
- kamera merekam sesuatu
- pemain melihat makhluk
- kru menemukan mayat
- pintu terbuka sendiri
- lampu mati sendiri
- seseorang kesurupan

Kecuali detail tersebut memang disebutkan
dalam informasi sumber.

3. Jangan mengubah dugaan menjadi fakta.

Jika sumber menggunakan bahasa seperti:
"diduga", "disebut", "dikabarkan",
"menurut cerita", "konon", atau "pengalaman",

pertahankan sifat tidak pastinya.

4. Jika informasi sumber sangat terbatas,
JANGAN mengisi kekosongan dengan fakta baru.

Gunakan storytelling yang bersifat naratif,
bukan klaim kejadian nyata.

Contoh:

AMAN:
"Bayangkan suasana motel tua itu pada malam hari."

TIDAK AMAN:
"Malam itu terdengar suara langkah dari lantai tiga."

Kalimat kedua hanya boleh digunakan jika
sumber memang menyebut suara tersebut.

5. Boleh membuat suasana, analogi, transisi,
dan deskripsi emosional selama tidak menyatakan
hal tersebut sebagai kejadian nyata.

6. Jangan melakukan research internet tambahan.

7. Jangan menyalin kalimat dari artikel.

8. Jangan membuat cerita seolah-olah semua
kejadian supernatural telah terbukti.

9. Jika sumber berasal dari film, acara TV,
atau proses produksi film, jangan menjadikan
film tersebut sebagai bukti bahwa kejadian
supernatural benar-benar terjadi.

10. Prioritaskan informasi kejadian mistis,
pengalaman orang, lokasi, atau misteri yang
memang disebutkan dalam sumber.

==================================================
GAYA NARASI
==================================================

- Bahasa Indonesia natural.
- Cocok untuk voice TTS.
- Kalimat pendek sampai sedang.
- Tidak terlalu formal.
- Mencekam tetapi tidak berlebihan.
- Hook harus menarik dalam 3-5 detik.
- Target script sekitar 150-220 kata.
- Jangan menggunakan emoji dalam script.

==================================================
STRUKTUR
==================================================

1. TITLE

Judul pendek, menarik, dan tidak clickbait
yang mengubah dugaan menjadi fakta.

2. HOOK

1-2 kalimat pertama yang membuat penasaran.

3. SCRIPT

Narasi sekitar 150-220 kata.

Gunakan informasi dari sumber sebagai fondasi.

Jika informasi faktual terbatas, gunakan
storytelling atmosferik untuk menghubungkan
informasi tersebut tanpa menciptakan kejadian baru.

4. ENDING

Akhiri dengan:

- pertanyaan misterius,
- kemungkinan yang belum terjawab,
- atau kalimat yang mengundang komentar.

Jangan menyimpulkan bahwa kejadian supernatural
tersebut pasti benar.

5. CAPTION

Pendek dan menarik untuk Facebook Reels /
YouTube Shorts.

6. HASHTAGS

5-8 hashtag relevan.

==================================================
SOURCE BASIS
==================================================

Tambahkan field:

"source_basis"

Isi dengan ringkasan singkat mengenai
informasi utama yang benar-benar digunakan
dari sumber.

Contoh:

"Artikel membahas pengalaman mistis kru
saat proses syuting film horor."

Jangan memasukkan fakta yang tidak ada
dalam sumber.

==================================================
STORY TYPE
==================================================

Tambahkan field:

"story_type"

Pilih salah satu:

"reported_mystery"
"reported_horror"
"urban_legend"
"entertainment_horror"
"unclear"

==================================================
FACT BOUNDARY
==================================================

Tambahkan field:

"fact_boundary"

Jelaskan secara singkat batas antara
informasi yang berasal dari sumber dan
bagian storytelling.

Contoh:

"Peristiwa mistis berasal dari laporan sumber,
sedangkan deskripsi suasana digunakan sebagai
narasi dan bukan klaim kejadian faktual."

==================================================
OUTPUT
==================================================

Balas HANYA JSON valid.

Format:

{{
    "title": "",
    "hook": "",
    "script": "",
    "ending": "",
    "caption": "",
    "hashtags": [],
    "source_basis": "",
    "story_type": "",
    "fact_boundary": ""
}}
"""

    print(
        "\n✍️ AI sedang menulis cerita..."
    )

    response = client.responses.create(
        model="gpt-5.6",
        input=prompt
    )

    result = json.loads(
        response.output_text
    )

    return result