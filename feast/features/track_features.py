"""
Track Features FeatureView
Global catalog of all discovered and approved tracks (offline-only)
"""
from datetime import timedelta
from feast import Entity, FeatureView, Field
from feast.types import Float32, String, Int64
from feast.value_type import ValueType
from feast.infra.offline_stores.file_source import FileSource

track_entity = Entity(
    name="track_id",
    description="Spotify track ID",
    value_type=ValueType.STRING,
    join_keys=["track_id"],
)

track_features_source = FileSource(
    name="track_features_source",
    path="data/parquet/track_features.parquet",
    timestamp_field="event_timestamp",
    created_timestamp_column="created_at",
)

track_features = FeatureView(
    name="track_features",
    entities=[track_entity],
    ttl=timedelta(days=365),
    online=False,  # Offline-only
    schema=[
        Field(name="track_id", dtype=String),
        Field(name="name", dtype=String),
        Field(name="artists", dtype=String),
        Field(name="album", dtype=String),
        Field(name="duration_ms", dtype=Int64),
        # ReccoBeats audio features
        Field(name="danceability", dtype=Float32),
        Field(name="energy", dtype=Float32),
        Field(name="valence", dtype=Float32),
        Field(name="tempo", dtype=Float32),
        Field(name="acousticness", dtype=Float32),
        Field(name="instrumentalness", dtype=Float32),
        Field(name="liveness", dtype=Float32),
        Field(name="loudness", dtype=Float32),
        Field(name="speechiness", dtype=Float32),
        Field(name="key", dtype=Int64),
        Field(name="mode", dtype=Int64),
        # Mood predictions
        # sad, happy, energetic, calm: 0, 1, 2, 3
        Field(name="mood", dtype=Int64),
        # Metadata
        Field(name="discovered_at", dtype=String),
        Field(name="event_timestamp", dtype=Int64),
    ],
    source=track_features_source,
)

