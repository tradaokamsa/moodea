"""
User Features FeatureView
User preferences and listening patterns (online + offline)
"""
from datetime import timedelta
from feast import Entity, FeatureView, Field
from feast.types import Float32, String, Int64, Array
from feast.infra.offline_stores.file_source import FileSource

# TODO: Define user entity
user_entity = Entity(
    name="user_id",
    description="User ID",
    value_type=String,
)

# TODO: Define user features source (Parquet file)
# user_features_source = FileSource(
#     name="user_features_source",
#     path="data/parquet/user_features.parquet",
#     timestamp_field="event_timestamp",
#     created_timestamp_column="created_at",
# )

# TODO: Define user_features FeatureView
# user_features = FeatureView(
#     name="user_features",
#     entities=[user_entity],
#     ttl=timedelta(days=30),
#     online=True,  # Online + offline
#     schema=[
#         Field(name="user_id", dtype=String),
#         Field(name="top_artists", dtype=Array(String)),
#         Field(name="top_genres", dtype=Array(String)),
#         Field(name="listening_pattern_score", dtype=Float32),
#         Field(name="preference_vector", dtype=Array(Float32)),
#         Field(name="event_timestamp", dtype=Int64),
#     ],
#     source=user_features_source,
# )

