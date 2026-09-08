#!/usr/bin/env python3
"""Train the policy that exposes a direct path for a selected S/A pair."""

from _train_hybrid_policy import parser, run


if __name__ == "__main__":
    run("exposer", parser("exposer").parse_args())
