-- ============================================================
-- Shalenu PortOne 한국 결제 스키마 (ALTER TABLE)
-- ============================================================

-- shalenu_payment_links 에 PortOne 컬럼 추가
ALTER TABLE shalenu_payment_links
    ADD COLUMN IF NOT EXISTS provider VARCHAR(20) NOT NULL DEFAULT 'stripe',
    ADD COLUMN IF NOT EXISTS portone_link_id VARCHAR(200),
    ADD COLUMN IF NOT EXISTS portone_link_url TEXT;

-- shalenu_online_payments 에 PortOne 컬럼 추가
ALTER TABLE shalenu_online_payments
    ADD COLUMN IF NOT EXISTS portone_imp_uid VARCHAR(200) UNIQUE;

-- 인덱스
CREATE INDEX IF NOT EXISTS idx_payment_links_provider ON shalenu_payment_links(church_id, provider);
