-- Demo operators and default validation rules for the OCR desk.
-- Safe to re-run: existing rows are left unchanged.

insert into users (id, username, full_name, role, created_at)
values
    ('usr_admin', 'admin', 'System Administrator', 'admin', now()),
    ('usr_supervisor', 'supervisor', 'Election Supervisor (Jane Smith)', 'supervisor', now()),
    ('usr_operator', 'operator', 'Data Capture Operator (John Doe)', 'operator', now()),
    ('usr_auditor', 'auditor', 'Independent Electoral Auditor', 'auditor', now())
on conflict (id) do nothing;

insert into validation_rules (
    id, rule_code, name, description, rule_type, is_active, severity, config_json
) values
    (
        'rule_sum_party_votes',
        'SUM_PARTY_VOTES_MATCH',
        'Party Votes Sum Reconciliation',
        'Validates that the sum of votes for all individual candidates/parties strictly equals the Total Valid Votes Cast.',
        'math',
        true,
        'error',
        '{"tolerance": 0}'::jsonb
    ),
    (
        'rule_reconciliation',
        'RECONCILIATION_MATCH',
        'Total Votes Cast Reconciliation',
        'Validates that Total Valid Votes Cast + Total Spoilt Ballots strictly equals Total Votes Cast.',
        'math',
        true,
        'error',
        '{}'::jsonb
    ),
    (
        'rule_turnout_ceiling',
        'TURNOUT_CEILING',
        'Voter Turnout Ceiling Check',
        'Validates that Total Votes Cast and the party-vote sum do not exceed Registered Voters (flags error if >100%, warning if unusually high >90%).',
        'threshold',
        true,
        'error',
        '{"warning_threshold_pct": 90.0, "max_threshold_pct": 100.0}'::jsonb
    ),
    (
        'rule_votes_within_registered',
        'VOTES_WITHIN_REGISTERED',
        'Votes Within Registered Voters',
        'Fails when the sum of party votes or Total Votes Cast is greater than Registered Voters on the slip.',
        'threshold',
        true,
        'error',
        '{}'::jsonb
    ),
    (
        'rule_all_pages_present',
        'ALL_PAGES_PRESENT',
        'Complete Multi-Page Set Requirement',
        'Enforces that all pages (Page X of Y) for a logical slip are uploaded, verified, and linked prior to approval.',
        'multi_page',
        true,
        'error',
        '{}'::jsonb
    ),
    (
        'rule_officer_signature',
        'OFFICER_SIGNATURE_PRESENT',
        'Presiding Officer Signature Verification',
        'Checks for the presence of the presiding officer''s handwritten signature on the final page.',
        'compliance',
        true,
        'warning',
        '{"require_on_final_page": true}'::jsonb
    ),
    (
        'rule_duplicate_vd',
        'DUPLICATE_VD_BALLOT',
        'Duplicate Slip Protection',
        'Ensures no other approved ballot result slip exists with the same Voting District and Ballot Type.',
        'uniqueness',
        true,
        'error',
        '{}'::jsonb
    ),
    (
        'rule_party_signatures',
        'PARTY_SIGNATURE_CONSISTENCY',
        'Party Agent Signatures on Non-Zero Rows',
        'Recommends that party agent signatures are present on rows where party votes are recorded.',
        'compliance',
        true,
        'warning',
        '{}'::jsonb
    )
on conflict (id) do update set
    rule_code = excluded.rule_code,
    name = excluded.name,
    description = excluded.description,
    rule_type = excluded.rule_type,
    is_active = excluded.is_active,
    severity = excluded.severity,
    config_json = excluded.config_json;
