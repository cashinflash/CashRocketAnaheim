"""Sign-guarded rule engine.

Two pure functions — `classify_credit` and `classify_debit` — with no
shared keyword lists. The only way to reach a debit category is through
`classify_debit`, so Jorge's LA-Finance sign bug (debit keyword matched
against a credit) is structurally impossible.

Resolution order per direction:
    1. Description preprocessor — strip ACH prefixes, confirmation IDs,
       trailing dates/locations so keyword match sees the semantic core
    2. Registry lookup (entities.json + entities_overrides.json)
    3. TYPE-OF-TRANSACTION keywords (fees, ATM, transfers, P2P) — fire
       first so "ATM withdrawal at 7-Eleven" doesn't get classified as
       groceries by a merchant keyword
    4. Merchant-specific keywords
    5. Claude/Plaid category hint as last-resort fallback, SIGN-GUARDED
    6. Return "unclassified" (never a silent default)

Every returned tuple is (category, rule_name) for audit.
"""

import re

from .registry import category_for


# ─────────────────────────────────────────────────────────────────────────────
# DESCRIPTION PREPROCESSOR
# Strips the noise that causes false-negatives / false-positives in keyword
# matching. Keeps the original description on the transaction for display.
# ─────────────────────────────────────────────────────────────────────────────

# ACH / bank prefix tokens that appear at start of description and carry no
# semantic value once the merchant is identified.
_ACH_PREFIXES = [
    r"^PPD\s+",      # Prearranged payment
    r"^WEB\s+",      # Web-initiated ACH
    r"^RTP\s+CREDIT\s+",   # Real-time payment credit
    r"^RTP\s+",
    r"^CCD\s+",      # Corporate credit/debit
    r"^TEL\s+",      # Telephone
    r"^ACH\s+",
    r"^POS\s+DEBIT\s+",
    r"^DD\s+",       # Direct deposit / DoorDash — ambiguous, but usually safe
    r"^ORIG\s+CO\s+NAME:\s*",  # e.g. "ORIG CO NAME:Bright Money"
    r"^CO\s+ENTRY\s+DESCR:\s*",
]

_ACH_PREFIX_RE = re.compile("|".join(_ACH_PREFIXES), re.IGNORECASE)

# Noise tokens that appear at END of description.
# Order matters: longest/most-specific first so we strip layer by layer.
_TRAILING_NOISE_PATTERNS = [
    # Bank ABA/contract numbers (e.g., "ABA/CONTR BNK-121000248")
    r"\s+ABA/CONTR\s+BNK-?\s*\d{9,}.*$",
    r"\s+BNK-?\s*\d{9,}.*$",
    # WEB ID: 1234567890 / IND ID: 1234567890 / PPD ID: 1234567890
    r"\s+(?:WEB|IND|PPD|CCD|ACH|ARC)\s+ID:?\s*[A-Z0-9]+.*$",
    # Confirmation# XXXXX12345
    r"\s+Confirmation#?\s*[A-Z0-9]+.*$",
    r"\s+Conf#?\s*[A-Z0-9]+.*$",
    # Trailing confirmation-looking code: ≥8 chars, must contain at least
    # one digit AND one letter (so "REPAYMENT", "WITHDRAWAL", "PAYROLL" are
    # preserved while "XXXXX12345", "SA22Ebf", "1776361711" are stripped).
    r"\s+(?=[A-Z0-9]*\d)(?=[A-Z0-9]*[A-Z])[A-Z0-9]{8,}\s*$",
    # Long all-digit transaction IDs (e.g., "PPD Tilt 1004694740")
    r"\s+\d{9,}\s*$",
    # MM/DD or MM/DD/YY at end
    r"\s+\d{1,2}/\d{1,2}(?:/\d{2,4})?\s*$",
    # "EFFECTIVE MM/DD"
    r"\s+EFFECTIVE\s+\d{1,2}/\d{1,2}\s*$",
]

_TRAILING_COMPILED = [re.compile(p, re.IGNORECASE) for p in _TRAILING_NOISE_PATTERNS]

