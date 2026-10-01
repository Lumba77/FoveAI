r"""
build_martinus_dataset.py
=========================
Build a JSONL dataset from Martinus material (PDF text + web content)
for the Mind Matter Extractor to process.

Sources:
  - introductory_book.pdf (88 pages, extracted to .txt)
  - Web content from third-testament.info (book descriptions, science of all-love)
"""
import json
import re
from pathlib import Path

MARTINUS_DIR = Path(r"C:\Users\danie\program\LUMAX\Training\data\martinus")
OUTPUT = MARTINUS_DIR / "martinus_dataset.jsonl"

# Web content fetched from third-testament.info
WEB_CONTENT = [
    {
        "title": "The Science of All-Love",
        "text": """The world's greatest religious command: Love your God above all things and your neighbour as yourself. The cosmic analyses show that the core in the revealed great cosmic conclusions or religious dogmas of the past is the absolute truth.

The world situation today is the condition of Armageddon. The devil shall rage in all his power. We have seen World Wars, attempts to wipe out populous towns, annihilation of races, millions murdered in concentration camps. Where is the belief in a loving God and practical Christian culture in this Doomsday existence?

Human beings grow out of religious dogmas, almost as children grow out of clothes and shoes. Millions have become materialists and atheists. The highest life-conditional cosmic truths have become a mystery. The religious ideals were perfectly adapted to the stages of evolution of those human beings to whom they were given, but a great part of humanity has outgrown these stages.

Today great masses have lost the faculty to believe because their instinct has degenerated through the development of intelligence. They have gained the faculty to analyse, research and observe. They demand logical arguments or scientific substantiation. The Book of Symbols and the Chief Work have been produced to help those who cannot believe in bare assertions without intellectual substantiation, but who with heart and intellect search for the justification of the condition of existence behind daily life's primitiveness.

Cosmic study opens a road to life's own over-all justification of the darkness in the world as a link in the creation of the eternal maintenance of the key-note of the universe: Love.""",
    },
    {
        "title": "Livets Bog - The Book of Life",
        "text": """The Third Testament provides an explanation of life's own religion. We all already exist as members of this religion, bad as well as good, believers as well as non-believers, animals and plants included. Everyone has vital roles to play in the gigantic theatrical performances taking place in nature, which we call the universe. The universe is alive, likened to a book - the book of life that everyone is reading every single moment.

Livets Bog 1: The world situation. The divine creative principle. The new world impulse. An international world kingdom under creation. Terrestrial mankind's receptivity to the new world impulse. From animal to human being. The basic energies and the planes of existence. Evolution.

Livets Bog 2 - Cosmic Chemistry: Our thought world, mentality or soul. Our fate is exclusively the result of how we use the forces of our consciousness. To think and act perfectly we must know the laws governing thought. With this knowledge it becomes possible to create a perfect fate and a perfect world.

Livets Bog 3 - Life Substances: The basic principles of eternal life are catalogued. The logical structure of the number system compared to the eternal basic structure of the universe.

Livets Bog 4 - Eternal Life: The living being. God is revealed in the living being and vice versa. The unity of eternity and time. Spiritual worlds. The purpose of the physical world. Politics and religion. Criminal law and Christianity. Democracy, dictatorship, and the united states of the world.

Livets Bog 5 - The Highest Fire: Sexuality in all its forms. The organic structure of neighbourly love. The transformation of sexuality. The creation of Man in God's image. From animal to Man.

Livets Bog 6 - The Kingdom of God: The inner psychic temple. Meditation, cosmic glimpses, the principle of prayer. The experience of being one with God. God's consciousness; The Holy Spirit. The Father and the son, the creators of time and space.

Livets Bog 7 - Cosmic World Morality: The foundation of the new world civilisation. The purpose of the world government. An economic system without money. The abolition of punishment. Cosmic science and the limitations of materialistic science. All living beings will become active cells in God's consciousness.""",
    },
    {
        "title": "The Eternal World Picture",
        "text": """The cosmic symbols are gathered in 6 volumes. With the help of the symbols the reader can easily form an overview of the eternal world picture.

Symbol 1: The Spirit of God upon the Face of the Waters
Symbol 2: The Principle of World Redemption
Symbol 3: Intolerance
Symbol 4: The Road towards Light
Symbol 5: Cosmic Unconsciousness
Symbol 6: The Living Being
Symbol 7: The Principle of Life Units
Symbol 8: The Divine Something, X1
Symbol 9: The Living Being's Creative Power, X2
Symbol 10: Creation, X3
Symbol 11: The Eternal World Picture, the Living Being, The Eternal Godhead and the Eternal Sons of God
Symbol 12: The Combination of the Basic Energies
Symbol 13: The Eternal World Plan
Symbol 14: The Cosmic Spiral Cycle
Symbol 15: The Law of Movement
Symbol 16: The Eternal Body

The symbols present the main principles of the world picture: the divine creative principle, the combination of basic energies, the eternal world plan, the cosmic spiral cycle, the law of movement, and the eternal body. Love is the keynote of the universe. Through contact with love, the human being is liberated from the primitive state of hatred and dark consciousness and elevated to the accomplishment of God's plan - the creation of the human being in the image of God.""",
    },
    {
        "title": "Logic - Introduction to The Third Testament",
        "text": """Love and logic is one and the same thing. Materialistic science and the mystery of life. An illogical view of the world. The Bible contains conclusive answers about eternity, in a form that can be understood by those with less critical faculties but also by those with wisdom.

The Biblical account of creation is explained. Reincarnation. The way out of the animal kingdom. The perfect Man at one with God. Eternal life and the understanding of light and darkness. God's elevated view of the world: Everything is very good.

Logic is intended as an introduction to The Third Testament. It shows that love and logic are not opposed but are the same thing seen from different angles. True logic leads to love, and true love is logical.""",
    },
    {
        "title": "Intellectualised Christianity",
        "text": """The Third Testament is the intellectualised Christianity. It underlines the connections between the Old Testament, the New Testament and the Third Testament. The core message of love and tolerance of Christianity is unified with a modern scientific attitude.

Mankind is ready for an intellectualised Christianity. Its foundation stone is a message of love that transcends traditional philosophical and religious divisions and contains thoughts about reincarnation, eternal life and the evolution of all living beings.

Martinus saw his work as spiritual science - providing people with a new, analytical and logical framework for understanding existence. Not blind faith, but logical understanding of the cosmic laws that govern life.""",
    },
    {
        "title": "Martinus Cosmology Core Principles",
        "text": """1. The universe is alive - everything is living beings, from atoms to galaxies.
2. Reincarnation - all living beings evolve through repeated physical lives.
3. The law of cause and effect (karma) - our fate is the result of how we use the forces of consciousness.
4. The basic energies - the universe is governed by basic energies that combine in different ways.
5. Evolution from animal to human to divine - all beings are on an eternal journey of evolution.
6. Love is the keynote of the universe - the cosmic goal is the creation of the human being in God's image.
7. The unity of love and logic - true logic leads to love, true love is logical.
8. Cosmic consciousness - a permanent state of awake day-consciousness of all spiritual forces and causes behind the physical world.
9. The eternal world picture - physical reality is a manifestation of eternal cosmic principles.
10. Suffering has a purpose - it is a consequence of violating cosmic laws, and drives evolution towards love.
11. All religions contain the same core truth - expressed in different forms for different stages of evolution.
12. The microcosmos and macrocosmos mirror each other - as above, so below.
13. Thought is creative - our thoughts shape our fate and our future.
14. The principle of life units - every being is a life unit within a larger life unit, infinitely.
15. God is the totality of all consciousness - the I AM THAT I AM of all existence.""",
    },
]


