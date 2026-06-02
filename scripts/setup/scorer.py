"""Scoring logic for the notes setup framework recommendation."""

from __future__ import annotations


def score(
    corpus: dict | None,
    q1: int,
    q2: int | None,
    q3: int | None,
) -> dict:
    """Return a recommendation dict based on corpus signals and question answers.

    Args:
        corpus: Output of analyze_corpus(), or None if no export was available.
        q1: Q1 answer (1-4). Answer 4 → EXISTING path, q2/q3 ignored.
        q2: Q2 answer (1-3), or None when q1 == 4.
        q3: Q3 answer (1-3), or None when q1 == 4.

    Returns dict with keys: winner, runner_up, scores, confidence, gap, rationale.
    """
    if q1 == 4:
        return {
            "winner": "EXISTING",
            "runner_up": None,
            "scores": {},
            "confidence": "n/a",
            "gap": 0,
            "rationale": (
                "You indicated your current system mostly works. "
                "We'll map your existing folders and suggest a few lightweight improvements."
            ),
        }

    scores: dict[str, int] = {"PARA": 0, "GTD": 0, "ZETTELKASTEN": 0}

    # ── Corpus signals ────────────────────────────────────────────────────────
    if corpus:
        note_count = corpus.get("note_count", 0)
        folder_count = corpus.get("folder_count", 0)
        avg_word_count = corpus.get("avg_word_count", 0.0)
        task_pct = corpus.get("task_keyword_pct", 0.0)
        xref_pct = corpus.get("cross_ref_pct", 0.0)
        oldest_days = corpus.get("oldest_note_days", 0)

        if note_count > 1000:
            scores["ZETTELKASTEN"] += 2
        if note_count < 200:
            scores["GTD"] += 1
            scores["PARA"] += 1

        if avg_word_count < 80:
            scores["GTD"] += 2
        elif avg_word_count > 300:
            scores["ZETTELKASTEN"] += 2
        else:
            scores["PARA"] += 1

        if xref_pct > 0.05:
            scores["ZETTELKASTEN"] += 3

        if task_pct > 0.10:
            scores["GTD"] += 2

        if folder_count > 6:
            scores["PARA"] += 2
        elif folder_count <= 2:
            scores["ZETTELKASTEN"] += 1
            scores["GTD"] += 1

        if oldest_days > 3 * 365:
            scores["ZETTELKASTEN"] += 1

    # ── Question answers ──────────────────────────────────────────────────────
    _q1_map = {1: ("GTD", 3), 2: ("PARA", 3), 3: ("ZETTELKASTEN", 3)}
    if q1 in _q1_map:
        fw, pts = _q1_map[q1]
        scores[fw] += pts

    if q2 == 1:
        scores["PARA"] += 2
    elif q2 == 2:
        scores["GTD"] += 2
        scores["PARA"] += 1
    elif q2 == 3:
        scores["ZETTELKASTEN"] += 2

    if q3 == 1:
        scores["GTD"] += 2
    elif q3 == 2:
        scores["PARA"] += 2
    elif q3 == 3:
        scores["ZETTELKASTEN"] += 3

    # ── Rank and tie-break ────────────────────────────────────────────────────
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    winner_key, winner_score = ranked[0]
    runner_key, runner_score = ranked[1]
    gap = winner_score - runner_score

    # Tie-break: PARA beats ZETTELKASTEN; GTD beats PARA when task signals dominate
    if gap < 2:
        task_dominated = corpus is not None and corpus.get("task_keyword_pct", 0) > 0.10
        if winner_key == "ZETTELKASTEN" and runner_key == "PARA":
            winner_key, runner_key = "PARA", "ZETTELKASTEN"
        elif winner_key == "PARA" and runner_key == "GTD" and task_dominated:
            winner_key, runner_key = "GTD", "PARA"

    if gap >= 5:
        confidence = "high"
    elif gap >= 2:
        confidence = "moderate"
    else:
        confidence = "low"
        if winner_key != "PARA":
            runner_key = winner_key
            winner_key = "PARA"

    rationale = _build_rationale(winner_key, runner_key, corpus, q1, q2, q3, scores)

    return {
        "winner": winner_key,
        "runner_up": runner_key,
        "scores": scores,
        "confidence": confidence,
        "gap": gap,
        "rationale": rationale,
    }


def _build_rationale(
    winner: str,
    runner_up: str,
    corpus: dict | None,
    q1: int,
    q2: int | None,
    q3: int | None,
    scores: dict,
) -> str:
    parts: list[str] = []

    # Goal-driven opener
    goal_map = {
        1: "Your primary focus on tasks and commitments",
        2: "Your focus on keeping active work clearly organised",
        3: "Your goal of developing ideas over time",
    }
    if q1 in goal_map:
        parts.append(goal_map[q1])

    # Corpus observations
    if corpus:
        note_count = corpus.get("note_count", 0)
        xref_pct = corpus.get("cross_ref_pct", 0.0)
        task_pct = corpus.get("task_keyword_pct", 0.0)
        avg_words = corpus.get("avg_word_count", 0.0)

        if winner == "ZETTELKASTEN" and xref_pct > 0.05:
            pct = int(xref_pct * 100)
            parts.append(f"and {pct}% of your notes already use cross-references")
        elif winner == "GTD" and task_pct > 0.10:
            pct = int(task_pct * 100)
            parts.append(f"and {pct}% of your notes contain task-oriented keywords")
        elif winner == "PARA" and note_count > 0:
            parts.append("align well with PARA's four-bucket structure")

        if avg_words > 300 and winner == "ZETTELKASTEN":
            parts.append("your long-form notes suggest a writing and synthesis workflow")
        elif avg_words < 80 and winner == "GTD":
            parts.append("your short, action-oriented notes fit GTD's list-based model")

    # Maintenance note
    if q2 == 1 and winner == "PARA":
        parts.append("PARA requires the least ongoing maintenance of the three options")
    elif q2 == 3 and winner == "ZETTELKASTEN":
        parts.append("you're willing to invest the deliberate processing Zettelkasten requires")

    # Runner-up note
    runner_labels = {
        "PARA": "PARA's simpler structure",
        "GTD": "GTD if task overload becomes your main pain",
        "ZETTELKASTEN": "Zettelkasten once your library grows and ideas need to compound",
    }
    runner_note = f"Consider {runner_labels.get(runner_up, runner_up)} as an alternative."

    main = " — ".join(parts) + "." if parts else f"{winner} is the best match for your library."
    return f"{main}\n{runner_note}"
