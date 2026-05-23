"""
Congress members ETL asset.

Pipeline: Congress.gov API + unitedstates/congress-legislators
       → MinIO snapshot → upsert DB

Data is stored as returned by the source. No vocabulary normalization is applied
upfront — if a specific transformation is needed to satisfy a DB constraint, it
will be added at that point with an explicit justification.
"""
