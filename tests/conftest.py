from __future__ import annotations
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SCRIPTS=ROOT/'src'/'media2md'/'bundle'/'scripts'
DOCS_ARCHIVE=ROOT/'docs'/'archive'
ACCEPTANCE_ARCHIVE=DOCS_ARCHIVE/'acceptance'
INSTALL_GUIDES_ARCHIVE=DOCS_ARCHIVE/'install-guides'
INSTALLERS_ARCHIVE=DOCS_ARCHIVE/'installers'
RELEASE_ARCHIVE=DOCS_ARCHIVE/'release'
sys.path.insert(0,str(ROOT/'src'))
import media2md  # noqa
sys.path.insert(0,str(SCRIPTS))
