-- Схема базы знаний. Расширение vector ставится в public, таблицы — в текущую схему (search_path).
create extension if not exists vector with schema public;

create table if not exists documents (
    doc_id   text primary key,
    doc_type text not null,
    title    text not null,
    body     text not null,
    make     text,
    model    text
);

create table if not exists chunks (
    chunk_id  text primary key,
    doc_id    text not null references documents (doc_id) on delete cascade,
    ord       int  not null,
    title     text not null,          -- заголовок документа
    content   text not null,          -- заголовок + текст чанка (вход эмбеддера)
    text      text not null,          -- только текст чанка (для цитирования)
    doc_type  text not null,          -- метаданные продублированы для фильтра без join
    make      text,
    model     text,
    embedding vector(384) not null,
    -- Заголовок весит больше текста (A против B): вопрос «Vertek V3 10.1» должен поднимать карточку
    -- магнитолы выше карточек машин, где тот же артикул упомянут в списке комплектов.
    tsv       tsvector generated always as (
        setweight(to_tsvector('russian', title), 'A') || setweight(to_tsvector('russian', text), 'B')
    ) stored
);

create index if not exists chunks_embedding_hnsw on chunks using hnsw (embedding vector_cosine_ops);
create index if not exists chunks_tsv_gin on chunks using gin (tsv);
create index if not exists chunks_make_model on chunks (lower(make), lower(model));

-- Каким эмбеддером построен индекс: вопрос нужно кодировать той же моделью.
create table if not exists kb_meta (
    key   text primary key,
    value text not null
);
