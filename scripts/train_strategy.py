#!/usr/bin/env python3
"""Train the complete anchor–mediator–rewrite ranking policy."""

from __future__ import annotations

import argparse
from pathlib import Path
from random import Random

from birdtracks.projectors.hybrid_strategy_training import (
    STRATEGY_FEATURE_COUNT,
    STRATEGY_FEATURE_NAMES,
    PreferenceGroup,
    load_strategy_preferences,
    strategy_candidates,
)
from birdtracks.projectors.hybrid_training_games import random_resolver_problem


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description=(
            "Train one policy to rank S/A anchors, intervening nodes, "
            "topology-preserving port arrangements, and recursive rewrites."
        )
    )
    result.add_argument("--steps", type=int, default=10_000)
    result.add_argument("--seed", type=int, default=7)
    result.add_argument("--hidden", type=int, default=128)
    result.add_argument("--depth", type=int, default=3)
    result.add_argument("--learning-rate", type=float, default=3e-4)
    result.add_argument("--min-lines", type=int, default=4)
    result.add_argument("--max-lines", type=int, default=24)
    result.add_argument("--min-layers", type=int, default=3)
    result.add_argument("--max-layers", type=int, default=16)
    result.add_argument("--preferences", type=Path)
    result.add_argument(
        "--preference-probability",
        type=float,
        default=0.8,
        help="probability of sampling a recorded human ranking when available",
    )
    result.add_argument("--report-every", type=int, default=100)
    result.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "dest" / "strategy.pt",
    )
    return result


def main() -> None:
    args = parser().parse_args()
    try:
        import torch
        from torch import nn
    except ImportError as exc:
        raise SystemExit(
            "PyTorch is required; install with: pip install -e '.[training]'"
        ) from exc
    _validate(args)
    rng = Random(args.seed)
    torch.manual_seed(args.seed)
    layers: list[nn.Module] = [
        nn.Linear(STRATEGY_FEATURE_COUNT, args.hidden), nn.ReLU()
    ]
    for _ in range(args.depth - 1):
        layers.extend((nn.Linear(args.hidden, args.hidden), nn.ReLU()))
    layers.append(nn.Linear(args.hidden, 1))
    model = nn.Sequential(*layers)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.learning_rate)
    preferences = (
        load_strategy_preferences(args.preferences)
        if args.preferences is not None else ()
    )
    parameters = sum(parameter.numel() for parameter in model.parameters())
    print(
        f"training {parameters:,}-parameter full strategy ranker; "
        f"human decisions={len(preferences)}"
    )

    running_loss = 0.0
    correct = human_seen = generated_seen = 0
    update = attempts = 0
    while update < args.steps:
        attempts += 1
        if attempts > args.steps * 100:
            raise RuntimeError("could not produce enough trainable decisions")
        use_human = (
            bool(preferences)
            and rng.random() < args.preference_probability
        )
        if use_human:
            group = rng.choice(preferences)
            human_seen += 1
        else:
            group = _generated_group(rng, args)
            generated_seen += 1
        if len(group.features) < 2:
            continue
        features = torch.tensor(group.features, dtype=torch.float32)
        scores = model(features).squeeze(-1)
        preferred = torch.tensor(group.preferred, dtype=torch.long)
        loss = torch.logsumexp(scores, dim=0) - torch.logsumexp(
            scores[preferred], dim=0
        )
        optimizer.zero_grad()
        loss.backward()
        optimizer.step()
        update += 1
        running_loss += float(loss.detach().item())
        correct += int(int(scores.argmax().item()) in group.preferred)
        if update % args.report_every == 0 or update == args.steps:
            count = update % args.report_every or args.report_every
            print(
                f"step={update:6d} loss={running_loss / count:.4f} "
                f"ranking_accuracy={correct / count:.1%} "
                f"sources={{'generated': {generated_seen}, "
                f"'human': {human_seen}}}"
            )
            running_loss = 0.0
            correct = human_seen = generated_seen = 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    torch.save({
        "model_state": model.state_dict(),
        "model_kind": "hybrid_strategy_action_ranker_v1",
        "feature_count": STRATEGY_FEATURE_COUNT,
        "feature_names": STRATEGY_FEATURE_NAMES,
        "hidden": args.hidden,
        "depth": args.depth,
        "parameters": parameters,
        "seed": args.seed,
        "training_steps": args.steps,
        "anchor_size": "len(S.support) + len(A.support)",
        "action_space": (
            "anchor pair, intervening S/A, topology-preserving port "
            "arrangement, and one exact recursive rewrite"
        ),
        "human_preferences": len(preferences),
    }, args.output)
    print(f"saved {args.output}")


def _generated_group(rng: Random, args: argparse.Namespace) -> PreferenceGroup:
    projector, _target = random_resolver_problem(
        rng,
        minimum_lines=args.min_lines,
        maximum_lines=args.max_lines,
        minimum_layers=args.min_layers,
        maximum_layers=args.max_layers,
    )
    candidates = strategy_candidates(projector)
    if not candidates:
        return PreferenceGroup((), ())
    best = min(candidate.oracle_score for candidate in candidates)
    return PreferenceGroup(
        tuple(candidate.features for candidate in candidates),
        tuple(
            index for index, candidate in enumerate(candidates)
            if candidate.oracle_score == best
        ),
    )


def _validate(args: argparse.Namespace) -> None:
    if min(args.steps, args.hidden, args.depth, args.report_every) < 1:
        raise SystemExit("training, model, and reporting sizes must be positive")
    if args.learning_rate <= 0:
        raise SystemExit("learning-rate must be positive")
    if not 0 <= args.preference_probability <= 1:
        raise SystemExit("preference-probability must lie between zero and one")


if __name__ == "__main__":
    main()