# Abbreviation expansion — helps with varied descriptions
_ABBREVIATIONS = [
    (re.compile(r"\bWDRL\b", re.IGNORECASE), "WITHDRAWAL"),
    (re.compile(r"\bWD\b", re.IGNORECASE), "WITHDRAWAL"),
    (re.compile(r"\bDEP\b", re.IGNORECASE), "DEPOSIT"),
    (re.compile(r"\bXFER\b", re.IGNORECASE), "TRANSFER"),
    (re.compile(r"\bTRSFR\b", re.IGNORECASE), "TRANSFER"),
    (re.compile(r"\bPMT\b", re.IGNORECASE), "PAYMENT"),
    (re.compile(r"\bPYMT\b", re.IGNORECASE), "PAYMENT"),
    (re.compile(r"\bRETRY\b", re.IGNORECASE), "RETRY"),  # preserve
]


def normalize_description(desc: str) -> str:
    """Return a cleaned description for classification. Original unchanged."""
    if not desc:
        return ""
    s = desc.strip()
    # Strip ACH prefixes
    s = _ACH_PREFIX_RE.sub("", s).strip()
    # Strip trailing noise in a loop (multiple layers can stack)
    for _ in range(4):
        prev = s
        for pat in _TRAILING_COMPILED:
            s = pat.sub("", s).strip()
        if s == prev:
            break
    # Expand abbreviations
    for pat, repl in _ABBREVIATIONS:
        s = pat.sub(repl, s)
    # Collapse whitespace
    s = re.sub(r"\s+", " ", s).strip()
    return s


# ─────────────────────────────────────────────────────────────────────────────
# TYPE-OF-TRANSACTION KEYWORDS (fire BEFORE merchant keywords)
# These are unambiguous transaction types — location/merchant is irrelevant.
# "ATM withdrawal at 7-Eleven" is an ATM transaction, not groceries.
# ─────────────────────────────────────────────────────────────────────────────

FEE_KEYWORDS = [
    "overdraft fee", "overdraft item fee", "nsf fee", "insufficient funds",
    "returned item", "returned check", "return fee", "stop payment fee",
    "monthly maintenance", "monthly service fee", "service fee",
    "atm fee", "non-wf atm fee", "non-wells fargo atm fee", "foreign fee",
    "wire fee", "paper statement fee", "late fee", "cash advance fee",
]

ATM_KEYWORDS_DEBIT = [
    "atm withdrawal", "atm wdrl", "atm wd", "cash withdrawal",
    "non-wf atm", "non-wells fargo atm", "atm debit",
]

ATM_KEYWORDS_CREDIT = [
    "atm cash deposit", "atm dep", "cash deposit", "branch deposit",
]

INTERNAL_TRANSFER_KEYWORDS = [
    "online transfer to", "online transfer from",
    "way2save", "savings xfer", "savings transfer",
    "automatic transfer", "auto xfer", "internal transfer",
    "online banking transfer", "keepthechange", "keep the change",
    "varotrsfr", "varo transfer", "chk 2257", "chk2257",
    # Fintech-to-bank transfers (applicant moving money between their own
    # accounts). These are NOT income and NOT expenses — just self-shuffling.
    # The Jairo Canas case: all credits on his traditional bank were "Chime
    # transfer" / "Moved from Chime" because his payroll hit Chime and he
    # transferred a portion to this account. Classifying these as
    # internal_transfer keeps them out of verified income AND lets the
    # multi-account aggregator dedupe them against the matching Chime debits.
    "chime transfer", "moved from chime", "transfer from chime", "to chime",
    "from chime", "chime deposit", "chime withdrawal",
    "cash app transfer", "cashapp transfer", "transfer from cash app",
    "transfer to cash app", "from cash app", "to cash app",
    "venmo transfer", "transfer from venmo", "transfer to venmo",
    "paypal transfer", "transfer from paypal", "transfer to paypal",
    "apple cash transfer",
    "moved from", "moved to",  # generic Plaid-style "Moved from X" wording
    # Chime Credit Builder secured-card internal movements. Chime labels
    # these "Card Payment from Secured Account" / "Credit Builder payment".
    # They're money shuffling between the applicant's own Chime accounts
    # (deposit → secured card or back). NOT external income or real spending.
    "card payment from secured account", "secured account",
    "credit builder payment", "chime credit builder",
]

