from deepterminal_api.analysis.base import clip


def test_clip_keeps_short_text_and_cuts_at_word_boundary():
    assert clip("short  text", 40) == "short text"
    out = clip("Recent demand has been driven by investment in artificial intelligence infrastructure", 40)
    assert len(out) <= 40 and out.endswith("…") and not out[:-1].endswith(" ")
    assert out.startswith("Recent demand has been driven by")


def test_ai_term_counts_acronym_case_sensitively():
    from deepterminal_api.analysis.sentiment import AI_TERM, NARRATIVE_TERMS
    rx = NARRATIVE_TERMS[AI_TERM]
    text = "Demand for AI infrastructure and artificial intelligence grew. We said we maintain our AIM. Ai is ambiguous."
    assert len(rx.findall(text)) == 2


def test_page_furniture_removed_but_table_numbers_kept():
    from deepterminal_api.services.filings import html_to_text
    html = ("<p>disrupt our supply and distribution chain and</p><p>27</p><p><a>Table of Contents</a></p>"
            "<p>negatively impact sales.</p><table><tr><td>31</td></tr></table>")
    assert html_to_text(html) == "disrupt our supply and distribution chain and\nnegatively impact sales.\n31"
