"""A shared, dependency-free ranking input for survey and game answers."""
from pathlib import Path

import streamlit as st
import streamlit.components.v2 as components

ASSETS = Path(__file__).resolve().parent.parent / 'static'
ranking_component = None


def register_ranking_component():
    """Register once per app script run, including fresh test runtimes."""
    global ranking_component
    ranking_component = components.component(
        'hint_ranking', html='<div class="ranking-root"></div>',
        css=(ASSETS / 'ranking.css').read_text(), js=(ASSETS / 'ranking.js').read_text(),
    )


def ranking_input(options, key, initial=None, submit=None):
    previous = st.session_state.get(key, {})
    value = previous.get('selection') or {'order': initial or [], 'confirmed': bool(initial)}
    result = ranking_component(
        key=key, data={'options': options, 'value': value, 'game': submit is not None, 'saved': initial},
        default={'selection': value},
        on_selection_change=lambda: None, on_submitted_change=lambda: None,
    )
    if submit and result.submitted:
        submit(result.submitted)
    selection = result.selection or value
    return selection.get('order', []) if selection.get('confirmed') else []
