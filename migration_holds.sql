-- Migration: Hold Management (Plan de cales)
-- Run with: docker exec towt-app-v2 python3 -c "..."

-- 1. Hold assignments table
CREATE TABLE IF NOT EXISTS hold_assignments (
    id SERIAL PRIMARY KEY,
    leg_id INTEGER NOT NULL REFERENCES legs(id) ON DELETE CASCADE,
    batch_id INTEGER NOT NULL REFERENCES packing_list_batches(id) ON DELETE CASCADE,
    hold_code VARCHAR(10) NOT NULL,
    pallet_quantity INTEGER NOT NULL DEFAULT 0,
    pallet_type VARCHAR(20),
    is_stackable BOOLEAN DEFAULT false,
    assigned_by VARCHAR(200),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_hold_assignments_leg ON hold_assignments(leg_id);
CREATE INDEX IF NOT EXISTS idx_hold_assignments_batch ON hold_assignments(batch_id);

-- 2. Hold plan confirmations table
CREATE TABLE IF NOT EXISTS hold_plan_confirmations (
    id SERIAL PRIMARY KEY,
    leg_id INTEGER NOT NULL UNIQUE REFERENCES legs(id) ON DELETE CASCADE,
    confirmed_by VARCHAR(200) NOT NULL,
    confirmed_at TIMESTAMPTZ DEFAULT NOW(),
    notes TEXT
);

CREATE INDEX IF NOT EXISTS idx_hold_plan_confirmations_leg ON hold_plan_confirmations(leg_id);

-- 3. Add etd_manual column to legs if not exists
ALTER TABLE legs ADD COLUMN IF NOT EXISTS etd_manual BOOLEAN DEFAULT false;
