-- 자동 백업 이메일 설정 테이블
CREATE TABLE IF NOT EXISTS shalenu_backup_settings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    church_id UUID NOT NULL REFERENCES shalenu_churches(id) ON DELETE CASCADE,
    is_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    frequency TEXT NOT NULL DEFAULT 'monthly', -- weekly / monthly
    send_to_email TEXT NOT NULL,
    last_backup_at TIMESTAMPTZ,
    next_backup_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (church_id)
);
