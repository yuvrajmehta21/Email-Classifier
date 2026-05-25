"""
Domain lists used by pre_classify.py.

Edit these by hand as the client reports new senders. Comparisons happen on
the lower-cased domain only (no path, no subdomain stripping).
"""

# Mailbox owner — the "you" the classifier checks for in the To field and body.
VIKRAM_EMAIL = "vikram@conceptclothing.co.in"
VIKRAM_NAMES = ["vikram", "vikram mehta", "sir"]

# Buyer / Internal domains. Anything matched here drives the AI prompt's
# sender_type field, which in turn controls the addressed_to_me logic.
DOMAIN_LIST = [
    {"domain": "groupe-beaumanoir.com", "type": "Buyer"},
    {"domain": "continuumba.com", "type": "Buyer"},
    {"domain": "itxsi.com", "type": "Buyer"},
    {"domain": "inditex.com", "type": "Buyer"},
    {"domain": "lfsourcing.com", "type": "Buyer"},
    {"domain": "montrosedel.com", "type": "Buyer"},
    {"domain": "shoulder.com.br", "type": "Buyer"},
    {"domain": "onequince.com", "type": "Buyer"},
    {"domain": "deepwear.info", "type": "Buyer"},
    {"domain": "voguesourcing.co.uk", "type": "Buyer"},
    {"domain": "elcorteingles.es", "type": "Buyer"},
    {"domain": "kuhl.com", "type": "Buyer"},
    {"domain": "pullbear.com", "type": "Buyer"},
    {"domain": "stradivarius.com", "type": "Buyer"},
    {"domain": "tjx.com", "type": "Buyer"},
    {"domain": "ovs.it", "type": "Buyer"},
    {"domain": "conceptclothing.co.in", "type": "Internal"},
    {"domain": "styleisland.com", "type": "Internal"},
]

# Hard overrides — these bypass content classification and force a label.
ALWAYS_PROMOTIONAL = [
    "nsdl.com",
]

ALWAYS_MISCELLANEOUS = [
    "nesl.co.in",
    "wrapcompliance.org",
]

BBG_ROXY_DOMAINS = [
    "boardriders.com.tw",
    "boardriders.co.jp",
    "bhaus.co.il",
    "actionbrandslatam.com",
    "boardriders.mx",
    "quiksilver.com.ar",
    "olgar.com.tr",
    "ccc.eu",
    "brkcompany.kr",
    "boardriders.co.za",
]