P2P_SENT_KEYWORDS = [
    "zelle to", "zelle payment to", "venmo to", "cashapp to",
    "apple cash sent", "paypal sent", "paypal to",
    "remitly", "xoom", "western union", "wu payment", "moneygram",
    "ria financial", "wise transfer", "apple cash sent money",
    # Bank-truncated Zelle variants (Chase/BoA etc. write "ZEL*" for Zelle)
    "faster payments zel", "withdrawal faster payments",
    "zel to", "zelle ",
]

P2P_RECEIVED_KEYWORDS = [
    "zelle from", "zelle payment from", "venmo from", "cashapp from",
    "apple cash received", "paypal received", "paypal from",
    # Bank-truncated Zelle variants
    "faster payments zel", "deposit faster payments",
    "zel from", "zelle ",
]

MOBILE_DEPOSIT_KEYWORDS = ["mobile deposit", "mobile chk", "check deposit", "remote deposit"]


# ─────────────────────────────────────────────────────────────────────────────
# MERCHANT KEYWORDS (fire after type-of-transaction)
# ─────────────────────────────────────────────────────────────────────────────

PAYROLL_KEYWORDS = [
    "payroll", "paychk", "paycheck", "direct dep", "dir dep", "dirdep",
    "salary", "wages", "employer", "kaiser payroll", "adp payroll",
    "gusto", "paychex", "intuit quickbooks", "rippling", "paylocity",
    "workday", "ukg", "runpayroll",
    "kern supt school", "la county payroll", "terraza court", "lausd payroll",
]

GOVT_BENEFITS_KEYWORDS = [
    "ssa treas", "social security", "ssi payment", "ssdi",
    "federal benefit",  # US Bank labels SS direct deposits as "Federal Benefit Credit"
    "va benefits", "va treas", "veterans", "disability payment",
    "edd", "unemployment", "ui benefits", "pua",
    "irs treas", "tax refund", "irs refund", "state refund",
    "franchise tax board", "ftb", "child tax credit",
    "pension", "retirement",
    "snap benefits", "ebt", "calfresh", "tanf", "wic",
]

CHILD_SUPPORT_KEYWORDS = ["child support", "csd treasury", "csda", "child sup"]

GIG_INCOME_KEYWORDS = [
    "uber pro card", "uber driver", "lyft driver", "lyft pay",
    "doordash dasher", "doordash driver", "ddpay", "grubhub driver",
    "instacart shopper", "shopper earnings", "postmates driver",
    "rover earnings", "wag earnings", "taskrabbit", "fiverr payout",
    "upwork payout", "etsy payout", "square payout", "stripe payout",
    "venmo business", "paypal business",
]

RENT_KEYWORDS = [
    "rent payment", "rental payment", "property mgmt", "property management",
    "apartments", "leasing", "greystar", "camden", "udr", "aimco",
    "mid-america", "invitation homes", "rentcafe", "paylease",
    "rentpayment", "zego", "appfolio", "rocky top rentals",
    "avalon", "essex", "equity residential", "airbnb hosting",
]

UTILITIES_KEYWORDS = [
    "electric", "edison", "pge", "pg&e", "sdg&e", "sce", "con ed",
    "duke energy", "dominion energy", "ladwp", "dwp", "socal gas",
    "gas co bill", "water bill", "sewer", "oildale mutual",
]

PHONE_KEYWORDS = [
    "t-mobile", "tmobile", "verizon", "att wireless", "at&t mob", "at&t wi",
    "sprint", "cricket", "metropcs", "metro by t-mobile", "straighttalk",
    "mint mobile", "google fi", "us cellular", "boost mobile",
]

INTERNET_KEYWORDS = [
    "spectrum", "comcast", "xfinity", "cox comm", "att uverse", "frontier",
    "centurylink", "optimum", "wow!", "starlink", "fios",
]

