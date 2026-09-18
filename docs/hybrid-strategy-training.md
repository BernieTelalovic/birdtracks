# Training the S/A simplification strategy

The strategy learner never constructs algebra. The exact projector kernel
enumerates legal macro actions and computes their results; the learned model
only ranks them. One macro action contains:

1. a surviving projector term;
2. an opposite-type S/A anchor pair with exactly one free direct line;
3. an intervening S/A on a second physical path;
4. a topology-preserving port arrangement;
5. one recursive S/A expansion.

This boundary means a poor model can miss a useful simplification, but cannot
change the represented operator.

## Hand-written baseline

```python
import birdtracks as bt

candidates = bt.strategy_candidates(expression)
next_expression = bt.heuristic_strategy_step(expression)
```

The baseline formalizes the hand procedure as a lexicographic score:

1. maximize `len(S.support) + len(A.support)`;
2. minimize the number of other S/A blockers around the intermediary;
3. minimize the intermediary's shared-domain obstruction with those blockers;
4. minimize graph distance to both anchors;
5. prefer the exact recursive rewrite with the best symbolic outcome.

The feature vector retains each component separately. A learned ranker can
therefore learn exceptions instead of inheriting the lexicographic rule.

## Recording preferences

Present `strategy_candidates(...)` in any UI, then record the chosen candidate
index (or tied acceptable indices):

```python
bt.append_strategy_preference(
    "dest/strategy-preferences.json",
    candidates,
    preferred=chosen_index,
)
```

The dataset stores fixed-width numeric features plus auditable action metadata.
It intentionally does not pickle Python objects. The file records its complete
feature schema and rejects incompatible versions rather than silently training
on shifted columns.

## Training

Install the optional dependency and train the variable-action ranker:

```bash
python -m pip install -e '.[training]'
python scripts/train_strategy.py \
  --preferences dest/strategy-preferences.json \
  --output dest/strategy.pt
```

Synthetic decisions use the transparent baseline as an oracle. When recorded
preferences are available, `--preference-probability` controls how often they
replace synthetic decisions. The loss is a groupwise softmax over the legal
actions in one state, and it permits several actions to be marked equally
acceptable.

## Applying a checkpoint

```python
policy = bt.LearnedHybridStrategy("dest/strategy.pt")
next_expression = policy.step(expression)
```

The checkpoint includes the ordered feature names, width, model shape, and
anchor-size definition. Loading fails if any of these are incompatible with
the running package.

At present the policy performs one macro action per call. This gives search
code an exact, memoizable transition function. Greedy repetition, beam search,
and branch-and-bound can all be layered above it without changing the training
or algebra APIs.
