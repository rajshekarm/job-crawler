ROLE_KEYWORDS = [
    "software engineer",
    "software developer",
    "swe",
    "sde",
    "full stack",
    "backend engineer",
    "software",
    "developer",
    "engineer"
]

def is_role_match(text: str):
    if not text:
        return False
    t = text.lower()
    return any(k in t for k in ROLE_KEYWORDS)


def best_match_query():
    """
    Always use a general but strong search term.
    """
    return "software engineer"
