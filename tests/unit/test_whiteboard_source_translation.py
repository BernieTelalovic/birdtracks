"""Command spacing is a parser view, not source or coefficient ownership."""

from fractions import Fraction

import pytest

from birdtracks import Antisymmetriser, Projector, Symmetriser
from birdtracks.projectors.whiteboard import EvaluationEnvironment, projector_backend
from birdtracks.projectors.whiteboard.calculation import evaluate_projector_expression
from birdtracks.projectors.whiteboard.pair_calculation import (
    pair_expression_from_blocks, pair_expression_with_prefactor,
)
from birdtracks.projectors.whiteboard.source_translation import algebra_command_spacing
from birdtracks.young_diagrams import PairExpression, PairTerm


@pytest.mark.parametrize(('source','expected'),[
    (r'B\def\pair\oplus2_3\pair',r'B \def \pair \oplus2_3 \pair'),
    (r'2\times\pair\otimes3\pair',r'2 \times \pair \otimes3 \pair'),
    (r'\frac{N\times N}{2}\birdtracks',r'\frac{N \times N}{2} \birdtracks'),
    (r'\left(\pair\right)',r'\left( \pair \right)'),
    (r'P_{\alpha}\otimes P_{\alpha}',r'P_{\alpha} \otimes P_{\alpha}'),
    (r'P_{x\otimes y}^\tr\otimes P',r'P_{x\otimes y}^\tr \otimes P'),
    (r'\mathcal{P\otimes Q}\otimes\mathcal{R}',r'\mathcal{P\otimes Q} \otimes\mathcal{R}'),
    (r'\text{label \pair {\otimes}}\otimes B',r'\text{label \pair {\otimes}} \otimes B'),
    (r'P\_{1}\otimes Q',r'P\_{1} \otimes Q'),
    (r'P\_{x\otimes y}\otimes Q',r'P\_{x\otimes y} \otimes Q'),
    (r'\\pair',r'\\pair'),
    (r'\text{unfinished \pair',r'\text{unfinished \pair'),
])
def test_spacing_preserves_protected_tokens_and_is_idempotent(source,expected):
    result=algebra_command_spacing(source)
    assert result==expected
    assert algebra_command_spacing(result)==result


@pytest.mark.parametrize('gap',['',' '])
@pytest.mark.parametrize('outer',['',r'3\times'])
def test_pair_prefactors_are_consumed_once_with_command_spacing(gap,outer):
    source=outer+gap+r'2_3'+gap+r'\pair'
    class Editor:
        # Match the actual widget's adjacent-prefactor ownership. Without a
        # separator after \times, the source factor is external to the editor.
        pair_expression=pair_expression_with_prefactor(source,source.index(r'\pair')).state()

    blocks=[{'id':'line','source':source}]
    value=pair_expression_from_blocks(blocks,{'line:pair:0':Editor()})
    assert value.terms[0].coefficient==(6 if outer else 2)
    assert value.terms[0].n0==3
    assert blocks[0]['source']==source


@pytest.mark.parametrize('gap',['',' '])
def test_explicit_pair_multiplier_preserves_internal_coefficient(gap):
    class Editor:
        pair_expression=PairExpression((PairTerm(unbarred=(1,),coefficient=2,n0=3),)).state()

    value=pair_expression_from_blocks([{'id':'line','source':'3'+gap+r'\times'+gap+r'\pair'}],
                                      {'line:pair:0':Editor()})
    assert value.terms[0].coefficient==6
    assert value.terms[0].n0==3


@pytest.mark.parametrize('gap',['',' '])
@pytest.mark.parametrize('explicit_times',[False,True])
def test_rational_negative_projector_prefactors_keep_exact_multiplication(gap,explicit_times):
    p=Projector([Antisymmetriser((1,2))])
    q=Projector([Symmetriser((1,))])
    class Editor:
        def __init__(self,value):
            self._whiteboard_source_value=value

    times=r'\times'+gap if explicit_times else ''
    source=rf'\frac{{2}}{{3}}{gap}{times}\birdtracks{gap}\otimes{gap}-\frac{{3}}{{4}}{gap}{times}\birdtracks'
    blocks=[{'id':'line','source':source}]
    value=evaluate_projector_expression(blocks,{'line:projector:0':Editor(p),'line:projector:1':Editor(q)},
                                        EvaluationEnvironment(projector_backend))
    assert value.collapse()==((p@q)*Fraction(-1,2)).collapse()
    assert blocks[0]['source']==source
