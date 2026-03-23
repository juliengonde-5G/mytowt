-- ============================================================
-- Migration SQL for my_TOWT — Activity Journal + Cargo Updates
-- Run via: docker exec towt-app-v2 python3 -c "..."
-- Or directly on PostgreSQL
-- ============================================================

-- 1. Activity Log table (new)
CREATE TABLE IF NOT EXISTS activity_log (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    username VARCHAR(100),
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    module VARCHAR(50) NOT NULL,
    action VARCHAR(50) NOT NULL,
    resource_type VARCHAR(50),
    resource_id INTEGER,
    detail TEXT
);
CREATE INDEX IF NOT EXISTS ix_activity_log_module ON activity_log(module);
CREATE INDEX IF NOT EXISTS ix_activity_log_id ON activity_log(id);

-- 2. Structured addresses on packing_list_batches
-- Shipper additions (shipper_name & shipper_address already exist)
ALTER TABLE packing_list_batches ADD COLUMN IF NOT EXISTS shipper_postal VARCHAR(20);
ALTER TABLE packing_list_batches ADD COLUMN IF NOT EXISTS shipper_city VARCHAR(100);
ALTER TABLE packing_list_batches ADD COLUMN IF NOT EXISTS shipper_country VARCHAR(100);

-- Notify additions (notify_address already exists, rename concept: now structured)
ALTER TABLE packing_list_batches ADD COLUMN IF NOT EXISTS notify_name VARCHAR(200);
ALTER TABLE packing_list_batches ADD COLUMN IF NOT EXISTS notify_postal VARCHAR(20);
ALTER TABLE packing_list_batches ADD COLUMN IF NOT EXISTS notify_city VARCHAR(100);
ALTER TABLE packing_list_batches ADD COLUMN IF NOT EXISTS notify_country VARCHAR(100);

-- Consignee additions (consignee_address already exists, rename concept: now structured)
ALTER TABLE packing_list_batches ADD COLUMN IF NOT EXISTS consignee_name VARCHAR(200);
ALTER TABLE packing_list_batches ADD COLUMN IF NOT EXISTS consignee_postal VARCHAR(20);
ALTER TABLE packing_list_batches ADD COLUMN IF NOT EXISTS consignee_city VARCHAR(100);
ALTER TABLE packing_list_batches ADD COLUMN IF NOT EXISTS consignee_country VARCHAR(100);

-- 3. Description of goods for Bill of Lading
ALTER TABLE packing_list_batches ADD COLUMN IF NOT EXISTS description_of_goods TEXT;
