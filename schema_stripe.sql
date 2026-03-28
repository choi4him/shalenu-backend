-- ============================================================
-- J-SheepFold Stripe 온라인 헌금 스키마
-- Supabase SQL Editor에서 실행
-- ============================================================
-- 사전 준비: .env에 아래 키 추가 필요
--   STRIPE_SECRET_KEY=sk_live_...   (또는 sk_test_... 테스트용)
--   STRIPE_WEBHOOK_SECRET=whsec_...
-- ============================================================

-- 1. 결제 링크 (Payment Links)
CREATE TABLE shalenu_payment_links (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    church_id UUID NOT NULL REFERENCES shalenu_churches(id) ON DELETE CASCADE,
    title VARCHAR(200) NOT NULL,
    description TEXT,
    amount INT,                           -- 센트 단위 (NULL이면 기부자 자유 입력)
    currency VARCHAR(3) NOT NULL DEFAULT 'usd',
    stripe_price_id VARCHAR(200),         -- Stripe Price ID
    stripe_link_id VARCHAR(200),          -- Stripe PaymentLink ID
    stripe_link_url TEXT,                 -- 공유 가능한 결제 URL
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_by UUID REFERENCES shalenu_users(id),
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- 2. 온라인 헌금 내역 (Online Payments)
CREATE TABLE shalenu_online_payments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    church_id UUID NOT NULL REFERENCES shalenu_churches(id) ON DELETE CASCADE,
    payment_link_id UUID REFERENCES shalenu_payment_links(id) ON DELETE SET NULL,
    stripe_session_id VARCHAR(200) UNIQUE, -- Checkout Session ID (중복 방지)
    donor_name VARCHAR(100),
    donor_email VARCHAR(200),
    amount INT NOT NULL,                   -- 센트 단위
    currency VARCHAR(3) NOT NULL DEFAULT 'usd',
    status VARCHAR(20) NOT NULL DEFAULT 'pending', -- pending | completed | failed | refunded
    paid_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- ── 인덱스 ────────────────────────────────────────────
CREATE INDEX idx_payment_links_church ON shalenu_payment_links(church_id);
CREATE INDEX idx_payment_links_church_active ON shalenu_payment_links(church_id, is_active);
CREATE INDEX idx_online_payments_church ON shalenu_online_payments(church_id);
CREATE INDEX idx_online_payments_link ON shalenu_online_payments(payment_link_id);
CREATE INDEX idx_online_payments_church_status ON shalenu_online_payments(church_id, status);

-- ── RLS 활성화 ─────────────────────────────────────────
ALTER TABLE shalenu_payment_links ENABLE ROW LEVEL SECURITY;
ALTER TABLE shalenu_online_payments ENABLE ROW LEVEL SECURITY;

-- ── RLS 정책 ───────────────────────────────────────────
CREATE POLICY "payment_links_service_all" ON shalenu_payment_links
  FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "payment_links_auth_all" ON shalenu_payment_links
  FOR ALL TO authenticated USING (true) WITH CHECK (true);

CREATE POLICY "online_payments_service_all" ON shalenu_online_payments
  FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "online_payments_auth_all" ON shalenu_online_payments
  FOR ALL TO authenticated USING (true) WITH CHECK (true);
