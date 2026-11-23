"""`streamlit run` entry point. The app lives in ui.py, where it is linted."""

import streamlit

from packages.monkeytype_analysis_console import ui

streamlit.set_page_config(page_title=ui.TITLE, page_icon="⌨️", layout="wide")
ui.render_app()
