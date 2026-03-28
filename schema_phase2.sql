-- ============================================================
-- J-SheepFold Phase 2 데이터베이스 스키마
-- Supabase SQL Editor에서 실행
-- ============================================================

-- 1. 예배 (Worship Services)
CREATE TABLE shalenu_worship_services (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    church_id UUID NOT NULL REFERENCES shalenu_churches(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,           -- 예: "주일 1부 예배", "수요 예배"
    day_of_week SMALLINT,                 -- 0=일, 1=월, ..., 6=토
    start_time TIME,
    is_active BOOLEAN DEFAULT TRUE,
    sort_order INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW()
);

-- 2. 구역/소그룹 (Small Groups)
CREATE TABLE shalenu_small_groups (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    church_id UUID NOT NULL REFERENCES shalenu_churches(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,           -- 그룹명
    group_type VARCHAR(50),               -- 구역, 소그룹, 셀 등 (lookup_codes 참조)
    leader_id UUID REFERENCES shalenu_members(id) ON DELETE SET NULL,
    description TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW()
);

-- 3. 구역원 (Small Group Members)
CREATE TABLE shalenu_small_group_members (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    small_group_id UUID NOT NULL REFERENCES shalenu_small_groups(id) ON DELETE CASCADE,
    member_id UUID NOT NULL REFERENCES shalenu_members(id) ON DELETE CASCADE,
    role VARCHAR(20) DEFAULT 'member',    -- leader, vice_leader, member
    joined_at DATE DEFAULT CURRENT_DATE,
    left_at DATE,
    is_active BOOLEAN DEFAULT TRUE,
    UNIQUE (small_group_id, member_id)
);

-- 4. 출석 (Attendance Logs)
CREATE TABLE shalenu_attendance_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    church_id UUID NOT NULL REFERENCES shalenu_churches(id) ON DELETE CASCADE,
    member_id UUID NOT NULL REFERENCES shalenu_members(id) ON DELETE CASCADE,
    service_id UUID REFERENCES shalenu_worship_services(id) ON DELETE SET NULL,
    attendance_date DATE NOT NULL,
    status VARCHAR(20) DEFAULT 'present', -- present, absent, late, online
    note TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE (church_id, member_id, service_id, attendance_date)
);

-- 5. 작정헌금 (Offering Pledges)
CREATE TABLE shalenu_offering_pledges (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    church_id UUID NOT NULL REFERENCES shalenu_churches(id) ON DELETE CASCADE,
    member_id UUID NOT NULL REFERENCES shalenu_members(id) ON DELETE CASCADE,
    pledge_year INT NOT NULL,
    offering_type VARCHAR(50) NOT NULL,   -- 십일조, 감사헌금 등 (lookup_codes 참조)
    pledged_amount BIGINT NOT NULL DEFAULT 0,
    paid_amount BIGINT NOT NULL DEFAULT 0,
    status VARCHAR(20) DEFAULT 'active',  -- active, completed, cancelled
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE (church_id, member_id, pledge_year, offering_type)
);

-- 6. 새가족 (Newcomers)
CREATE TABLE shalenu_newcomers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    church_id UUID NOT NULL REFERENCES shalenu_churches(id) ON DELETE CASCADE,
    member_id UUID REFERENCES shalenu_members(id) ON DELETE SET NULL,  -- 등록 후 연결
    name VARCHAR(100) NOT NULL,
    phone VARCHAR(20),
    email VARCHAR(255),
    gender VARCHAR(10),
    birth_date DATE,
    address TEXT,
    visit_date DATE NOT NULL,             -- 첫 방문일
    visit_route VARCHAR(100),             -- 방문 경로 (지인 소개, 인터넷 등)
    assigned_to UUID REFERENCES shalenu_members(id) ON DELETE SET NULL,  -- 담당 인도자
    status VARCHAR(20) DEFAULT 'visiting', -- visiting, registered, left
    note TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- ============================================================
-- 인덱스
-- ============================================================
CREATE INDEX idx_worship_services_church ON shalenu_worship_services(church_id);
CREATE INDEX idx_small_groups_church ON shalenu_small_groups(church_id);
CREATE INDEX idx_small_group_members_group ON shalenu_small_group_members(small_group_id);
CREATE INDEX idx_small_group_members_member ON shalenu_small_group_members(member_id);
CREATE INDEX idx_attendance_church ON shalenu_attendance_logs(church_id);
CREATE INDEX idx_attendance_church_date ON shalenu_attendance_logs(church_id, attendance_date);
CREATE INDEX idx_attendance_member ON shalenu_attendance_logs(member_id);
CREATE INDEX idx_pledges_church ON shalenu_offering_pledges(church_id);
CREATE INDEX idx_pledges_church_year ON shalenu_offering_pledges(church_id, pledge_year);
CREATE INDEX idx_pledges_member ON shalenu_offering_pledges(member_id);
CREATE INDEX idx_newcomers_church ON shalenu_newcomers(church_id);
CREATE INDEX idx_newcomers_church_status ON shalenu_newcomers(church_id, status);

-- ============================================================
-- RLS (Row Level Security) 활성화
-- ============================================================
ALTER TABLE shalenu_worship_services ENABLE ROW LEVEL SECURITY;
ALTER TABLE shalenu_small_groups ENABLE ROW LEVEL SECURITY;
ALTER TABLE shalenu_small_group_members ENABLE ROW LEVEL SECURITY;
ALTER TABLE shalenu_attendance_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE shalenu_offering_pledges ENABLE ROW LEVEL SECURITY;
ALTER TABLE shalenu_newcomers ENABLE ROW LEVEL SECURITY;
