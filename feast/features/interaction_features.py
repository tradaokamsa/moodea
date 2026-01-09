"""
Interaction Features FeatureView
Aggregated interaction history per user-track pair (online + offline)
"""
from datetime import timedelta
from feast import Entity, FeatureView, Field
from feast.types import Float32, String, Int64
from feast.infra.offline_stores.file_source import FileSource

interaction_entity = Entity(
    name="interaction_id",
    description="User-Track interaction composite key",
    value_type=String,
    join_keys=["user_id", "track_id"],
)

interaction_features_source = FileSource(
    name="interaction_features_source",
    path="data/parquet/interaction_features.parquet",
    timestamp_field="event_timestamp",
    created_timestamp_column="created_at",
)

interaction_features = FeatureView(
    name="interaction_features",
    entities=[interaction_entity],
    ttl=timedelta(days=90),
    online=True,  # Online + offline
    schema=[
        Field(name="user_id", dtype=String),
        Field(name="track_id", dtype=String),
        Field(name="total_score", dtype=Float32),
        Field(name="interaction_count", dtype=Int64),
        Field(name="last_interaction_score", dtype=Float32),
        Field(name="recency_score", dtype=Float32),
        Field(name="event_timestamp", dtype=Int64),
    ],
    source=interaction_features_source,
)