INSURANCE_KEYWORDS = [
    "state farm", "geico", "progressive", "allstate", "farmers insurance",
    "aaa ca insurance", "aaa insurance", "liberty mutual", "travelers",
    "usaa insurance", "nationwide insurance", "mercury insurance",
    "the general insurance", "safeco", "esurance", "root insurance", "metromile",
    "kaiser permanente", "blue cross", "blue shield", "anthem", "aetna",
    "health insurance", "dental plan", "life insurance",
]

GROCERY_KEYWORDS = [
    "ralphs", "vons", "albertsons", "safeway", "kroger", "food 4 less",
    "food4less", "superior grocers", "stater bros", "whole foods",
    "trader joe", "sprouts", "walmart grocery", "target grocery", "aldi",
    "smart & final", "costco whse", "sam's club", "el super", "cardenas",
    "northgate", "vallarta", "winco foods", "publix", "heb",
    "gas n liquor", "anthony's food", "el carrusel", "little caesars pizza",
]

GAS_FUEL_KEYWORDS = [
    "arco", " 76 ", "chevron", "shell oil", "mobil ", "exxon", "bp oil",
    "costco gas", "sams gas", "circle k", "speedway", "valero",
    "phillips 66", "sinclair", "ampm", "am pm", "conoco", "texaco",
]

RESTAURANT_KEYWORDS = [
    "starbucks", "mcdonald", "jack in the box", "chick fil", "in-n-out", "in n out",
    "chipotle", "taco bell", "subway", "panda express", "el pollo loco",
    "wingstop", "jersey mike", "jimmy john", "five guys", "shake shack",
    "kfc", "popeyes", "raising cane", "del taco", "carl jr", "hardee",
    "doordash", "ubereats", "uber eats", "grubhub", "postmates",
    "maya cinemas", "krispy kreme", "dave's hot chicken", "mariscos",
    "molcasalsa", "dominos", "pizza hut", "papa john",
]

SUBSCRIPTION_KEYWORDS = [
    "netflix", "hulu", "disney plus", "disney+", "peacock", "paramount+",
    "hbo max", "apple tv", "amazon prime", "prime video",
    "spotify", "apple music", "youtube premium", "pandora",
    "apple.com/bill", "apple com bill", "icloud",
    "xbox", "playstation", "psn ", "nintendo", "gamepass",
    "audible", "kindle", "nytimes", "wsj", "wapo",
    "peloton", "planet fitness",
    "ring ai", "ring protect", "alarm.com",
    "verify credit", "credit karma", "experian ",
    "onlyfans", "patreon",
    "chatgpt", "openai", "claude subscription", "anthropic",
    "foreclosure.com", "public records",
]

LOAN_PAYMENT_KEYWORDS = [
    "westlake", "credit acceptance", "santander consumer", "ally auto",
    "capital one auto", "chrysler capital", "nissan motor", "toyota financial",
    "honda financial", "ford motor cr", "gm financial", "us bank auto",
    "bank of america auto", "wells fargo auto", "navient", "sallie mae",
    "nelnet", "great lakes", "mohela", "edfinancial", "ffel",
    "student loan", "studentloan",
    "synchrony", "discover payment", "discover card pmt", "american express",
    "amex epayment", "chase card", "chase epay", "capital one mobile payment",
    "capital one card", "capital one mobile pmt", "citi card", "citi payment",
    "barclays", "aspire credit",
    "aci westlake", "snap finance", "snaploan", "together loans",
    "flexible finance", "standard bow", "la-finance", "atlas financial",
    "atlasfinancial", "upstart network", "sunshine loan", "sunshineloan",
    "cross river bank", "possible finance payment",
]

