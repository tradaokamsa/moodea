# Flink Jobs

PyFlink streaming jobs for real-time feature computation from Kafka events.

## Structure

- `src/main.py`: Flink job entry point
- `src/processors/`: Event processors (user features, interaction features)
- `src/sinks/`: Custom sinks (Feast sink)

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Configure environment variables (copy `.env.example` to `.env`)

3. Run Flink job:
```bash
flink run -py src/main.py
```

## Jobs

- **User Feature Processor**: Processes `user-events` → computes `user_features` → writes to Feast
- **Interaction Feature Processor**: Processes `interaction-events` → computes `interaction_features` → writes to Feast

