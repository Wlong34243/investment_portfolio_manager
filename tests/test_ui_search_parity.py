"""UI corpus search matches search_ranked code path."""

from ui.corpus_search import assemble_search


def test_ui_parity_with_search_ranked():
    from core.corpus.search import search_ranked

    q = "Schwab"
    ctx = assemble_search(q=q, limit=10)
    cli = search_ranked(q, limit=10)
    ui_paths = [row["hit"].path for row in ctx["hits"]]
    cli_paths = [h.path for h in cli[: len(ui_paths)]]
    assert ui_paths == cli_paths