FINTECH_REPAYMENT_KEYWORDS = [
    "earnin repayment", "earnin rpay", "brigit-com", "brigit protection",
    "dave inc", "dave.com", "cleo advance", "cleo ai",
    "empower repayment", "tilt advance", "tilt finance", "tilt cash advance",
    "moneylion", "instacash repayment", "ml plus",
    "klover", "albert advance", "floatme", "b9 advance",
    "payactiv", "dailypay", "gerald repayment", "joingerald",
    # MyPay (earned-wage-access). Deposits "MyPay advance", debits "MyPay
    # repayment" and "MyPay instant advance fees". Jairo Canas regression —
    # he had 6 advances + 2 repayments that were all sitting in other_credit /
    # other_expense which understated his fintech stacking count.
    "mypay", "my pay",
    "possible finance", "oppfi", "opp loans", "netcredit", "net credit",
    "credit genie", "creditgenie", "cg connect", "cg auth",
    "atm.com", "atm_com", "atm-com",
    "grant cash", "grant repay", "grant sub", "grant money", "oasiscre",
    "advance america", "money app",
    "klarna", "afterpay", "affirm", "zip pay", "quadpay",
]

MEDICAL_KEYWORDS = [
    "kaiser hospital", "sutter health", "dignity health", "scripps", "providence",
    "cedars-sinai", "cvs pharm", "walgreens pharm", "rite aid pharm",
    "kp scal", "mms lac usc", "quest diag", "labcorp",
    "urgent care", "dental office", "orthodont", "optometry",
]

TRANSPORTATION_KEYWORDS = [
    "uber trip", "lyft ride", "metro rail", "bart fare", "metrolink",
    "amtrak", "greyhound", "parking meter", "parkmobile", "spothero",
    "dmv ", "vehicle registration", "smog check",
]

CHILDCARE_KEYWORDS = [
    "daycare", "child care", "preschool", "after school", "kindercare",
    "bright horizons", "la petite", "primrose",
]

SPECULATIVE_KEYWORDS = [
    "casino", "gambl", "coinbase", "crypto.com", "binance", "kraken",
    "robinhood", "draftkings", "fanduel", "draft kings", "fan duel",
    "betmgm", "caesars sportsbook", "bovada", "online casino",
    "lotto", "scratcher", "powerball", "mega millions",
]

MONEY_ORDER_KEYWORDS = [
    "money order",
]


# ─────────────────────────────────────────────────────────────────────────────
# Helper
# ─────────────────────────────────────────────────────────────────────────────

def _any_keyword(description: str, keywords: list[str]) -> bool:
    desc_lower = description.lower()
    return any(kw.lower() in desc_lower for kw in keywords)


# ─────────────────────────────────────────────────────────────────────────────
# Category-hint fallback (Layer 2.5)
#
# When registry + keywords fail, try the `category` field the extractor
# already attached (Claude or Plaid pre-categorized). SIGN-GUARDED: we only
# accept hints whose direction matches the transaction direction, so a
# "loan_payment" hint on a credit transaction is ignored (that's the Jorge
# class of bug we never want to reintroduce).
# ─────────────────────────────────────────────────────────────────────────────

_HINT_CREDIT_OK = {
    "payroll", "gig_income", "govt_benefits", "pension", "child_support",
    "p2p_received", "fintech_advance", "loan_proceeds", "internal_transfer",
    "cash_deposit", "mobile_deposit", "account_verification",
    "bnpl_refund", "other_credit",
}

_HINT_DEBIT_OK = {
    "rent", "utilities", "phone", "internet", "insurance",
    "groceries", "gas_fuel", "restaurants", "subscriptions",
    "loan_payment", "fintech_repayment", "bnpl_payment",
    "atm", "money_order", "p2p_sent",
    "medical", "transportation", "childcare",
    "speculative", "internal_transfer", "fee",
    "account_verification", "other_expense",
}


# Plaid personal_finance_category.primary → our taxonomy (debit side)
_PLAID_PFC_DEBIT = {
    "LOAN_PAYMENTS": "loan_payment",
    "BANK_FEES": "fee",
    "TRANSFER_OUT": "internal_transfer",
    "RENT_AND_UTILITIES": "utilities",  # will get more specific via keywords
    "FOOD_AND_DRINK": "restaurants",
    "GENERAL_MERCHANDISE": "other_expense",
    "MEDICAL": "medical",
    "PERSONAL_CARE": "other_expense",
    "TRANSPORTATION": "transportation",
    "TRAVEL": "other_expense",
    "ENTERTAINMENT": "subscriptions",
    "HOME_IMPROVEMENT": "other_expense",
    "GOVERNMENT_AND_NON_PROFIT": "other_expense",
    "GENERAL_SERVICES": "other_expense",
}

