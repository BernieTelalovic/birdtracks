"""Symbolic birdtrack projector values."""

from .canvas_session import ProjectorCanvasSession, load
from .canvas import create
from .configuration import ProjectorConfiguration
from .detangle_game import detangle_game, load_detangle_demonstrations
from .detangle_training import (
    DetangleAction,
    DetangleMetrics,
    DetangleSearchResult,
    DetangleState,
    LearnedDetangler,
    LearnedDetangleResult,
    beam_search_detangle,
    greedy_detangle,
)
from .identities import (
    AlgebraicIdentity,
    ANTISYMMETRISER_RECURSION,
    IDENTITIES,
    MULTIPLY_CONNECTED_S_A_ANNIHILATION,
    SAME_TYPE_NESTED_ABSORPTION,
    SYMMETRISER_RECURSION,
)
from .hybrid_simplification import (
    ExposureTarget,
    SATarget,
    StrandPath,
    collapse_resolved_sa_pair,
    expose_sa_target_step,
    find_sa_exposure_targets,
    find_sa_targets,
    hybrid_collapse,
    hybrid_reduce,
    hybrid_simplify_step,
    resolve_sa_target_step,
    sa_pair_paths,
    sa_pair_ready_to_collapse,
)
from .hybrid_training_games import (
    exposure_training_game,
    hybrid_dataset_overview,
    load_exposure_problems,
    load_resolver_problems,
    random_exposure_problem,
    random_resolver_problem,
    resolver_training_game,
)
from .permutation_node import PermutationNode
from .projector import Connection, NodePort, Projector, ProjectorNode
from .projector_sum import ProjectorSum
from .simplification import (
    expand_node,
    permute_node_ports,
    recursive_expand_node,
    remove_multiply_connected_s_a_terms,
    simplify_step,
)
from .symmetrisers import Antisymmetriser, Symmetriser

__all__ = [
    "Antisymmetriser",
    "AlgebraicIdentity",
    "ANTISYMMETRISER_RECURSION",
    "Connection",
    "NodePort",
    "IDENTITIES",
    "MULTIPLY_CONNECTED_S_A_ANNIHILATION",
    "DetangleAction",
    "DetangleMetrics",
    "DetangleSearchResult",
    "DetangleState",
    "ExposureTarget",
    "LearnedDetangler",
    "LearnedDetangleResult",
    "SATarget",
    "StrandPath",
    "collapse_resolved_sa_pair",
    "create",
    "SAME_TYPE_NESTED_ABSORPTION",
    "Projector",
    "ProjectorCanvasSession",
    "ProjectorConfiguration",
    "ProjectorNode",
    "ProjectorSum",
    "PermutationNode",
    "Symmetriser",
    "SYMMETRISER_RECURSION",
    "expand_node",
    "permute_node_ports",
    "recursive_expand_node",
    "beam_search_detangle",
    "detangle_game",
    "greedy_detangle",
    "load_detangle_demonstrations",
    "load",
    "expose_sa_target_step",
    "exposure_training_game",
    "find_sa_exposure_targets",
    "find_sa_targets",
    "hybrid_dataset_overview",
    "hybrid_collapse",
    "hybrid_reduce",
    "hybrid_simplify_step",
    "load_exposure_problems",
    "load_resolver_problems",
    "random_exposure_problem",
    "random_resolver_problem",
    "remove_multiply_connected_s_a_terms",
    "simplify_step",
    "resolve_sa_target_step",
    "sa_pair_paths",
    "sa_pair_ready_to_collapse",
    "resolver_training_game",
]
