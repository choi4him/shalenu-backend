-- ============================================================
-- J-SheepFold Phase 3 데이터베이스 스키마
-- Supabase SQL Editor에서 실행
-- ============================================================

-- 1. 목양 노트 (Pastoral Notes)
CREATE TABLE shalenu_pastoral_notes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    church_id UUID NOT NULL REFERENCES shalenu_churches(id) ON DELETE CASCADE,
    member_id UUID NOT NULL REFERENCES shalenu_members(id) ON DELETE CASCADE,
    author_id UUID NOT NULL REFERENCES shalenu_users(id) ON DELETE CASCADE,
    category VARCHAR(20) NOT NULL DEFAULT 'general', -- visit, counsel, prayer, general
    content TEXT NOT NULL,
    is_private BOOLEAN DEFAULT TRUE,
    visited_at DATE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- 2. 문자/이메일 발송 (Messages)
CREATE TABLE shalenu_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    church_id UUID NOT NULL REFERENCES shalenu_churches(id) ON DELETE CASCADE,
    title VARCHAR(200) NOT NULL,
    content TEXT NOT NULL,
    message_type VARCHAR(10) NOT NULL,    -- sms, email
    sender_id UUID NOT NULL REFERENCES shalenu_users(id) ON DELETE CASCADE,
    recipient_type VARCHAR(20) NOT NULL,  -- all, group, individual
    recipient_ids UUID[],
    status VARCHAR(20) DEFAULT 'draft',   -- draft, sent, failed
    sent_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

-- 3. 생일 알림 설정 (Birthday Alerts)
CREATE TABLE shalenu_birthday_alerts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    church_id UUID NOT NULL REFERENCES shalenu_churches(id) ON DELETE CASCADE,
    alert_days_before INT NOT NULL DEFAULT 7,
    is_active BOOLEAN DEFAULT TRUE,
    notify_via VARCHAR(10) DEFAULT 'both', -- sms, email, both
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE (church_id)
);

-- 4. 시설 (Facilities)
CREATE TABLE shalenu_facilities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    church_id UUID NOT NULL REFERENCES shalenu_churches(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    capacity INT,
    description TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW()
);

-- 5. 시설 예약 (Facility Bookings)
CREATE TABLE shalenu_facility_bookings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    church_id UUID NOT NULL REFERENCES shalenu_churches(id) ON DELETE CASCADE,
    facility_id UUID NOT NULL REFERENCES shalenu_facilities(id) ON DELETE CASCADE,
    title VARCHAR(200) NOT NULL,
    booked_by UUID NOT NULL REFERENCES shalenu_users(id) ON DELETE CASCADE,
    start_time TIMESTAMPTZ NOT NULL,
    end_time TIMESTAMPTZ NOT NULL,
    status VARCHAR(20) DEFAULT 'pending', -- pending, approved, cancelled
    note TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- ============================================================
-- 인덱스
-- ============================================================
CREATE INDEX idx_pastoral_notes_church ON shalenu_pastoral_notes(church_id);
CREATE INDEX idx_pastoral_notes_member ON shalenu_pastoral_notes(member_id);
CREATE INDEX idx_pastoral_notes_author ON shalenu_pastoral_notes(author_id);
CREATE INDEX idx_pastoral_notes_church_member ON shalenu_pastoral_notes(church_id, member_id);
CREATE INDEX idx_messages_church ON shalenu_messages(church_id);
CREATE INDEX idx_messages_church_status ON shalenu_messages(church_id, status);
CREATE INDEX idx_messages_sender ON shalenu_messages(sender_id);
CREATE INDEX idx_birthday_alerts_church ON shalenu_birthday_alerts(church_id);
CREATE INDEX idx_facilities_church ON shalenu_facilities(church_id);
CREATE INDEX idx_facility_bookings_church ON shalenu_facility_bookings(church_id);
CREATE INDEX idx_facility_bookings_facility ON shalenu_facility_bookings(facility_id);
CREATE INDEX idx_facility_bookings_time ON shalenu_facility_bookings(facility_id, start_time, end_time);

-- ============================================================
-- RLS (Row Level Security) 활성화
-- ============================================================
ALTER TABLE shalenu_pastoral_notes ENABLE ROW LEVEL SECURITY;
ALTER TABLE shalenu_messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE shalenu_birthday_alerts ENABLE ROW LEVEL SECURITY;
ALTER TABLE shalenu_facilities ENABLE ROW LEVEL SECURITY;
ALTER TABLE shalenu_facility_bookings ENABLE ROW LEVEL SECURITY;

-- ============================================================
-- RLS 정책 (service_role은 전체 접근, authenticated는 church_id 기준)
-- ============================================================

-- 목양 노트
CREATE POLICY "pastoral_notes_service_all" ON shalenu_pastoral_notes
  FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "pastoral_notes_auth_read" ON shalenu_pastoral_notes
  FOR SELECT TO authenticated USING (true);
CREATE POLICY "pastoral_notes_auth_write" ON shalenu_pastoral_notes
  FOR ALL TO authenticated USING (true) WITH CHECK (true);

-- 메시지
CREATE POLICY "messages_service_all" ON shalenu_messages
  FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "messages_auth_all" ON shalenu_messages
  FOR ALL TO authenticated USING (true) WITH CHECK (true);

-- 생일 알림
CREATE POLICY "birthday_alerts_service_all" ON shalenu_birthday_alerts
  FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "birthday_alerts_auth_all" ON shalenu_birthday_alerts
  FOR ALL TO authenticated USING (true) WITH CHECK (true);

-- 시설
CREATE POLICY "facilities_service_all" ON shalenu_facilities
  FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "facilities_auth_all" ON shalenu_facilities
  FOR ALL TO authenticated USING (true) WITH CHECK (true);

-- 시설 예약
CREATE POLICY "facility_bookings_service_all" ON shalenu_facility_bookings
  FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "facility_bookings_auth_all" ON shalenu_facility_bookings
  FOR ALL TO authenticated USING (true) WITH CHECK (true);

-- ============================================================
-- updated_at 자동 갱신 트리거
-- ============================================================
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
$$ language 'plpgsql';

CREATE TRIGGER update_pastoral_notes_updated_at
  BEFORE UPDATE ON shalenu_pastoral_notes
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ============================================================
-- 기본 데이터 (생일 알림 기본 설정)
-- ============================================================
-- 교회별 생일 알림 기본 레코드는 church 생성 시 애플리케이션 레벨에서 삽입 권장
-- INSERT INTO shalenu_birthday_alerts (church_id, alert_days_before, is_active, notify_via)
-- VALUES ('<교회-UUID>', 7, true, 'both');
