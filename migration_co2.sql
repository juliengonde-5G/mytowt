-- Migration: CO2 decarbonation variables table
-- Date: 2026-03-03
-- Description: Add co2_variables table for decarbonation calculation
--              with history tracking for TOWT CO2 EF

-- Create co2_variables table
CREATE TABLE IF NOT EXISTS co2_variables (
    id SERIAL PRIMARY KEY,
    variable_name VARCHAR(100) NOT NULL,
    variable_value FLOAT NOT NULL,
    unit VARCHAR(50),
    description VARCHAR(255),
    effective_date DATE NOT NULL,
    is_current BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index for quick lookup of current values
CREATE INDEX IF NOT EXISTS idx_co2_variables_current
    ON co2_variables (variable_name, is_current)
    WHERE is_current = TRUE;

-- Index for history queries
CREATE INDEX IF NOT EXISTS idx_co2_variables_history
    ON co2_variables (variable_name, effective_date DESC);

-- Insert default values
INSERT INTO co2_variables (variable_name, variable_value, unit, description, effective_date, is_current)
VALUES
    ('towt_co2_ef', 1.5, 'gCO2/t.km', 'TOWT CO2 emission factor', '2026-01-01', TRUE),
    ('conventional_co2_ef', 13.7, 'gCO2/t.km', 'Conventional transport CO2 emission factor', '2026-01-01', TRUE),
    ('sailing_cargo_capacity', 1100, 'mt', 'Sailing cargo capacity', '2026-01-01', TRUE),
    ('nm_to_km', 1.852, 'km/nm', 'Nautical miles to km conversion', '2026-01-01', TRUE)
ON CONFLICT DO NOTHING;
