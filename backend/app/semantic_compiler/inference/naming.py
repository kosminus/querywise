"""Tiny dependency-free English pluralizer for table-name matching."""


def plural_candidates(word: str) -> list[str]:
    """Plausible table names for a singular entity word, best-first."""
    candidates = [word + "s"]
    if word.endswith("y") and len(word) > 1 and word[-2] not in "aeiou":
        candidates.append(word[:-1] + "ies")
    if word.endswith(("s", "x", "z", "ch", "sh")):
        candidates.append(word + "es")
    candidates.append(word)  # already-plural or uncountable table names
    return candidates


def singularize(word: str) -> str:
    if word.endswith("ies") and len(word) > 3:
        return word[:-3] + "y"
    if word.endswith("ses") or word.endswith("xes") or word.endswith("zes"):
        return word[:-2]
    if word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word
