# Statistical Modeling Plan

## Objective

Estimate two different quantities without confusing them:

1. `P(round win | current state)` — how favourable the current situation is.
2. `P(action | current state)` — which action players tend to choose.

The first can be trained from the downloaded metadata. Reliable movement actions
such as peeking, holding, and rotating require positional demo data later.

Hard game rules remain in the simulator. Statistical models estimate uncertain
outcomes and player behaviour; they do not replace deterministic rules.

## Current implementation status

The first two model profiles are now available under `src/cs2_sim/models/`:

- `SmallStatisticalModel`: dependency-free Beta/Dirichlet scorer with entropy;
- `FullLightGBMModel`: optional LightGBM scorer blended with the small model;
- `features.py`: one shared feature schema for training and inference.

The full profile still needs replay parsing and labelled `TrainingExample` rows
before it can produce a trained artifact. This keeps model code separate from
the dataset-specific parser.

## Available data and limits

The current metadata provides round outcomes, kill events, player sides, bomb
plant timing, map, patch, and match identifiers. From it, create one compact
snapshot at round start, after each kill, and at bomb plant.

Initial features:

- Map and patch
- Round number
- Elapsed and remaining round time
- CT and T players alive
- Alive-player difference
- Bomb planted flag and bomb site
- Number and side of recent kills
- Current score difference, if available

Do not generate a row for every game tick. Event snapshots are much smaller and
contain nearly all information available in this metadata.

## Algorithms and their roles

### 1. Beta-binomial win tables

Use this as the first working probability model. Group similar states into
buckets and calculate a smoothed CT win probability:

```text
P(CT win | state bucket) = (CT wins + alpha) / (samples + alpha + beta)
```

Start with `alpha = beta = 1`. This model is extremely fast, handles small
samples safely, and exposes its sample size and uncertainty. It is also a useful
fallback when a learned model is unavailable.

Suggested bucket:

```text
map, time bucket, CT alive, T alive, bomb state
```

### 2. Dirichlet-multinomial action model

Use a Dirichlet-smoothed count table for discrete actions:

```text
P(action | state) = (action count + alpha) /
                    (state count + alpha * number of legal actions)
```

The existing `BayesianPolicy` is the start of this model. Movement destinations
must remain part of the action key, for example:

```text
move_to_adjacent_zone:A_SITE
```

This is the preferred small action model because it is fast, inspectable, and
can report confidence from its sample count.

### 3. Logistic regression baseline

Train logistic regression for round-win probability after the count-table model.
It is fast and gives understandable feature weights:

```text
P(CT win) = sigmoid(weighted feature sum)
```

Use one-hot encoding for low-cardinality categories such as map and bomb site.
Regularize the model to reduce overfitting. This provides the baseline that more
complex models must beat.

### 4. Gaussian Naive Bayes

Gaussian Naive Bayes can be included as a speed benchmark, but it should not be
the primary model. It assumes that numeric features are conditionally
independent and Gaussian within each class.

This assumption is weak for CS2 data:

- Alive counts are discrete.
- Time is bounded.
- Bomb state is categorical.
- Many features strongly interact.

It may still be useful for continuous measurements such as engagement distance
or movement duration after transformation. Compare it against logistic
regression, but do not select it solely because it trains quickly.

### 5. LightGBM

Use LightGBM as the primary nonlinear round-win model after the baselines work.
Its histogram-based decision trees are fast for compact tabular data and can
learn interactions such as:

```text
bomb planted + low time + player advantage + map
```

Initial limits for fast CPU training:

```text
num_leaves: 15-31
learning_rate: 0.05
num_boost_round: at most 500
early_stopping_rounds: 30
feature_fraction: 0.8
bagging_fraction: 0.8
```

Use early stopping instead of a large parameter search. Do not add XGBoost or
CatBoost until LightGBM has been evaluated; testing many similar algorithms adds
complexity without improving the simulation design.

### 6. Shannon entropy

Shannon entropy is an analysis and uncertainty measure, not a replacement for a
prediction model:

```text
H(actions | state) = -sum(P(action) * log2(P(action)))
```

Use normalized entropy `H / log2(number of legal actions)` so results range from
zero to one:

- Near `0`: players almost always choose the same action; the state is predictable.
- Near `1`: several actions are used evenly; advice should have lower confidence.

Applications:

- Display confidence alongside a recommendation.
- Detect predictable team tendencies.
- Find states where more data is needed.
- Compare tactical variety between teams or patches.
- Use information gain or mutual information for feature selection.

Never describe the lowest-entropy action as automatically the best action. It is
only the most predictable action.

### 7. Markov transition model

After positional demos are available, model zone transitions:

```text
P(next zone | current zone, side, time bucket, bomb state)
```

This provides fast route and rotation probabilities. A first-order Markov model
is sufficient initially. Consider a hidden Markov model only if latent tactical
phases such as default, execute, retake, and save cannot be represented directly.

### 8. Gaussian mixtures and density estimation

Gaussian mixture models or kernel density estimation can create position
heatmaps and discover common setups when coordinates become available. They are
not useful with the current event-only metadata and should be deferred.

## Fast implementation order

### Phase 1: Dataset validation

- Stream every Parquet shard once.
- Validate required columns and count corrupt rows.
- Write compact event snapshots to one processed dataset.
- Keep all rows from one match in the same data split.

### Phase 2: Statistical baselines

- Train the beta-binomial win table.
- Train the Dirichlet action table when action labels exist.
- Calculate normalized Shannon entropy and sample counts.
- Save tables as versioned JSON.

### Phase 3: Predictive baselines

- Train logistic regression.
- Optionally benchmark Gaussian Naive Bayes.
- Record training time, model size, log loss, and Brier score.

### Phase 4: Nonlinear model

- Train LightGBM with early stopping.
- Compare it with the simpler baselines on the same chronological holdout.
- Keep LightGBM only if it produces a meaningful calibration improvement.

### Phase 5: Positional actions

- Parse a selected set of raw demos.
- Convert coordinates into named map zones.
- Infer hold, peek, move, rotate, utility, plant, defuse, and save actions.
- Train the Dirichlet action policy and Markov transition model.

## Evaluation

Split by whole match, not by snapshot. Prefer a chronological split so newer
matches and patches are used only for validation or testing.

Primary metrics:

- Log loss: quality of the complete predicted probability.
- Brier score: squared probability error.
- Calibration: whether predicted 70% situations win approximately 70% of the time.
- Training and inference time.
- Model size.

Secondary metrics:

- ROC AUC, for ranking only.
- Accuracy, reported with a fixed threshold but not used as the main metric.
- Entropy and sample count, for action-policy confidence.

Reject any model that improves accuracy while making probability calibration
substantially worse.

## Selection rule

Use the simplest model that meets the following requirements:

1. It beats the global win-rate baseline on log loss and Brier score.
2. It is calibrated on a match-grouped chronological holdout.
3. Inference remains well below the one-second decision interval.
4. It reports uncertainty or falls back safely for unseen states.
5. The model artifact is small enough to ship with the simulation.

Recommended initial stack:

```text
Round value:  beta-binomial fallback -> logistic regression -> LightGBM
Action choice: Dirichlet counts + normalized Shannon entropy
Movement:      first-order Markov transitions, added after positional parsing
```
