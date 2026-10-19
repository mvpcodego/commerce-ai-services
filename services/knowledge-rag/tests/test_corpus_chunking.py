import itertools

from rag.chunking import chunk_doc, split_sentences
from rag.corpus import Doc, build_corpus


def test_corpus_is_deterministic_and_sized(corpus):
    again = build_corpus()
    assert [d.doc_id for d in corpus] == [d.doc_id for d in again]
    assert [d.text for d in corpus] == [d.text for d in again]
    assert 60 <= len(corpus) <= 120
    assert len({d.doc_id for d in corpus}) == len(corpus)
    faq = [d for d in corpus if d.doc_type == "faq"]
    assert 10 <= len(faq) <= 15


def test_car_docs_carry_make_and_model(corpus):
    rio = next(d for d in corpus if d.doc_id == "car-kia-rio")
    assert (rio.make, rio.model) == ("Kia", "Rio")
    assert "рамка" in rio.text and "Комплект «Kia Rio +" in rio.text
    assert all(d.make is None for d in corpus if d.doc_type != "car")


def test_split_sentences_keeps_decimals():
    assert split_sentences('Экран 10.1" дюйма. Цена 3 500 ₽. «Набор» есть.') == [
        'Экран 10.1" дюйма.',
        "Цена 3 500 ₽.",
        "«Набор» есть.",
    ]


def _doc(n: int) -> Doc:
    return Doc("d1", "faq", "Заголовок", " ".join(f"Предложение номер {i} про магнитолу." for i in range(n)))


def test_short_doc_is_one_chunk():
    chunks = chunk_doc(_doc(2), max_chars=500)
    assert len(chunks) == 1 and chunks[0].chunk_id == "d1#0"
    assert chunks[0].content.startswith("Заголовок. ")


def test_chunks_respect_size_and_overlap():
    chunks = chunk_doc(_doc(20), max_chars=120, overlap=1)
    assert len(chunks) > 3
    assert all(len(c.text) <= 120 for c in chunks)
    for a, b in itertools.pairwise(chunks):
        last = split_sentences(a.text)[-1]
        assert split_sentences(b.text)[0] == last  # перекрытие в одно предложение
    # все предложения документа покрыты
    covered = {s for c in chunks for s in split_sentences(c.text)}
    assert covered == set(split_sentences(_doc(20).text))


def test_no_overlap_means_disjoint_chunks():
    chunks = chunk_doc(_doc(20), max_chars=120, overlap=0)
    sents = [s for c in chunks for s in split_sentences(c.text)]
    assert sents == split_sentences(_doc(20).text)


def test_long_sentence_still_emitted():
    doc = Doc("d2", "faq", "T", "Очень " * 100 + "длинное предложение. Короткое.")
    chunks = chunk_doc(doc, max_chars=50)
    assert len(chunks) == 2 and chunks[0].text.startswith("Очень")