# Plaid personal_finance_category.primary → our taxonomy (credit side)
_PLAID_PFC_CREDIT = {
    "INCOME": "payroll",
    "TRANSFER_IN": "internal_transfer",
}


def _hint_category(txn: dict, is_credit: bool) -> tuple[str, str] | None:
    """Try to derive a category from extractor-provided hints.
    Returns (category, rule_name) or None. Sign-guarded."""
    # Try Plaid's primary category first (richest signal)
    pfc = (txn.get("personal_finance_category") or {}).get("primary") if isinstance(txn.get("personal_finance_category"), dict) else None
    if not pfc:
        pfc = txn.get("plaid_pfc_primary") or ""
    if pfc:
        pfc_upper = str(pfc).upper().strip()
        mapping = _PLAID_PFC_CREDIT if is_credit else _PLAID_PFC_DEBIT
        hit = mapping.get(pfc_upper)
        if hit:
            return hit, f"plaid_pfc:{pfc_upper.lower()}"

    # Try the flat `category` field (Claude-assigned or Plaid-converted)
    cat = (txn.get("category") or "").lower().strip()
    if cat:
        ok = _HINT_CREDIT_OK if is_credit else _HINT_DEBIT_OK
        if cat in ok:
            return cat, f"hint:{cat}"

    # Try Plaid's `category` array (older shape)
    cat_arr = txn.get("plaid_category") or []
    if isinstance(cat_arr, list) and cat_arr:
        first = str(cat_arr[0]).upper().strip().replace(" ", "_")
        mapping = _PLAID_PFC_CREDIT if is_credit else _PLAID_PFC_DEBIT
        hit = mapping.get(first)
        if hit:
            return hit, f"plaid_cat:{first.lower()}"

    return None


# ─────────────────────────────────────────────────────────────────────────────
# Credit classifier
# ─────────────────────────────────────────────────────────────────────────────

def classify_credit(description: str, amount: float, txn: dict | None = None) -> tuple[str, str]:
    """Returns (category, rule_name). Never silent-defaults.

    `txn` is the full transaction dict so we can use Plaid/Claude hints
    as a fallback. Pass None if you only have description available.
    """
    norm = normalize_description(description)

    # 2.1 — registry (match against both original and normalized)
    category = category_for(description, is_credit=True)
    if category is not None:
        return category, "registry:credit"
    if norm and norm != description:
        category = category_for(norm, is_credit=True)
        if category is not None:
            return category, "registry:credit:normalized"

    # 2.2 — TYPE keywords first
    if _any_keyword(norm, ATM_KEYWORDS_CREDIT):
        return "cash_deposit", "keyword:cash_deposit"
    if _any_keyword(norm, MOBILE_DEPOSIT_KEYWORDS):
        return "mobile_deposit", "keyword:mobile_deposit"
    if _any_keyword(norm, P2P_RECEIVED_KEYWORDS):
        return "p2p_received", "keyword:p2p_received"
    if _any_keyword(norm, INTERNAL_TRANSFER_KEYWORDS):
        return "internal_transfer", "keyword:internal_transfer"

    # 2.3 — Merchant / source keywords
    if _any_keyword(norm, PAYROLL_KEYWORDS):
        return "payroll", "keyword:payroll"
    if _any_keyword(norm, GOVT_BENEFITS_KEYWORDS):
        return "govt_benefits", "keyword:govt_benefits"
    if _any_keyword(norm, CHILD_SUPPORT_KEYWORDS):
        return "child_support", "keyword:child_support"
    if _any_keyword(norm, GIG_INCOME_KEYWORDS):
        return "gig_income", "keyword:gig_income"

    # Generic Zelle/Venmo/etc "from" pattern
    if re.search(r"\b(zelle|venmo|cashapp|cash app|paypal|apple cash)\b.*\bfrom\b", norm, re.IGNORECASE):
        return "p2p_received", "keyword:p2p_from"

    # 2.5 — hint fallback (sign-guarded)
    if txn is not None:
        hint = _hint_category(txn, is_credit=True)
        if hint is not None:
            return hint[0], hint[1]

    return "unclassified", "no_rule_matched"


