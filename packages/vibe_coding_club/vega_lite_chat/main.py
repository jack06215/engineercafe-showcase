"""`streamlit run` entry point. The app lives in ui.py, where it is linted."""

import streamlit

from packages.vibe_coding_club.vega_lite_chat import ui

streamlit.set_page_config(page_title=ui.TITLE, page_icon="📊")
ui.render_app()
