-- Upgrade databases that already ran the initial signal_metadata migration.
-- Existing metadata rows and observation data are preserved.
BEGIN;
ALTER TABLE public.signal_metadata
  DROP CONSTRAINT IF EXISTS signal_metadata_measurement_type_check;
ALTER TABLE public.signal_metadata
  ADD CONSTRAINT signal_metadata_measurement_type_check
  CHECK (measurement_type IN ('Temperature', 'Pressure', 'Level', 'Flow', 'Energy', 'Unclassified'));
COMMIT;
