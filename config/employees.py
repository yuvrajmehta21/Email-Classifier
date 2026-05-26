"""
Employee allowlist used by the daily-summary tool to group emails by named
person. Matching is case-insensitive substring against Graph display names
(from.emailAddress.name and toRecipients[].emailAddress.name — CC is
intentionally excluded) and against the first body line when it starts with
a greeting like "Hi <name>".
"""

EMPLOYEES = [
    "Gulshan",
    "Rashmi",
    "Pradeep",
    "Amit",
    "Srivastava",
    "Neetu",
    "Pankaj",
    "Indra",
    "Bharti",
    "Piyush",
    "Shaji",
    "Vikram Mehta",
]

GREETING_PREFIXES = ("hi", "hello", "dear")
