"""
retrieval/query_router.py

Routes a user query to the relevant Qdrant collections using keyword detection.
Falls back to searching all collections if intent is ambiguous.

Returns: list of section keys e.g. ["sops"], ["deviations", "capas"], ["all"]
"""

import re
from typing import List


# Keyword patterns per collection
COLLECTION_KEYWORDS = {
    "sops": [
        r"\bsop\b", r"\bprocedure\b", r"\bstandard\b", r"\bprocess\b",
        r"\bprotocol\b", r"\bguideline\b", r"\bdocument\b", r"\bpolicy\b",
        r"\bworkflow\b", r"\binstruction\b", r"\bmanual\b", r"\bhandbook\b",
        r"\beffective\b", r"\bdepartment\b", r"\bversion\b",
    ],
    "deviations": [
        r"\bdeviation\b", r"\bdev\b", r"\bincident\b", r"\bviolation\b",
        r"\bfailure\b", r"\bbreach\b", r"\broot cause\b", r"\bimpact\b",
        r"\boccurred\b", r"\bnon.?conformance\b", r"\bopen deviation\b",
        r"\bclosed deviation\b", r"\bcritical\b", r"\bmajor\b", r"\bminor\b",
    ],
    "capas": [
        r"\bcapa\b", r"\bcorrective\b", r"\bpreventive\b", r"\baction\b",
        r"\bfix\b", r"\bremediation\b", r"\bimprovement\b", r"\bimplementation\b",
        r"\bowner\b", r"\bdue date\b", r"\beffectiveness\b",
    ],
    "audits": [
        r"\baudit\b", r"\bfinding\b", r"\binspection\b", r"\bobservation\b",
        r"\bassessment\b", r"\bannex\b", r"\bregulator\b", r"\bgdp\b",
        r"\bgmp\b", r"\bfda\b", r"\biso\b", r"\bcompliance\b",
    ],
    "decisions": [
        r"\bdecision\b", r"\bmanagement\b", r"\bapproval\b", r"\bsuspension\b",
        r"\bbudget\b", r"\bescalation\b", r"\bresolution\b", r"\bmandate\b",
        r"\bauthorization\b", r"\bzero.?trust\b",
    ],
}

# Phrases that trigger ALL collections
ALL_TRIGGERS = [
    r"\ball\b", r"\beverything\b", r"\bfull\b", r"\boverview\b",
    r"\bsummary\b", r"\brelated\b", r"\blinked\b", r"\bconnected\b",
    r"\bshow me\b", r"\btell me about\b",
]


def route_query(query: str) -> List[str]:
    """
    Returns the list of collection keys to search for the given query.
    e.g. ["sops"] or ["deviations", "capas"] or ["sops","deviations","capas","audits","decisions"]
    """
    q = query.lower()

    # Check if the query is very broad
    for pattern in ALL_TRIGGERS:
        if re.search(pattern, q):
            return ["sops", "deviations", "capas", "audits", "decisions"]

    # Score each collection by keyword matches
    scores = {}
    for section, patterns in COLLECTION_KEYWORDS.items():
        hits = sum(1 for p in patterns if re.search(p, q))
        if hits > 0:
            scores[section] = hits

    if not scores:
        # No clear match — search all
        return ["sops", "deviations", "capas", "audits", "decisions"]

    if len(scores) == 1:
        return list(scores.keys())

    # If multiple, return top 2 by score
    sorted_sections = sorted(scores, key=lambda k: scores[k], reverse=True)
    return sorted_sections[:2]


def describe_route(sections: List[str]) -> str:
    """Human-readable description of which collections will be searched."""
    label_map = {
        "sops":       "SOPs",
        "deviations": "Deviations",
        "capas":      "CAPAs",
        "audits":     "Audit Findings",
        "decisions":  "Decisions",
    }
    return " + ".join(label_map.get(s, s) for s in sections)
