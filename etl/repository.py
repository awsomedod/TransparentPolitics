from dagster import Definitions

# Assets, schedules, and sensors are registered here as they are built.
# Each milestone adds entries to these lists.
defs = Definitions(
    assets=[],
    schedules=[],
    sensors=[],
)
