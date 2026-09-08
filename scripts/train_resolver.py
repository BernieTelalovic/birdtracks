#!/usr/bin/env python3
"""Train the policy that clears obstructed paths from a selected S/A pair."""

from _train_hybrid_policy import parser, run


if __name__ == "__main__":
    run("resolver", parser("resolver").parse_args())
