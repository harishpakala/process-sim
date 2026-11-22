-- Add historian signal classification without modifying the signal_samples hypertable.
-- Apply to the same PostgreSQL/TimescaleDB database that owns public.signal_samples.
-- No measurement types or units are inferred or backfilled by this migration.
BEGIN;
CREATE TABLE IF NOT EXISTS public.signal_metadata (
    signal_id text PRIMARY KEY,
    measurement_type text NOT NULL DEFAULT 'Unclassified'
        CHECK (measurement_type IN ('Temperature', 'Pressure', 'Level', 'Energy', 'Unclassified')),
    unit text,
    classification_source text NOT NULL DEFAULT 'unclassified',
    verification_status text NOT NULL DEFAULT 'NOT_VERIFIED'
        CHECK (verification_status IN ('NOT_VERIFIED', 'PROVISIONAL', 'VERIFIED')),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT signal_metadata_signal_nonblank CHECK (length(btrim(signal_id)) > 0),
    CONSTRAINT signal_metadata_unit_nonblank CHECK (unit IS NULL OR length(btrim(unit)) > 0),
    CONSTRAINT signal_metadata_source_nonblank CHECK (length(btrim(classification_source)) > 0)
);
-- Populate only identifiers seen in the historian. Leave classifications unknown
-- until they are supported by authoritative engineering or simulation evidence.
INSERT INTO public.signal_metadata (signal_id)
SELECT DISTINCT signal_id FROM public.signal_samples
WHERE signal_id IS NOT NULL AND length(btrim(signal_id)) > 0
ON CONFLICT (signal_id) DO NOTHING;
COMMENT ON TABLE public.signal_metadata IS
    'Per-signal historian display metadata; not proof of physical sensor identity.';
COMMENT ON COLUMN public.signal_metadata.measurement_type IS
    'Engineering classification, Unclassified until independently evidenced.';
COMMIT;
