-- Purge all passenger bookings EXCEPT PAX-20260310-7415
-- Cascading FKs will automatically delete:
--   passengers, passenger_payments, passenger_documents,
--   preboarding_forms, passenger_audit_logs

BEGIN;

-- Verify the booking to keep exists
SELECT id, reference, status FROM passenger_bookings WHERE reference = 'PAX-20260310-7415';

-- Delete all other bookings (CASCADE handles child tables)
DELETE FROM passenger_bookings WHERE reference != 'PAX-20260310-7415';

COMMIT;
