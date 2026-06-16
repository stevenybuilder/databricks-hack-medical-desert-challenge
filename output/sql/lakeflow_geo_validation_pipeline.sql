-- Lakeflow/DLT production template for the geo validation workflow.
-- Do not run this file through a SQL warehouse. Use it as the SQL source for a
-- Lakeflow Declarative Pipeline when this becomes a scheduled data-quality job.

CREATE OR REFRESH MATERIALIZED VIEW workspace.default.hackathon_geo_validation_candidates_mv
COMMENT 'Geo validation candidates using the same pincode/fuzzy triage logic as the hackathon batch.'
AS
SELECT *
FROM workspace.default.hackathon_geo_validation_candidates;

CREATE OR REFRESH MATERIALIZED VIEW workspace.default.hackathon_geo_address_janitor_mv
COMMENT 'LLM parsed Indian addresses ready for geocoder validation.'
AS
SELECT *
FROM workspace.default.hackathon_geo_address_janitor;

CREATE OR REFRESH MATERIALIZED VIEW workspace.default.hackathon_geo_fuzzy_reconciliation_mv
COMMENT 'Parsed address reconciliation against pincode, state, district, and join confidence signals.'
AS
SELECT *
FROM workspace.default.hackathon_geo_fuzzy_reconciliation;
