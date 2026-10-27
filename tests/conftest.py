"""the tests never send files to the trash of the system (see papers.journal.empty_trash)"""
import os

import pytest


@pytest.fixture(autouse=True)
def no_system_trash(monkeypatch):
    import send2trash
    monkeypatch.setattr(send2trash, 'send2trash', os.remove)
