-- OCR 골든셋 플라이휠 — Supabase 스키마 (개발/수동 동기화 전용).
--
-- 적용: Supabase 프로젝트의 SQL Editor 에 붙여 실행(또는 `supabase db push`).
-- 접근: **RLS enable + 정책 미생성(전면 차단)** → anon/authenticated 는 못 읽고 못 쓴다.
--       service_role 키(RLS 우회)로만 접근. 키는 로컬 config.json 의 SUPABASE_SERVICE_ROLE_KEY.
-- 확장(나중): pgvector 유사검색은 golden_samples 에 `embedding vector(N)` 컬럼을 **추가**하는
--       비파괴 방식으로(이 스키마는 안 건드림).

create extension if not exists "pgcrypto";

-- 프롬프트/러너 버전(서명). score_ocr.py 의 prompt_signature 와 동일 12hex.
create table if not exists prompt_versions (
    sig            text primary key,            -- prompt_signature() 12hex
    prompt_sha256  text not null,
    model          text not null,
    runner         text not null,
    schema_version int  not null,
    created_at     timestamptz not null default now()
);

-- 골든 샘플(정답). 크롭 PNG 는 Storage 버킷 'crops' 에 sha256 키로 둔다.
create table if not exists golden_samples (
    sample_id   text primary key,               -- <pdf_stem>__p<i>__c<ci>
    pdf_stem    text not null,
    page_i      int,
    crop_ci     int,
    bbox        jsonb,
    png_sha256  text not null,                  -- Storage crops/<sha256>.png
    golden      jsonb not null,                 -- {header, questions:[...]}
    created_at  timestamptz not null default now(),
    updated_at  timestamptz not null default now()
);

-- 한 번의 채점 런(특정 프롬프트 sig 로 특정 골든셋을 채점한 단위).
create table if not exists ocr_runs (
    id          uuid primary key default gen_random_uuid(),
    sig         text not null references prompt_versions(sig),
    pdf_stem    text not null,
    aggregate   jsonb not null,                 -- aggregate(scores) 결과
    created_at  timestamptz not null default now()
);

-- 런 내 크롭별 점수(CropScore).
create table if not exists scores (
    id          uuid primary key default gen_random_uuid(),
    run_id      uuid not null references ocr_runs(id) on delete cascade,
    sample_id   text not null references golden_samples(sample_id),
    score       jsonb not null,                 -- asdict(CropScore)
    created_at  timestamptz not null default now()
);

create index if not exists scores_run_idx on scores(run_id);
create index if not exists scores_sample_idx on scores(sample_id);
create index if not exists golden_pdf_idx on golden_samples(pdf_stem);

-- RLS enable, 정책은 만들지 않는다 → service_role 외 전면 차단.
alter table prompt_versions enable row level security;
alter table golden_samples  enable row level security;
alter table ocr_runs        enable row level security;
alter table scores          enable row level security;

-- Storage 버킷 'crops' 는 대시보드나 아래 호출로 비공개 생성(이미 있으면 무시):
-- select storage.create_bucket('crops', public => false);
