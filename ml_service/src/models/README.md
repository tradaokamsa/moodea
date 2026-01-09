# Models Directory Structure

This directory contains PyTorch models for the recommendation system, organized into clear subdirectories.

## Directory Structure

```
models/
├── recommendation/     # Recommendation models (two-tower, reranker)
│   ├── models.py       # TwoTowerModel, UserTower, ItemTower, RerankerModel
│   ├── trainer.py      # TwoTowerTrainer, RerankerTrainer
│   └── dataset.py      # RecommendationDataset
│
├── mood/               # Mood prediction models
│   ├── model.py        # MoodPredictor, MoodLoss, AudioFeatureProcessor
│   └── trainer.py      # MoodTrainer, MoodDataset
│
└── common/             # Shared utilities
    ├── losses.py       # BPRLoss, TripletLoss, InBatchNegativeLoss, RankingLoss,PairwiseRankingLoss
    └── feature_processor.py  # FeatureProcessor, feature configs
```

## Usage

### Recommendation Models

```python
from models.recommendation.models import TwoTowerModel, RerankerModel
from models.recommendation.trainer import TwoTowerTrainer
from models.common.feature_processor import create_user_feature_config, create_item_feature_config

# Initialize model
model = TwoTowerModel(
    user_feature_config=create_user_feature_config(),
    item_feature_config=create_item_feature_config(),
    embedding_dim=128
)

# Train
trainer = TwoTowerTrainer(model=model, loss_type="bpr", learning_rate=1e-3)
trainer.train(train_loader=train_dataloader, num_epochs=10)
```

### Mood Prediction Models

```python
from models.mood.model import MoodPredictor, AudioFeatureProcessor
from models.mood.trainer import MoodTrainer, MoodDataset

# Initialize model
model = MoodPredictor(input_dim=9, num_moods=5)

# Train
trainer = MoodTrainer(model=model, learning_rate=1e-3)
trainer.train(train_loader=train_dataloader, num_epochs=10)
```

## Import Notes

Since we don't use `__init__.py`, imports should use explicit paths:

- `from models.recommendation.models import TwoTowerModel`
- `from models.mood.model import MoodPredictor`
- `from models.common.losses import BPRLoss`

This makes the code structure clear and avoids circular imports.
