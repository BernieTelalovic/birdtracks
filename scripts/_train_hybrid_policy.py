"""Shared command-line trainer for target-conditioned hybrid policies."""

from __future__ import annotations

import argparse
from pathlib import Path
from random import Random

from birdtracks.projectors.hybrid_policy_training import (
    FEATURE_COUNT,
    PolicyKind,
    oracle_trajectory,
)
from birdtracks.projectors.hybrid_training_games import (
    load_exposure_problems,
    load_resolver_problems,
    random_exposure_problem,
    random_resolver_problem,
)


def parser(kind: PolicyKind) -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description=f"Train the target-conditioned S/A {kind} policy."
    )
    result.add_argument("--steps", type=int, default=10_000)
    result.add_argument("--seed", type=int, default=7)
    result.add_argument("--hidden", type=int, default=96)
    result.add_argument("--depth", type=int, default=3)
    result.add_argument("--learning-rate", type=float, default=3e-4)
    result.add_argument("--min-lines", type=int, default=4)
    result.add_argument("--max-lines", type=int, default=24)
    result.add_argument("--min-layers", type=int, default=3)
    result.add_argument("--max-layers", type=int, default=16)
    result.add_argument(
        "--episode-steps", type=int, default=128,
        help="safety cap; successful trajectories stop naturally",
    )
    result.add_argument("--replay-size", type=int, default=256)
    result.add_argument("--human-data", type=Path)
    result.add_argument(
        "--human-probability", type=float, default=0.8,
        help="probability that an update starts from a human problem",
    )
    result.add_argument("--report-every", type=int, default=100)
    result.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "dest" / f"{kind}.pt",
    )
    return result


def run(kind: PolicyKind, args: argparse.Namespace) -> None:
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
    layers: list[nn.Module] = [nn.Linear(FEATURE_COUNT, args.hidden), nn.ReLU()]
    for _ in range(args.depth - 1):
        layers.extend((nn.Linear(args.hidden, args.hidden), nn.ReLU()))
    layers.append(nn.Linear(args.hidden, 1))
    model = nn.Sequential(*layers)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.learning_rate)
    human = _load_human(kind, args.human_data)
    replay: list[tuple[object, object]] = []
    parameters = sum(parameter.numel() for parameter in model.parameters())
    print(
        f"training {parameters:,}-parameter {kind} action-ranking policy; "
        f"lines={args.min_lines}–{args.max_lines}, "
        f"layers={args.min_layers}–{args.max_layers}"
    )
    print(
        f"human examples={len(human)}; "
        f"human sampling probability={args.human_probability:.0%}"
    )
    correct = trajectory_steps = generated_seen = human_seen = 0
    losses = 0.0
    update = 0
    attempts = 0
    while update < args.steps:
        attempts += 1
        if attempts > args.steps * 100:
            raise RuntimeError("could not produce enough trainable trajectories")
        use_human = bool(human) and rng.random() < args.human_probability
        if use_human:
            projector, target = rng.choice(human)
            human_seen += 1
        else:
            if replay and rng.random() < 0.5:
                projector, target = rng.choice(replay)
            else:
                projector, target = _random_problem(kind, rng, args)
                replay.append((projector, target))
                if len(replay) > args.replay_size:
                    replay.pop(rng.randrange(len(replay)))
            generated_seen += 1
        trajectory = oracle_trajectory(
            projector, target, kind, maximum_steps=args.episode_steps
        )
        if not trajectory:
            continue
        candidates, preferred = rng.choice(trajectory)
        features = torch.tensor(
            [candidate.features for candidate in candidates], dtype=torch.float32
        )
        scores = model(features).squeeze(-1)
        preferred_tensor = torch.tensor(preferred, dtype=torch.long)
        loss = torch.logsumexp(scores, dim=0) - torch.logsumexp(
            scores[preferred_tensor], dim=0
        )
        optimizer.zero_grad()
        loss.backward()
        optimizer.step()
        update += 1
        losses += float(loss.detach().item())
        correct += int(int(scores.argmax().item()) in preferred)
        trajectory_steps += len(trajectory)
        if update % args.report_every == 0 or update == args.steps:
            count = update % args.report_every or args.report_every
            print(
                f"step={update:6d} loss={losses / count:.4f} "
                f"oracle_accuracy={correct / count:.1%} "
                f"mean_trajectory_steps={trajectory_steps / count:.2f} "
                f"sources={{'generated': {generated_seen}, 'human': {human_seen}}}"
            )
            correct = trajectory_steps = generated_seen = human_seen = 0
            losses = 0.0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    torch.save({
        "model_state": model.state_dict(),
        "model_kind": f"hybrid_{kind}_action_ranker_v1",
        "feature_count": FEATURE_COUNT,
        "hidden": args.hidden,
        "depth": args.depth,
        "parameters": parameters,
        "seed": args.seed,
        "training_steps": args.steps,
        "episode_safety_cap": args.episode_steps,
        "action_space": "legal port rearrangement plus one recursive rewrite",
        "terminal": (
            "direct target strand" if kind == "exposer"
            else "adjacent target pair with only direct strands"
        ),
        "deterministic_cleanup": True,
        "deterministic_endpoint_collapse": kind == "resolver",
        "human_examples": len(human),
        "human_probability": args.human_probability,
    }, args.output)
    print(f"saved {args.output}")


def _random_problem(kind: PolicyKind, rng: Random, args: argparse.Namespace):
    function = random_resolver_problem if kind == "resolver" else random_exposure_problem
    return function(
        rng,
        minimum_lines=args.min_lines,
        maximum_lines=args.max_lines,
        minimum_layers=args.min_layers,
        maximum_layers=args.max_layers,
    )


def _load_human(kind: PolicyKind, path: Path | None):
    if path is None:
        return ()
    function = load_resolver_problems if kind == "resolver" else load_exposure_problems
    return function(path)


def _validate(args: argparse.Namespace) -> None:
    if min(args.steps, args.hidden, args.depth, args.episode_steps,
           args.replay_size, args.report_every) < 1:
        raise SystemExit("training, model, episode, and reporting sizes must be positive")
    if not 0 <= args.human_probability <= 1:
        raise SystemExit("human-probability must lie between zero and one")
    if args.learning_rate <= 0:
        raise SystemExit("learning-rate must be positive")

