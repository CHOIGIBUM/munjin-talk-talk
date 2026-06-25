"""Domain-managed agenda category inference for patient questions."""

from __future__ import annotations

import re

from domain_config import agenda_category_rules
from utils import clean_quote


def infer_agenda_category(text: str, current_category: str = "other") -> str:
    """Return a specific agenda category when domain rules match the question text."""
    category = clean_quote(current_category or "other")
    if category and category != "other":
        return category

    normalized = re.sub(r"\s+", " ", clean_quote(text)).strip()
    if not normalized:
        return category or "other"

    for rule in agenda_category_rules():
        rule_category = clean_quote(rule.get("category") or "")
        groups = rule.get("all_of") or []
        if not rule_category or not isinstance(groups, list):
            continue
        if all(_matches_any_token(normalized, group) for group in groups if isinstance(group, list)):
            return rule_category
    return category or "other"


def _matches_any_token(text: str, tokens: list[str]) -> bool:
    return any(clean_quote(token) and clean_quote(token) in text for token in tokens)
