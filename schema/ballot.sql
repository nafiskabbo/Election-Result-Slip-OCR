-- =============================================================================
-- Election Result Slip OCR Platform
-- PostgreSQL 16+ schema
--
-- Apply on a new database:
--   psql -U ballot -d ballot -v ON_ERROR_STOP=1 -f schema/ballot.sql
--
-- Backup:
--   pg_dump -U ballot -d ballot --no-owner --format=plain  > ballot-YYYYMMDD.sql
--   pg_dump -U ballot -d ballot --format=custom            > ballot-YYYYMMDD.dump
--
-- Restore:
--   psql -U ballot -d ballot -v ON_ERROR_STOP=1 -f ballot-YYYYMMDD.sql
--   pg_restore --no-owner --role=ballot -d ballot ballot-YYYYMMDD.dump
-- =============================================================================

create table if not exists users (
    id text primary key,
    username text not null,
    full_name text not null,
    role text not null,
    created_at timestamptz not null default now(),
    constraint users_username_key unique (username),
    constraint users_role_check check (role in ('admin', 'supervisor', 'operator', 'auditor'))
);

comment on table users is 'Desk operators and reviewers. Authentication is role-based in the application.';
comment on column users.role is 'admin | supervisor | operator | auditor';

create table if not exists slips (
    id text primary key,
    slip_reference text not null,
    ballot_type text not null,
    election_name text not null,
    province text,
    municipality text,
    voting_district text not null,
    station_name text,
    registered_voters integer not null default 0,
    status text not null,
    presiding_officer_name text,
    presiding_officer_signature_detected boolean not null default false,
    total_valid_votes integer not null default 0,
    total_spoilt_votes integer not null default 0,
    total_votes_cast integer not null default 0,
    special_votes integer not null default 0,
    section_24a_votes integer not null default 0,
    total_expected_pages integer not null default 1,
    total_received_pages integer not null default 1,
    is_vote_related boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    approved_at timestamptz,
    approved_by text,
    rejection_reason text,
    constraint slips_status_check check (
        status in ('incomplete', 'pending_review', 'approved', 'rejected', 'flagged')
    ),
    constraint slips_registered_voters_check check (registered_voters >= 0),
    constraint slips_vote_counts_check check (
        total_valid_votes >= 0
        and total_spoilt_votes >= 0
        and total_votes_cast >= 0
        and special_votes >= 0
        and section_24a_votes >= 0
    ),
    constraint slips_page_counts_check check (
        total_expected_pages >= 1
        and total_received_pages >= 0
    ),
    constraint slips_approved_by_fkey foreign key (approved_by) references users (id)
);

comment on table slips is 'One logical result slip, possibly spanning several photographed pages.';
comment on column slips.slip_reference is 'Grouping key, typically barcode prefix + voting district + ballot type.';
comment on column slips.status is 'incomplete | pending_review | approved | rejected | flagged';
comment on column slips.voting_district is 'IEC voting district (VD) number.';

alter table slips add column if not exists is_vote_related boolean not null default true;
comment on column slips.is_vote_related is 'False when the upload is not an IEC result slip; vote tables must not be shown.';

alter table slips add column if not exists processing_started_at timestamptz;
alter table slips add column if not exists processing_ended_at timestamptz;
comment on column slips.processing_started_at is 'When OCR processing of this slip first started.';
comment on column slips.processing_ended_at is 'When OCR processing of this slip last finished.';

create table if not exists slip_pages (
    id text primary key,
    slip_id text not null,
    page_number integer not null,
    page_total integer not null,
    barcode_text text,
    raw_file_path text not null,
    enhanced_file_path text not null,
    thumbnail_path text,
    status text not null,
    upload_timestamp timestamptz not null default now(),
    file_size bigint not null,
    mime_type text not null,
    exception_flags jsonb,
    constraint slip_pages_page_number_check check (page_number >= 1),
    constraint slip_pages_page_total_check check (page_total >= 1),
    constraint slip_pages_file_size_check check (file_size >= 0),
    constraint slip_pages_slip_id_fkey foreign key (slip_id) references slips (id) on delete cascade
);

