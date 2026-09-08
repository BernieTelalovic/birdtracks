#!/usr/bin/env python3
"""Train a small topology-safe detangling layout value model.

Install with ``pip install -e '.[training]'``, then for example run:

    python scripts/train_detangler.py --steps 5000 \
        --demonstrations dest/my-detangling-examples.json
"""

from __future__ import annotations

import argparse
from pathlib import Path
from random import Random

from birdtracks.projectors.detangle_training import (
    DETANGLER_SCHEMA_VERSION,
    FEATURE_COUNT,
    DetangleState,
    beam_search_detangle,
    random_projector,
)
from birdtracks.projectors.detangle_game import load_detangle_demonstrations

DEFAULT_OUTPUT = Path(__file__).resolve().parents[1] / "dest" / "detangler.pt"


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--steps", type=int, default=10_000)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--hidden", type=int, default=96)
    parser.add_argument("--depth", type=int, default=3)
    parser.add_argument("--learning-rate", type=float, default=3e-4)
    parser.add_argument("--min-strands", type=int, default=5)
    parser.add_argument("--max-strands", type=int, default=12)
    parser.add_argument("--min-layers", type=int, default=2)
    parser.add_argument("--max-layers", type=int, default=7)
    parser.add_argument("--scramble-moves", type=int, default=20)
    parser.add_argument(
        "--demonstrations",
        type=Path,
        help="versioned JSON produced by detangle_game",
    )
    parser.add_argument(
        "--human-weight",
        type=float,
        default=20.0,
        help="preference-loss weight of one human pair relative to random data",
    )
    parser.add_argument(
        "--oracle-depth",
        type=int,
        default=2,
        help="legal-move lookahead used to label the first action",
    )
    parser.add_argument(
        "--beam-width",
        type=int,
        default=8,
        help="number of candidate layouts retained at each oracle depth",
    )
    parser.add_argument(
        "--tie-tolerance",
        type=float,
        default=1e-9,
        help="loss tolerance for treating oracle actions as equally good",
    )
    parser.add_argument("--report-every", type=int, default=100)
    parser.add_argument(
        "--output", type=Path, default=DEFAULT_OUTPUT
    )
    return parser.parse_args()


