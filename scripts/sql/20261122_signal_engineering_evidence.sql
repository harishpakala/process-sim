-- Keep auditable engineering LocalID -> asset identifier -> OPC UA SignalName evidence.
-- The source presently verified in code is OPCUAConnectivity, not OPCUAINVENTORY.
BEGIN;
CREATE TABLE IF NOT EXISTS public.signal_engineering_evidence (
    signal_id text NOT NULL,
    engineering_domain text NOT NULL CHECK (engineering_domain IN ('DEXPI', 'ECAD')),
    local_id text NOT NULL,
    asset_identifier text NOT NULL,
    mapping_source text NOT NULL,
    inferred_measurement_type text,
    observed_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (signal_id, engineering_domain, local_id, asset_identifier),
    CHECK (inferred_measurement_type IS NULL OR inferred_measurement_type IN
           ('Temperature', 'Pressure', 'Level', 'Flow', 'Energy'))
);
CREATE INDEX IF NOT EXISTS signal_engineering_evidence_asset_idx
    ON public.signal_engineering_evidence (asset_identifier);
COMMENT ON TABLE public.signal_engineering_evidence IS
    'Source-backed engineering associations, not verified physical sensor identity.';
COMMIT;