comment on table slip_pages is 'One uploaded image or PDF page belonging to a slip. Files live on disk; this table stores paths.';
comment on column slip_pages.exception_flags is 'JSON array of capture warnings, for example low-confidence digits.';

create table if not exists party_results (
    id text primary key,
    slip_id text not null,
    page_id text not null,
    row_index integer not null,
    party_name text not null,
    party_code text not null,
    votes integer not null default 0,
    confidence_score double precision not null default 1.0,
    is_overridden boolean not null default false,
    overridden_by text,
    original_ocr_votes integer not null default 0,
    signature_detected boolean not null default false,
    bbox_json jsonb,
    constraint party_results_row_index_check check (row_index >= 0),
    constraint party_results_votes_check check (votes >= 0 and original_ocr_votes >= 0),
    constraint party_results_confidence_check check (confidence_score >= 0),
    constraint party_results_slip_id_fkey foreign key (slip_id) references slips (id) on delete cascade,
    constraint party_results_page_id_fkey foreign key (page_id) references slip_pages (id) on delete cascade
);

comment on table party_results is 'One party or candidate row extracted from a slip page. original_ocr_votes is kept after operator override.';

create table if not exists audit_logs (
    id text primary key,
    slip_id text,
    page_id text,
    user_id text not null,
    action text not null,
    field_name text,
    old_value text,
    new_value text,
    reason text,
    ip_address text,
    timestamp timestamptz not null default now(),
    constraint audit_logs_slip_id_fkey foreign key (slip_id) references slips (id) on delete set null,
    constraint audit_logs_page_id_fkey foreign key (page_id) references slip_pages (id) on delete set null,
    constraint audit_logs_user_id_fkey foreign key (user_id) references users (id)
);

comment on table audit_logs is 'Immutable change history. Rows are inserted, never updated.';

create table if not exists validation_rules (
    id text primary key,
    rule_code text not null,
    name text not null,
    description text not null,
    rule_type text not null,
    is_active boolean not null default true,
    severity text not null,
    config_json jsonb not null default '{}'::jsonb,
    constraint validation_rules_rule_code_key unique (rule_code),
    constraint validation_rules_severity_check check (severity in ('error', 'warning'))
);

comment on table validation_rules is 'Configurable checks run before approval (totals, turnout, duplicates, completeness).';

create table if not exists validation_results (
    id text primary key,
    slip_id text not null,
    rule_code text not null,
    status text not null,
    message text not null,
    evaluated_at timestamptz not null default now(),
    constraint validation_results_status_check check (status in ('pass', 'fail', 'warn')),
    constraint validation_results_slip_id_fkey foreign key (slip_id) references slips (id) on delete cascade,
    constraint validation_results_rule_code_fkey foreign key (rule_code) references validation_rules (rule_code)
);

comment on table validation_results is 'Latest evaluation of each rule against a slip. Replaced when validation is re-run.';

create index if not exists slips_slip_reference_idx on slips (slip_reference);
create index if not exists slips_voting_district_ballot_type_idx on slips (voting_district, ballot_type);
create index if not exists slips_status_updated_at_idx on slips (status, updated_at desc);
create index if not exists slips_approved_vd_type_idx
    on slips (voting_district, ballot_type)
    where status = 'approved';
create index if not exists slips_approved_by_idx on slips (approved_by);

create index if not exists slip_pages_slip_id_idx on slip_pages (slip_id);

create index if not exists party_results_slip_id_idx on party_results (slip_id);
create index if not exists party_results_page_id_idx on party_results (page_id);

create index if not exists audit_logs_slip_id_idx on audit_logs (slip_id);
create index if not exists audit_logs_page_id_idx on audit_logs (page_id);
create index if not exists audit_logs_user_id_idx on audit_logs (user_id);
create index if not exists audit_logs_timestamp_idx on audit_logs (timestamp desc);

create index if not exists validation_results_slip_id_idx on validation_results (slip_id);
create index if not exists validation_results_rule_code_idx on validation_results (rule_code);