def main() -> None:
    args = arguments()
    try:
        import torch
        from torch import nn
    except ImportError as exc:
        raise SystemExit(
            "PyTorch is required; install with: pip install -e '.[training]'"
        ) from exc

    if min(
        args.steps,
        args.depth,
        args.hidden,
        args.report_every,
        args.oracle_depth,
        args.beam_width,
    ) < 1:
        raise SystemExit("step, model, report, and oracle sizes must be positive")
    if args.tie_tolerance < 0:
        raise SystemExit("tie-tolerance cannot be negative")
    if args.human_weight <= 0:
        raise SystemExit("human-weight must be positive")
    if args.min_strands < 4 or args.min_strands > args.max_strands:
        raise SystemExit("strand bounds must be ordered and at least four")
    if args.min_layers < 1 or args.min_layers > args.max_layers:
        raise SystemExit("layer bounds must be ordered and positive")
    rng = Random(args.seed)
    torch.manual_seed(args.seed)
    feature_count = FEATURE_COUNT
    layers: list[nn.Module] = [nn.Linear(feature_count, args.hidden), nn.ReLU()]
    for _ in range(args.depth - 1):
        layers.extend((nn.Linear(args.hidden, args.hidden), nn.ReLU()))
    layers.append(nn.Linear(args.hidden, 1))
    model = nn.Sequential(*layers)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.learning_rate)
    parameter_count = sum(parameter.numel() for parameter in model.parameters())
    demonstrations = (
        load_detangle_demonstrations(args.demonstrations)
        if args.demonstrations is not None
        else ()
    )
    print(f"training {parameter_count:,}-parameter layout value model")
    if demonstrations:
        print(
            f"loaded {len(demonstrations)} human preferences from "
            f"{args.demonstrations} at {args.human_weight:g}x weight"
        )
    else:
        print("no human preference dataset supplied; using random oracle pairs")

    random_correct = 0
    human_correct = 0
    human_seen = 0
    preference_margin = 0.0
    for step in range(1, args.steps + 1):
        strands = rng.randint(args.min_strands, args.max_strands)
        layer_count = rng.randint(args.min_layers, args.max_layers)
        projector = random_projector(rng, strands=strands, layers=layer_count)
        state = DetangleState.random_layout(projector, rng)
        for _ in range(rng.randint(0, args.scramble_moves)):
            actions = state.legal_actions()[1:]
            if actions:
                state = state.apply(rng.choice(actions))

        oracle = beam_search_detangle(
            state,
            depth=args.oracle_depth,
            beam_width=args.beam_width,
            tolerance=args.tie_tolerance,
        )
        random_preferred = oracle.state
        random_rejected = state
        if abs(oracle.metrics.loss - state.metrics().loss) <= args.tie_tolerance:
            alternative = DetangleState.random_layout(projector, rng)
            if alternative.metrics().loss < state.metrics().loss:
                random_preferred, random_rejected = alternative, state
            else:
                random_preferred, random_rejected = state, alternative

        random_features = torch.tensor(
            [
                random_preferred.value_features(),
                random_rejected.value_features(),
            ],
            dtype=torch.float32,
        )
        random_values = model(random_features).squeeze(-1)
        random_loss = nn.functional.softplus(
            random_values[1] - random_values[0]
        )
        objective = random_loss

        human_values = None
        if demonstrations:
            human_initial, human_preferred = rng.choice(demonstrations)
            human_features = torch.tensor(
                [
                    human_preferred.value_features(),
                    human_initial.value_features(),
                ],
                dtype=torch.float32,
            )
            human_values = model(human_features).squeeze(-1)
            human_loss = nn.functional.softplus(
                human_values[1] - human_values[0]
            )
            objective = (
                random_loss + args.human_weight * human_loss
            ) / (1.0 + args.human_weight)
        optimizer.zero_grad()
        objective.backward()
        optimizer.step()

        random_correct += bool(random_values[0] > random_values[1])
        preference_margin += float(
            (random_values[0] - random_values[1]).detach().item()
        )
        if human_values is not None:
            human_correct += bool(human_values[0] > human_values[1])
            human_seen += 1
        if step % args.report_every == 0 or step == args.steps:
            count = step % args.report_every or args.report_every
            human_accuracy = (
                f"{human_correct / human_seen:.1%}"
                if human_seen
                else "n/a"
            )
            print(
                f"step={step:6d} loss={objective.item():.4f} "
                f"random_pair_accuracy={random_correct / count:.1%} "
                f"human_pair_accuracy={human_accuracy} "
                f"mean_random_margin={preference_margin / count:.5f}"
            )
            random_correct = 0
            human_correct = 0
            human_seen = 0
            preference_margin = 0.0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            "model_state": model.state_dict(),
            "feature_count": feature_count,
            "detangler_schema_version": DETANGLER_SCHEMA_VERSION,
            "hidden": args.hidden,
            "depth": args.depth,
            "parameters": parameter_count,
            "seed": args.seed,
            "model_kind": "layout_value_v1",
            "loss": "(1 + length) * (1 + crossings) / (1 + straight)",
            "action_space": "visible_sa_columns_v3",
            "oracle": {
                "kind": "beam_search",
                "depth": args.oracle_depth,
                "width": args.beam_width,
                "tie_tolerance": args.tie_tolerance,
            },
            "preferences": {
                "human_dataset": (
                    str(args.demonstrations)
                    if args.demonstrations is not None
                    else None
                ),
                "human_examples": len(demonstrations),
                "human_weight": args.human_weight,
                "random_weight": 1.0,
                "objective": "pairwise_logistic",
            },
        },
        args.output,
    )
    print(f"saved {args.output}")


if __name__ == "__main__":
    main()