# ─────────────────────────────────────────────────────────────────────────────
# Debit classifier
# ─────────────────────────────────────────────────────────────────────────────

def classify_debit(description: str, amount: float, txn: dict | None = None) -> tuple[str, str]:
    """Returns (category, rule_name). Never silent-defaults."""
    norm = normalize_description(description)

    # 2.1 — registry
    category = category_for(description, is_credit=False)
    if category is not None:
        return category, "registry:debit"
    if norm and norm != description:
        category = category_for(norm, is_credit=False)
        if category is not None:
            return category, "registry:debit:normalized"

    # 2.2 — TYPE-OF-TRANSACTION keywords FIRST.
    # These are unambiguous transaction types regardless of merchant.
    # "ATM withdrawal at 7-Eleven" is an ATM transaction — NOT groceries.
    if _any_keyword(norm, FEE_KEYWORDS):
        return "fee", "keyword:fee"
    if _any_keyword(norm, ATM_KEYWORDS_DEBIT):
        return "atm", "keyword:atm"
    if _any_keyword(norm, INTERNAL_TRANSFER_KEYWORDS):
        return "internal_transfer", "keyword:internal_transfer"
    if _any_keyword(norm, P2P_SENT_KEYWORDS):
        return "p2p_sent", "keyword:p2p_sent"
    if _any_keyword(norm, MONEY_ORDER_KEYWORDS):
        return "money_order", "keyword:money_order"

    # 2.3 — Merchant-specific keywords (priority: housing/essentials first)
    if _any_keyword(norm, RENT_KEYWORDS):
        return "rent", "keyword:rent"
    if _any_keyword(norm, UTILITIES_KEYWORDS):
        return "utilities", "keyword:utilities"
    if _any_keyword(norm, PHONE_KEYWORDS):
        return "phone", "keyword:phone"
    if _any_keyword(norm, INTERNET_KEYWORDS):
        return "internet", "keyword:internet"
    if _any_keyword(norm, INSURANCE_KEYWORDS):
        return "insurance", "keyword:insurance"
    if _any_keyword(norm, FINTECH_REPAYMENT_KEYWORDS):
        return "fintech_repayment", "keyword:fintech_repayment"
    if _any_keyword(norm, LOAN_PAYMENT_KEYWORDS):
        return "loan_payment", "keyword:loan_payment"
    if _any_keyword(norm, MEDICAL_KEYWORDS):
        return "medical", "keyword:medical"
    if _any_keyword(norm, SUBSCRIPTION_KEYWORDS):
        return "subscriptions", "keyword:subscriptions"
    if _any_keyword(norm, TRANSPORTATION_KEYWORDS):
        return "transportation", "keyword:transportation"
    if _any_keyword(norm, CHILDCARE_KEYWORDS):
        return "childcare", "keyword:childcare"
    if _any_keyword(norm, GAS_FUEL_KEYWORDS):
        return "gas_fuel", "keyword:gas_fuel"
    if _any_keyword(norm, GROCERY_KEYWORDS):
        return "groceries", "keyword:groceries"
    if _any_keyword(norm, RESTAURANT_KEYWORDS):
        return "restaurants", "keyword:restaurants"
    if _any_keyword(norm, SPECULATIVE_KEYWORDS):
        return "speculative", "keyword:speculative"

    # 2.5 — hint fallback (sign-guarded)
    if txn is not None:
        hint = _hint_category(txn, is_credit=False)
        if hint is not None:
            return hint[0], hint[1]

    return "unclassified", "no_rule_matched"
