"""Narrow deterministic checks for known misleading business-hours inferences."""
import re


def unsupported_hours_claim(text, support):
    daily = r'\b(daily|every day|seven days|7 days)\b'
    claimed_daily = r'\b(open daily|daily service|daily opening|operates daily|every day|seven days|7 days)\b'
    if re.search(claimed_daily, text, re.IGNORECASE) and not re.search(
        daily + r'|monday\s*(?:-|–|through|to)\s*sunday', support, re.IGNORECASE
    ):
        return True
    permanent = r'\b(permanently closed|permanent closure|closing permanently|ceased operations|shut down)\b'
    return bool(re.search(permanent, text, re.IGNORECASE) and not re.search(permanent, support, re.IGNORECASE))
