-- ═══════════════════════════════════════════════════════════════
-- MIGRATION: Stowage Plan System
-- Date: 2026-03-25
-- Description: Add stowage_plans table, cargo_zone to claims,
--              and migrate existing hold data.
-- ═══════════════════════════════════════════════════════════════

-- 1. Create stowage_plans table
CREATE TABLE IF NOT EXISTS stowage_plans (
    id SERIAL PRIMARY KEY,
    leg_id INTEGER NOT NULL REFERENCES legs(id) ON DELETE CASCADE,
    batch_id INTEGER NOT NULL REFERENCES packing_list_batches(id) ON DELETE CASCADE,
    zone_code VARCHAR(20) NOT NULL,
    pallet_quantity INTEGER,
    pallet_format VARCHAR(20),
    weight_total_kg FLOAT,
    is_dangerous INTEGER DEFAULT 0,
    imo_class VARCHAR(20),
    is_oversized INTEGER DEFAULT 0,
    stackable INTEGER DEFAULT 0,
    assigned_by VARCHAR(200),
    assigned_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS ix_stowage_plans_leg_id ON stowage_plans(leg_id);
CREATE INDEX IF NOT EXISTS ix_stowage_plans_batch_id ON stowage_plans(batch_id);

-- 2. Add cargo_zone column to claims table
ALTER TABLE claims ADD COLUMN IF NOT EXISTS cargo_zone VARCHAR(20);

-- 3. Migrate existing hold data (avant → AV zones, arriere → AR zones)
-- Map legacy "avant" to "INF_AV_AR" (first forward zone in loading order)
-- Map legacy "arriere" to "INF_AR_AR" (first aft zone in loading order)
UPDATE packing_list_batches
SET hold = 'INF_AV_AR'
WHERE hold IS NOT NULL AND LOWER(TRIM(hold)) = 'avant';

UPDATE packing_list_batches
SET hold = 'INF_AR_AR'
WHERE hold IS NOT NULL AND LOWER(TRIM(hold)) = 'arriere';

-- Also update docker_shifts hold field
UPDATE docker_shifts
SET hold = 'INF_AV_AR'
WHERE LOWER(TRIM(hold)) = 'avant';

UPDATE docker_shifts
SET hold = 'INF_AR_AR'
WHERE LOWER(TRIM(hold)) = 'arriere';

-- 4. Create stowage_plan entries for existing batches that have a mapped hold
INSERT INTO stowage_plans (leg_id, batch_id, zone_code, pallet_quantity, pallet_format, weight_total_kg, assigned_by, assigned_at)
SELECT
    oa.leg_id,
    b.id,
    b.hold,
    b.pallet_quantity,
    COALESCE(b.pallet_type, 'EPAL'),
    COALESCE(b.weight_kg, 0) * COALESCE(b.pallet_quantity, 0),
    'migration',
    NOW()
FROM packing_list_batches b
JOIN packing_lists pl ON b.packing_list_id = pl.id
JOIN orders o ON pl.order_id = o.id
JOIN order_assignments oa ON oa.order_id = o.id
WHERE b.hold IN (
    'INF_AR_AR', 'INF_AR_MIL', 'INF_AR_AV',
    'INF_AV_AR', 'INF_AV_MIL', 'INF_AV_AV',
    'MIL_AR_AR', 'MIL_AR_MIL', 'MIL_AR_AV',
    'MIL_AV_AR', 'MIL_AV_MIL', 'MIL_AV_AV',
    'SUP_AR_AR', 'SUP_AR_MIL', 'SUP_AR_AV',
    'SUP_AV_AR', 'SUP_AV_MIL', 'SUP_AV_AV'
)
AND NOT EXISTS (
    SELECT 1 FROM stowage_plans sp WHERE sp.batch_id = b.id AND sp.leg_id = oa.leg_id
);
