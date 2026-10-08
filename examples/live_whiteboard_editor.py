"""Disposable render-as-you-write whiteboard for manual verification."""

from fractions import Fraction
from pathlib import Path
from tempfile import TemporaryDirectory

from IPython.display import Markdown, display

from birdtracks import Antisymmetriser, Projector, Symmetriser, whiteboard
from birdtracks.projectors.widget import projector_widget


directory = TemporaryDirectory(prefix='birdtracks-live-whiteboard-')
path = Path(directory.name)/'live.whiteboard'
diagram = Projector([Antisymmetriser((1,2)), Symmetriser((3,))], coefficient=Fraction(-2,3))
seed = projector_widget(diagram)
board = whiteboard(path,debug=True)
board.blocks = [
    {'id':'notation','source':r'\frac{1}{2} x + \alpha'},
    {'id':'diagram','source':r'P\def \birdtracks','projector_snapshots':{'0':seed.configuration.state()}},
    {'id':'pair','source':r'B\def \pair', 'pair_snapshots':{'0': {
        'version':1,'kind':'sum','terms':[{'kind':'pair','barred':[1],'unbarred':[1],
                                        'coefficient':'1','n0':'2'}]}}},
]
display(Markdown('Click text or an embedded diagram/pair to edit in place. Try an incomplete fraction, '
                 'then Save. Evaluation remains explicit with Shift-Enter.'))
display(board)
display(Markdown(f'Disposable file: `{path}`. Copy it before stopping the kernel if you want to keep it.'))
