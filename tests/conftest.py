"""the tests never send files to the trash of the system (see papers.journal.empty_trash),
and leave the PDFs of tests/downloadedpapers in place"""
import os

import pytest


@pytest.fixture(autouse=True)
def no_system_trash(monkeypatch):
    import send2trash
    monkeypatch.setattr(send2trash, 'send2trash', os.remove)


FIXTURES = os.path.join(os.path.dirname(__file__), 'downloadedpapers')


@pytest.fixture(autouse=True)
def fixture_pdfs_kept():
    """a test that moves or deletes a committed test PDF fails: the tests after it
    would download it again (and fail when the network does)"""
    before = sorted(f for f in os.listdir(FIXTURES) if f.endswith('.pdf'))
    yield
    after = sorted(f for f in os.listdir(FIXTURES) if f.endswith('.pdf'))
    assert after == before, f'test PDFs moved or deleted from {FIXTURES}: {sorted(set(before) - set(after))}'
