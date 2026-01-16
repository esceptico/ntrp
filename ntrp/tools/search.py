import re


def simplify_query(query: str) -> str:
    """Strip boolean operators, quotes, parentheses from complex queries."""
    simplified = re.sub(r"\s+OR\s+", " ", query, flags=re.IGNORECASE)
    simplified = re.sub(r"\s+AND\s+", " ", simplified, flags=re.IGNORECASE)
    simplified = simplified.replace('"', "").replace("'", "")
    simplified = simplified.replace("(", "").replace(")", "")
    simplified = re.sub(r"\s+", " ", simplified).strip()

    words = simplified.split()
    if len(words) > 6:
        simplified = " ".join(words[:5])

    return simplified