def split_text_to_chunks(text: str, max_chars: int = 800) -> list[str]:
    """Split text into chunks at paragraph boundaries."""
    paragraphs = re.split(r"\n\n+", text.strip())
    chunks = []
    current = ""
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        if len(current) + len(para) + 2 > max_chars and current:
            chunks.append(current.strip())
            current = para
        else:
            current = current + "\n\n" + para if current else para
    if current.strip():
        chunks.append(current.strip())
    return chunks


def main():
    rows = []

    # 1. Process PDF text
    pdf_txt = MARTINUS_DIR / "introductory_book.txt"
    if pdf_txt.exists():
        with open(pdf_txt, "r", encoding="utf-8") as f:
            full_text = f.read()
        # Split on page breaks and clean up
        pages = full_text.split("--- PAGE BREAK ---")
        for page_text in pages:
            page_text = page_text.strip()
            if len(page_text) < 50:
                continue
            chunks = split_text_to_chunks(page_text, max_chars=1000)
            for chunk in chunks:
                if len(chunk) < 80:
                    continue
                rows.append({
                    "instruction": "Extract the cosmological principle from this passage of Martinus's Third Testament.",
                    "output": chunk,
                    "source": "introductory_book.pdf",
                })

    # 2. Process web content
    for item in WEB_CONTENT:
        chunks = split_text_to_chunks(item["text"], max_chars=800)
        for chunk in chunks:
            rows.append({
                "instruction": f"Extract the key principle from: {item['title']}",
                "output": chunk,
                "source": f"web:{item['title']}",
            })

    # Write JSONL
    with open(OUTPUT, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    print(f"✅ Martinus dataset: {OUTPUT}")
    print(f"   {len(rows)} rows")
    print(f"   Sources: introductory_book.pdf ({sum(1 for r in rows if 'pdf' in r['source'])} rows)")
    print(f"            web content ({sum(1 for r in rows if 'web' in r['source'])} rows)")


if __name__ == "__main__":
    main()
