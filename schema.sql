-- Shalenu 데이터베이스 스키마
-- Supabase SQL Editor에서 실행

-- 교회
CREATE TABLE shalenu_churches (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(200) NOT NULL,
    address TEXT,
    phone VARCHAR(20),
    founded_date DATE,
    denomination VARCHAR(100),
    plan VARCHAR(20) DEFAULT 'free',
    created_at TIMESTAMP DEFAULT NOW()
);

-- 교인
CREATE TABLE shalenu_members (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    church_id UUID NOT NULL REFERENCES shalenu_churches(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    gender VARCHAR(10),
    phone VARCHAR(20),
    email VARCHAR(255),
    address TEXT,
    birth_date DATE,
    join_date DATE DEFAULT CURRENT_DATE,
    baptism_date DATE,
    status VARCHAR(20) DEFAULT 'active',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- 사용자 (관리자)
CREATE TABLE shalenu_users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    church_id UUID NOT NULL REFERENCES shalenu_churches(id) ON DELETE CASCADE,
    member_id UUID REFERENCES shalenu_members(id) ON DELETE SET NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(20) DEFAULT 'admin',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW()
);

-- 공통 코드 (룩업)
CREATE TABLE shalenu_lookup_codes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    church_id UUID NOT NULL REFERENCES shalenu_churches(id) ON DELETE CASCADE,
    category VARCHAR(50) NOT NULL,
    code VARCHAR(50) NOT NULL,
    label VARCHAR(100) NOT NULL,
    sort_order INT DEFAULT 0,
    parent_code TEXT,
    is_active BOOLEAN DEFAULT TRUE
);

-- 헌금 헤더
CREATE TABLE shalenu_offerings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    church_id UUID NOT NULL REFERENCES shalenu_churches(id) ON DELETE CASCADE,
    offering_date DATE NOT NULL,
    offering_type VARCHAR(50) NOT NULL,
    worship_type VARCHAR(50),
    total_amount INTEGER NOT NULL DEFAULT 0,
    status VARCHAR(20) DEFAULT 'confirmed',
    created_by UUID REFERENCES shalenu_users(id) ON DELETE SET NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

-- 헌금 항목
CREATE TABLE shalenu_offering_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    offering_id UUID NOT NULL REFERENCES shalenu_offerings(id) ON DELETE CASCADE,
    member_id UUID REFERENCES shalenu_members(id) ON DELETE SET NULL,
    giver_name VARCHAR(100),
    amount INTEGER NOT NULL,
    payment_method VARCHAR(20) DEFAULT 'cash',
    note TEXT
);

-- 계좌
CREATE TABLE shalenu_accounts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    church_id UUID NOT NULL REFERENCES shalenu_churches(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    account_type VARCHAR(20),
    balance BIGINT DEFAULT 0,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW()
);

-- 재정 거래
CREATE TABLE shalenu_transactions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    church_id UUID NOT NULL REFERENCES shalenu_churches(id) ON DELETE CASCADE,
    txn_type VARCHAR(10) NOT NULL CHECK (txn_type IN ('income', 'expense')),
    category VARCHAR(100),
    amount INTEGER NOT NULL,
    description TEXT,
    txn_date DATE NOT NULL,
    account_id UUID REFERENCES shalenu_accounts(id) ON DELETE SET NULL,
    ref_offering_id UUID REFERENCES shalenu_offerings(id) ON DELETE SET NULL,
    created_by UUID REFERENCES shalenu_users(id) ON DELETE SET NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

-- 예산
CREATE TABLE shalenu_budgets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    church_id UUID NOT NULL REFERENCES shalenu_churches(id) ON DELETE CASCADE,
    fiscal_year INT NOT NULL,
    status VARCHAR(20) DEFAULT 'draft',
    total_amount BIGINT DEFAULT 0,
    approved_by UUID REFERENCES shalenu_users(id) ON DELETE SET NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE (church_id, fiscal_year)
);

-- 예산 항목
CREATE TABLE shalenu_budget_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    budget_id UUID NOT NULL REFERENCES shalenu_budgets(id) ON DELETE CASCADE,
    category VARCHAR(100) NOT NULL,
    description TEXT,
    planned_amount BIGINT NOT NULL DEFAULT 0
);

-- 인덱스
CREATE INDEX idx_users_church_id ON shalenu_users(church_id);
CREATE INDEX idx_members_church_id ON shalenu_members(church_id);
CREATE INDEX idx_members_church_status ON shalenu_members(church_id, status);
CREATE INDEX idx_offerings_church_id ON shalenu_offerings(church_id);
CREATE INDEX idx_offerings_church_date ON shalenu_offerings(church_id, offering_date);
CREATE INDEX idx_offering_items_offering ON shalenu_offering_items(offering_id);
CREATE INDEX idx_transactions_church_id ON shalenu_transactions(church_id);
CREATE INDEX idx_transactions_church_date ON shalenu_transactions(church_id, txn_date);
CREATE INDEX idx_lookup_church_category ON shalenu_lookup_codes(church_id, category);
CREATE INDEX idx_budgets_church_year ON shalenu_budgets(church_id, fiscal_year);
CREATE INDEX idx_budget_items_budget ON shalenu_budget_items(budget_id);
