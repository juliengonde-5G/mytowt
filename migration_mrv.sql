-- ============================================================
-- Migration SQL for my_TOWT — MRV Fuel Reporting Module
-- Run via: docker exec towt-app-v2 python3 -c "..."
-- Or directly on PostgreSQL
-- ============================================================

-- 1. MRV Parameters table (global settings)
CREATE TABLE IF NOT EXISTS mrv_parameters (
    id SERIAL PRIMARY KEY,
    parameter_name VARCHAR(100) UNIQUE NOT NULL,
    parameter_value FLOAT NOT NULL,
    unit VARCHAR(50),
    description VARCHAR(255),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Insert default parameters
INSERT INTO mrv_parameters (parameter_name, parameter_value, unit, description)
VALUES
    ('avg_mdo_density', 0.845, 't/m³', 'Densité moyenne MDO (entre 0.82 et 0.87)'),
    ('mdo_admissible_deviation', 2.0, 'mt', 'Déviation admissible ROB (metric tons)'),
    ('co2_emission_factor', 3.206, 't CO₂/t fuel', 'Facteur émission CO₂ par tonne MDO')
ON CONFLICT (parameter_name) DO NOTHING;

-- 2. MRV Events table (fuel reporting events per leg)
CREATE TABLE IF NOT EXISTS mrv_events (
    id SERIAL PRIMARY KEY,
    leg_id INTEGER NOT NULL REFERENCES legs(id) ON DELETE CASCADE,
    sof_event_id INTEGER REFERENCES sof_events(id) ON DELETE SET NULL,

    -- Event identification
    event_type VARCHAR(30) NOT NULL,
    timestamp_utc TIMESTAMPTZ NOT NULL,

    -- 4 DO Counters (running totals)
    port_me_do_counter FLOAT,
    stbd_me_do_counter FLOAT,
    fwd_gen_do_counter FLOAT,
    aft_gen_do_counter FLOAT,

    -- Declared values
    rob_mt FLOAT,
    cargo_mrv_mt FLOAT,

    -- Bunkering (departure events only)
    bunkering_qty_mt FLOAT,
    bunkering_date DATE,

    -- Position (from AIS/GPS)
    latitude_deg INTEGER,
    latitude_min INTEGER,
    latitude_ns VARCHAR(1),
    longitude_deg INTEGER,
    longitude_min INTEGER,
    longitude_ew VARCHAR(1),

    -- Distance
    distance_nm FLOAT,

    -- Calculated fields
    me_consumption_mdo FLOAT,
    ae_consumption_mdo FLOAT,
    total_consumption_mdo FLOAT,
    rob_calculated FLOAT,

    -- Quality
    quality_status VARCHAR(10) DEFAULT 'pending',
    quality_notes TEXT,

    -- Metadata
    created_by VARCHAR(200),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_mrv_events_leg_id ON mrv_events(leg_id);
CREATE INDEX IF NOT EXISTS ix_mrv_events_timestamp ON mrv_events(timestamp_utc);

-- 3. Add lightship_mt to vessels table (for MRV cargo calculation: displacement - lightship)
ALTER TABLE vessels ADD COLUMN IF NOT EXISTS lightship_mt FLOAT;
