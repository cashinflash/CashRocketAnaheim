"""
Cash in Flash — Deterministic Decision Engine
Calculates FCF, applies risk adjustments, and makes the final loan decision.
100% consistent — same inputs always produce same outputs.
"""

import re
from collections import defaultdict, Counter
from datetime import datetime

# ══════════════════════════════════════════
# PLAID CATEGORY MAP
# Maps Plaid personal_finance_category.detailed
# strings to internal categories
# ══════════════════════════════════════════

PLAID_CATEGORY_MAP = {
    'INCOME_WAGES': 'payroll', 'INCOME_DIVIDENDS': 'other_credit',
    'INCOME_INTEREST_EARNED': 'other_credit', 'INCOME_RETIREMENT_PENSION': 'pension',
    'INCOME_TAX_REFUND': 'other_credit', 'INCOME_UNEMPLOYMENT': 'govt_benefits',
    'INCOME_GOVERNMENT_AND_NON_PROFIT': 'govt_benefits', 'INCOME_OTHER_INCOME': 'other_credit',
    'RENT_AND_UTILITIES_RENT': 'rent', 'RENT_AND_UTILITIES_GAS_AND_ELECTRICITY': 'utilities',
    'RENT_AND_UTILITIES_WATER': 'utilities', 'RENT_AND_UTILITIES_INTERNET_AND_CABLE': 'internet',
    'RENT_AND_UTILITIES_TELEPHONE': 'phone',
    'FOOD_AND_DRINK_GROCERIES': 'groceries', 'FOOD_AND_DRINK_RESTAURANT': 'restaurants',
    'FOOD_AND_DRINK_COFFEE': 'restaurants', 'FOOD_AND_DRINK_FAST_FOOD': 'restaurants',
    'FOOD_AND_DRINK_BEER_WINE_AND_LIQUOR': 'restaurants',
    'TRANSPORTATION_GAS': 'gas_fuel', 'TRANSPORTATION_PUBLIC_TRANSIT': 'transportation',
    'TRANSPORTATION_PARKING': 'transportation', 'TRANSPORTATION_TAXIS_AND_RIDE_SHARES': 'transportation',
    'LOAN_PAYMENTS_PERSONAL_LOAN_PAYMENT': 'loan_payment', 'LOAN_PAYMENTS_CAR_PAYMENT': 'loan_payment',
    'LOAN_PAYMENTS_CREDIT_CARD_PAYMENT': 'loan_payment', 'LOAN_PAYMENTS_MORTGAGE_PAYMENT': 'rent',
    'LOAN_PAYMENTS_STUDENT_LOAN': 'loan_payment',
    'TRANSFER_IN_CASH_ADVANCES_AND_LOANS': 'fintech_advance',
    'TRANSFER_OUT_ACCOUNT_TRANSFER': 'internal_transfer',
    'TRANSFER_IN_DEPOSIT': 'cash_deposit', 'TRANSFER_IN_ACCOUNT_TRANSFER': 'internal_transfer',
    'TRANSFER_SEND_PAYMENT': 'p2p_sent', 'TRANSFER_RECEIVE_PAYMENT': 'p2p_received',
    'INSURANCE_AUTO': 'insurance', 'INSURANCE_HEALTH': 'insurance', 'INSURANCE_LIFE': 'insurance',
    'MEDICAL_MEDICAL_SERVICES': 'medical', 'MEDICAL_PHARMACIES_AND_SUPPLEMENTS': 'medical',
    'GENERAL_MERCHANDISE_SUPERSTORES': 'other_expense', 'GENERAL_MERCHANDISE_DISCOUNT_STORES': 'other_expense',
    'GENERAL_MERCHANDISE_DEPARTMENT_STORES': 'other_expense',
    'ENTERTAINMENT_TV_AND_MOVIES': 'subscriptions', 'ENTERTAINMENT_MUSIC_AND_AUDIO': 'subscriptions',
    'ENTERTAINMENT_GAMES': 'subscriptions', 'ENTERTAINMENT_CASINOS_AND_GAMBLING': 'speculative',
    'ENTERTAINMENT_SPORTING_EVENTS_AMUSEMENT_PARKS_AND_MUSEUMS': 'other_expense',
    'BANK_FEES_OVERDRAFT': 'fee', 'BANK_FEES_ATM': 'fee', 'BANK_FEES_LATE_PAYMENT': 'fee',
    'PERSONAL_CARE_LAUNDRY_AND_DRY_CLEANING': 'other_expense',
    'PERSONAL_CARE_HAIR_AND_BEAUTY': 'other_expense',
    'GENERAL_SERVICES_ACCOUNTING_AND_FINANCIAL_PLANNING': 'other_expense',
    'GOVERNMENT_AND_NON_PROFIT_TAX_PAYMENT': 'other_expense',
}

# ══════════════════════════════════════════
# TRANSACTION CLASSIFIER
# Claude labels each transaction in Call 1.
# This engine uses Claude's labels directly.
# Fallback keyword matching is used only when
# Claude's label is missing or unrecognized.
# ══════════════════════════════════════════

# Income categories Claude assigns that count as verified income
VERIFIED_INCOME_CATEGORIES = {
    'payroll', 'gig_income', 'govt_benefits', 'pension', 'child_support'
}

# Categories where funds are real but source is unverifiable
UNVERIFIED_INCOME_CATEGORIES = {'cash_deposit', 'p2p_received'}

# Expense categories Claude assigns -> internal bucket mapping
EXPENSE_CATEGORY_MAP = {
    'rent':             'rent',
    'mortgage':         'rent',
    'utilities':        'utilities',
    'phone':            'utilities',
    'internet':         'utilities',
    'insurance':        'insurance',
    'groceries':        'groceries',
    'gas_fuel':         'gas',
    'restaurants':      'restaurants',
    'subscriptions':    'subscriptions',
    'loan_payment':     'loan_payment',
    'childcare':        'childcare',
    'transportation':   'transportation',
    'medical':          'medical',
    'atm':              'atm',
    'fintech_repayment':'fintech_repayment',
    'bnpl_payment':     'bnpl_payment',
    'internal_transfer':'internal_transfer',
    'p2p_sent':         'p2p_sent',
    'speculative':      'speculative',
    'fee':              'fee',
    'other_expense':    'other_expense',
    'money_order':      'money_order',
    'cash_deposit':     'cash_deposit',  # credit-side, handled separately
}

# Credit categories that are never income
EXCLUDED_CREDIT_CATEGORIES = {
    'fintech_advance', 'internal_transfer', 'p2p_received',
    'loan_proceeds', 'other_credit'
}


# ══════════════════════════════════════════
# PLAID JSON CONVERTER
# ══════════════════════════════════════════

def convert_plaid_to_extracted(plaid_json):
    """Convert Plaid asset report JSON to the extracted_data format the engine expects.

    Aggregates transactions across EVERY account the applicant connected (Jairo
    Canas regression — he connected a traditional bank + Chime; payroll was on
    Chime but the engine previously only processed the first account with any
    transactions, silently dropping the account where the real income lived).
    Balances/negative-days are summed across accounts so the picture matches
    what the applicant actually has.
    """
    report = plaid_json.get('report') or plaid_json.get('asset_report') or plaid_json
    items = report.get('items', [])
    if not items:
        print('[PLAID] No items found in asset report JSON')
        return None

    # Collect every account across every item
    all_accounts = []
    for item in items:
        for acc in item.get('accounts', []):
            all_accounts.append(acc)
    if not all_accounts:
        print('[PLAID] No accounts found in asset report JSON')
        return None

    # Aggregate across every account that has transactions
    plaid_txns = []
    total_current_balance = 0.0
    total_available_balance = 0.0
    holder_name = ''
    account_count_with_txns = 0
    account_summaries = []
    # Historical balance series aligned by date across accounts
    balance_by_date = {}  # date -> sum(current across all accounts on that date)

    for acc in all_accounts:
        acc_txns = acc.get('transactions', []) or []
        balances = acc.get('balances', {}) or {}
        historical = acc.get('historical_balances', []) or []
        acc_id = acc.get('account_id') or ''
        acc_name = acc.get('official_name') or acc.get('name') or 'Account'
        acc_subtype = acc.get('subtype') or acc.get('type') or ''

        # Tag each txn with its source account so we can de-duplicate internal
        # transfers and preserve provenance in the audit trail.
        for t in acc_txns:
            t['_cif_account_id'] = acc_id
            t['_cif_account_name'] = acc_name
            t['_cif_account_subtype'] = acc_subtype
            plaid_txns.append(t)

        total_current_balance += float(balances.get('current') or 0)
        total_available_balance += float(balances.get('available') or 0)

        for b in historical:
            d = b.get('date', '')
            cur = float(b.get('current') or 0)
            if d:
                balance_by_date[d] = balance_by_date.get(d, 0.0) + cur

        # Take holder name from the first account that has one
        if not holder_name:
            owners = acc.get('owners') or [{}]
            names = (owners[0] or {}).get('names', [])
            if names:
                holder_name = names[0]

        if acc_txns:
            account_count_with_txns += 1
        account_summaries.append({
            'id': acc_id,
            'name': acc_name,
            'subtype': acc_subtype,
            'txn_count': len(acc_txns),
            'current_balance': float(balances.get('current') or 0),
        })

    if not plaid_txns:
        print('[PLAID] Accounts present but no transactions across any of them')
        return None

    # Sort combined ledger chronologically so downstream reconciliation and
    # review queue work deterministically.
    plaid_txns.sort(key=lambda t: t.get('date') or '')

    print(f'[PLAID] Aggregated {len(plaid_txns)} transactions across {account_count_with_txns} of {len(all_accounts)} accounts',
          flush=True)

    # Statement period (min → max date across all accounts)
    dates = [t.get('date') for t in plaid_txns if t.get('date')]
    start_date = min(dates) if dates else ''
    end_date = max(dates) if dates else ''
    days = (datetime.strptime(end_date, '%Y-%m-%d') - datetime.strptime(start_date, '%Y-%m-%d')).days + 1 if start_date and end_date else 30

    # Negative days = any day the combined balance across all accounts is < 0.
    neg_days = sum(1 for d, bal in balance_by_date.items() if bal < 0)
    daily_bals = list(balance_by_date.values())
    avg_bal = (sum(daily_bals) / len(daily_bals)) if daily_bals else 0

    # NSF detection (Plaid tags overdrafts on the txn level — no change needed)
    nsf_count = 0
    for t in plaid_txns:
        pfc = t.get('personal_finance_category', {})
        if pfc.get('detailed', '') == 'BANK_FEES_OVERDRAFT':
            nsf_count += 1

    # Convert transactions
    transactions = []
    for t in plaid_txns:
        pfc = t.get('personal_finance_category', {})
        detailed = pfc.get('detailed', '')
        primary = pfc.get('primary', '')

        # Plaid amounts: positive = debit (money leaving), negative = credit (money coming in)
        plaid_amount = t.get('amount', 0)
        is_credit = plaid_amount < 0
        amount = abs(plaid_amount)

        # Map category
        category = PLAID_CATEGORY_MAP.get(detailed, '')
        if not category:
            # Try primary-level mapping
            primary_map = {
                'INCOME': 'other_credit', 'TRANSFER_IN': 'other_credit',
                'TRANSFER_OUT': 'internal_transfer', 'FOOD_AND_DRINK': 'restaurants',
                'GENERAL_MERCHANDISE': 'other_expense', 'ENTERTAINMENT': 'other_expense',
                'PERSONAL_CARE': 'other_expense', 'GENERAL_SERVICES': 'other_expense',
                'RENT_AND_UTILITIES': 'utilities', 'TRANSPORTATION': 'transportation',
                'LOAN_PAYMENTS': 'loan_payment', 'MEDICAL': 'medical',
                'INSURANCE': 'insurance', 'BANK_FEES': 'fee',
                'GOVERNMENT_AND_NON_PROFIT': 'other_expense',
            }
            category = primary_map.get(primary, 'other_expense' if not is_credit else 'other_credit')

        # Use Plaid's normalized merchant name for fintech detection
        merchant = t.get('merchant_name', '') or ''
        desc = t.get('original_description', '') or t.get('name', '') or ''
        # Truncate description to 80 chars
        if len(desc) > 80:
            desc = desc[:77] + '...'

        # Confidence: Plaid data is generally HIGH confidence
        confidence = 'high'

        # Flag large retail as potential money order
        if not is_credit and category in ('groceries', 'other_expense'):
            if amount >= 500 and any(k in desc.lower() for k in ['walmart', 'kroger', 'target', 'costco']):
                category = 'money_order'
                confidence = 'low'

        transactions.append({
            'date': t.get('date', ''),
            'description': desc,
            'amount': amount,
            'is_credit': is_credit,
            'category': category,
            'confidence': confidence,
            'merchant_name': merchant,
            'payment_channel': t.get('payment_channel', ''),
            'plaid_category': detailed,
            'account_id': t.get('_cif_account_id', ''),
            'account_name': t.get('_cif_account_name', ''),
            'account_subtype': t.get('_cif_account_subtype', ''),
        })

    # Combined beginning balance = earliest date's aggregated balance
    sorted_hist_dates = sorted(balance_by_date.keys())
    combined_beginning = balance_by_date[sorted_hist_dates[0]] if sorted_hist_dates else 0

    return {
        'transactions': transactions,
        'nsf_count': nsf_count,
        'negative_days': neg_days,
        'avg_daily_balance': round(avg_bal, 2),
        'statement_days': days,
        'account_closed': False,
        'fraud_indicators': False,
        'account_holder_name': holder_name,
        'connected_accounts': account_summaries,
        'connected_account_count': len(all_accounts),
        'beginning_balance': round(combined_beginning, 2),
        'ending_balance': round(total_current_balance, 2),
        'available_balance': round(total_available_balance, 2),
        'statement_start': start_date,
        'statement_end': end_date,
        'data_source': 'plaid_json',
    }


# ══════════════════════════════════════════
# FALLBACK KEYWORD CLASSIFIER
# ══════════════════════════════════════════

def classify_transaction_fallback(desc, is_credit, amount=0):
    """
    Fallback keyword classifier — used ONLY when Claude's label is missing.
    Claude's label takes priority always.
    """
    d = desc.lower()

    # Internal transfers — check first (highest priority)
    if any(k in d for k in ['secured deposit', 'from savings', 'to savings',
                              'chime savings', 'round up', 'internal transfer',
                              'transfer to chk', 'transfer from chk']):
        return 'internal_transfer'

    if is_credit:
        # Fintech advances
        if any(k in d for k in ['dave', 'brigit', 'earnin', 'moneylion', 'albert',
                                  'cleo', 'empower', 'tilt', 'mypay', 'my pay',
                                  'varo', 'klover', 'floatme', 'beem', 'b9',
                                  'spotme', 'gerald', 'payactiv', 'dailypay']):
            return 'fintech_advance'
        # P2P received
        if any(k in d for k in ['zelle', 'venmo', 'cashapp', 'paypal', 'apple cash']):
            return 'p2p_received'
        # Payroll
        if any(k in d for k in ['payroll', 'direct dep', 'salary', 'wages',
                                  'adp', 'paychex', 'gusto', 'ach credit']):
            return 'payroll'
        # Gig income
        if any(k in d for k in ['doordash', 'uber', 'lyft', 'instacart',
                                  'amazon flex', 'grubhub', 'shipt', 'taskrabbit']):
            return 'gig_income'
        # Government benefits
        if any(k in d for k in ['ssa', 'ssi', 'disability', 'edd',
                                  'unemployment', 'social security', 'calworks',
                                  'federal benefit', 'fed benefit', 'soc sec',
                                  'va benefit', 'va payment', 'treasury',
                                  'child support', 'calworks', 'snap',
                                  'ebt', 'tanf', 'welfare',
                                  'ihss', 'in-home support', 'in home support',
                                  'dpss', 'general relief', 'calfresh']):
            return 'govt_benefits'
        # Pension
        if any(k in d for k in ['pension', 'retirement', 'annuity', 'calpers',
                                  'opers', 'fers', 'tsp ']):
            return 'pension'
        return 'other_credit'

    else:
        # BNPL payments — dual-track (counted as expense AND fintech lender)
        if any(k in d for k in ['afterpay', 'sezzle', 'affirm', 'acima', 'sunbit',
                                  'cherry spv', 'pypl payin4', 'payin4', 'klarna',
                                  'zip shein', 'zip temu', 'zip best buy', 'quadpay',
                                  'perpay', 'zebit', 'flexshopper', 'splitit',
                                  'paytomorrow', 'together loans', 'wisetack',
                                  'breadpay', 'greensky', 'shop pay', 'laybuy',
                                  'koalafi', 'snap finance', 'snapfinance',
                                  'progressive leasing', 'proglease', 'katapult', 'smartpay']):
            return 'bnpl_payment'
        # Fintech repayments (cash advance / payday)
        if any(k in d for k in ['dave', 'brigit', 'earnin', 'moneylion', 'albert',
                                  'cleo', 'empower', 'tilt', 'mypay', 'my pay',
                                  'varo', 'klover', 'floatme', 'beem', 'b9',
                                  'jointrue', 'joint true',
                                  'grant subscrip', 'grant sub',
                                  'advance america', 'advance americ',
                                  'true finance', 'truefinance', 'repaymar',
                                  'enableloans', 'enable loans',
                                  'oasiscre',
                                  'speedy cash', 'speedy loan', 'speedycash',
                                  'ace cash', 'ace express', 'cashnetusa',
                                  'check into cash', 'checkngo', 'check n go',
                                  'oportun', 'sunshine loan', 'loanmart',
                                  'moneytree', 'money tree', 'rapidcash',
                                  'titlemax', 'rise credit', 'national payday',
                                  'net pay advance', 'maxlend', 'plain green',
                                  'mobiloans', 'fig loans', 'lendup', 'oppfi',
                                  'creditninja', 'jora credit']):
            return 'fintech_repayment'
        # Money order detection — must come BEFORE groceries
        RETAIL_MONEY_ORDER = ['walmart', 'wal-mart', 'wal mart', 'kroger', 'target', 'costco', 'western union', 'moneygram', 'money order']
        if any(k in d for k in RETAIL_MONEY_ORDER) and amount >= 200:
            return 'money_order'
        # P2P sent
        if any(k in d for k in ['zelle', 'venmo', 'cashapp', 'paypal', 'apple cash']):
            return 'p2p_sent'
        # Speculative
        if any(k in d for k in ['casino', 'gambling', 'lottery', 'draftkings',
                                  'fanduel', 'coinbase', 'binance', 'crypto']):
            return 'speculative'
        # Insurance
        if any(k in d for k in ['insurance', 'aaa ', 'geico', 'progressive',
                                  'state farm', 'allstate', 'farmers', 'usaa']):
            return 'insurance'
        # Rent
        if any(k in d for k in ['rent', 'lease', 'landlord', 'property mgmt']):
            return 'rent'
        # Utilities/Phone
        if any(k in d for k in ['t-mobile', 'tmobile', 'verizon', 'at&t',
                                  'cricket', 'metro pcs', 'metropcs', 'boost',
                                  'total wireless', 'mint mobile', 'visible',
                                  'sce ', 'socal gas', 'socalgas', 'ladwp',
                                  'pg&e', 'pge', 'sdge', 'edison',
                                  'spectrum', 'comcast', 'cox ', 'xfinity',
                                  'frontier comm', 'centurylink', 'optimum']):
            return 'utilities'
        # Groceries
        if any(k in d for k in ['food4less', 'food 4 less', 'el super',
                                  'walmart', 'wal-mart', 'wal mart',
                                  'kroger', 'vons', 'ralphs', 'stater',
                                  'aldi', 'trader joe', 'whole foods',
                                  'costco', 'smart final', 'smart & final',
                                  'winco', '99 ranch', 'h-e-b', 'heb ',
                                  'publix', 'safeway', 'albertsons',
                                  'food lion', 'piggly', 'sprouts',
                                  'grocery outlet']):
            return 'groceries'
        # Gas
        if any(k in d for k in ['chevron', 'shell oil', 'arco', 'mobil', 'exxon',
                                  'valero', 'circle k', 'ace fuels', 'bp ',
                                  'tmb oil', '76 ', 'phillips 66', 'speedway',
                                  'racetrac', 'murphy oil', 'quiktrip', 'wawa',
                                  'sheetz', 'pilot ', 'flying j', 'loves ',
                                  'sunoco', 'sinclair']):
            return 'gas_fuel'
        # Restaurants / Fast Food
        if any(k in d for k in ['mcdonald', 'jack in the box', 'taco bell',
                                  'burger king', 'wendy', 'subway', 'chick-fil',
                                  'popeyes', 'panda express', 'chipotle',
                                  'in-n-out', 'five guys', 'carl\'s jr',
                                  'del taco', 'el pollo', 'wingstop',
                                  'starbucks', 'dunkin', 'pizza hut',
                                  'domino', 'papa john', 'little caesars',
                                  'ihop', 'denny', 'applebee', 'chili',
                                  'olive garden', 'outback', 'red lobster',
                                  'luis pizza']):
            return 'restaurants'
        # Subscriptions
        if any(k in d for k in ['netflix', 'spotify', 'hulu', 'disney', 'adobe',
                                  'microsoft', 'icloud', 'youtube premium',
                                  'expressvpn', 'nordvpn', 'amazon prime']):
            return 'subscriptions'
        # Loan payments
        if any(k in d for k in ['capital one', 'synchrony', 'discover payment',
                                  'american express', 'upstart', 'atlas financial',
                                  'wilshire', 'pnm*consumer', 'loan payment']):
            return 'loan_payment'
        # ATM
        if 'atm' in d or 'cash withdrawal' in d:
            return 'atm'
        return 'other_expense'


# ══════════════════════════════════════════
# SMART P2P CLASSIFICATION
# ══════════════════════════════════════════

def _extract_p2p_recipient(desc):
    """Extract recipient name from P2P description."""
    d = desc.lower()
    # Zelle patterns: "Zelle payment to NAME for MEMO" or "Zelle to NAME"
    m = re.search(r'zelle\s+(?:payment\s+)?to\s+([a-z][a-z\s]{1,30}?)(?:\s+for\s|\s+conf|\s*$)', d)
    if m: return m.group(1).strip().title()
    # PayPal: "PAYPAL *merchant" or "PMNT SENT ... PayPal"
    m = re.search(r'paypal\s*\*\s*([a-z][a-z\s*]{1,25})', d)
    if m: return 'PayPal ' + m.group(1).strip().title()
    # Venmo/CashApp
    m = re.search(r'(?:venmo|cashapp)\s+(?:to\s+)?([a-z][a-z\s]{1,25})', d)
    if m: return m.group(1).strip().title()
    # Chime
    if 'chime payment sent' in d or 'chime' in d:
        return 'SELF_CHIME'
    # Generic "PMNT SENT ... NAME"
    m = re.search(r'pmnt\s+sent\s+\S+\s+(.+?)(?:\s+\w{2}\s*$|\s+\d)', d)
    if m: return m.group(1).strip().title()
    return desc[:30].strip()

def _extract_p2p_memo(desc):
    """Extract memo/purpose from Zelle description."""
    m = re.search(r'for\s+"([^"]+)"', desc, re.I)
    if m: return m.group(1).strip().lower()
    m = re.search(r'for\s+([^;]+?)(?:;|\s*conf|\s*$)', desc, re.I)
    if m and len(m.group(1).strip()) < 40: return m.group(1).strip().lower()
    return ''

def _categorize_from_memo(memo):
    """Determine expense category from Zelle memo text."""
    if not memo: return None
    m = memo.lower()
    if any(k in m for k in ['rent', 'lease', 'apartment', 'housing']): return 'rent'
    if any(k in m for k in ['loan', 'owe', 'payback', 'pay back', 'borrow']): return 'loan_payment'
    if any(k in m for k in ['bill', 'utilities', 'electric', 'water', 'gas bill', 'power']): return 'utilities'
    if any(k in m for k in ['kaiser', 'medical', 'doctor', 'hospital', 'pharmacy']): return 'medical'
    if any(k in m for k in ['food', 'dinner', 'lunch', 'groceries']): return 'restaurants'
    if any(k in m for k in ['insurance', 'premium']): return 'insurance'
    if any(k in m for k in ['childcare', 'daycare', 'babysit']): return 'childcare'
    return None

def classify_p2p_sent(p2p_sent_items, p2p_received_items, applicant_name):
    """
    Smart P2P classification using 5 rules:
    1. Self-transfers → exclude
    2. Reciprocal flows → net the amount
    3. Recurring/large → count as expense with memo-based category
    4. Memo parsing for categorization
    5. Small one-time → exclude

    Returns list of dicts with: desc, amount, date, counted, category, reason, confidence
    """
    results = []
    applicant_lower = (applicant_name or '').lower().split()
    applicant_first = applicant_lower[0] if applicant_lower else ''
    applicant_last = applicant_lower[-1] if len(applicant_lower) > 1 else ''

    # Group sent by recipient
    sent_by_recipient = defaultdict(list)
    for item in p2p_sent_items:
        recipient = _extract_p2p_recipient(item.get('desc', ''))
        sent_by_recipient[recipient].append(item)

    # Group received by sender
    received_by_sender = defaultdict(float)
    for item in p2p_received_items:
        d = item.get('desc', '').lower()
        m = re.search(r'(?:from|FROM)\s+([a-z][a-z\s]{1,30}?)(?:\s+on\s|\s+conf|\s*$)', d)
        sender = m.group(1).strip().title() if m else d[:30].strip()
        received_by_sender[sender] += item.get('amount', 0)

    for recipient, items in sent_by_recipient.items():
        total_sent = sum(i.get('amount', 0) for i in items)

        # Rule 1: Self-transfers
        r_lower = recipient.lower()
        is_self = (
            r_lower == 'self_chime' or
            'chime' in r_lower or
            (applicant_first and applicant_first in r_lower) or
            (applicant_last and len(applicant_last) > 2 and applicant_last in r_lower)
        )
        if is_self:
            for item in items:
                results.append({**item, 'counted': False, 'category': 'Self Transfer',
                    'reason': f'Self-transfer to {recipient} — excluded',
                    'confidence': 'high'})
            continue

        # Rule 2: Reciprocal netting
        received_total = received_by_sender.get(recipient, 0)
        # Also try fuzzy match on first name
        if not received_total:
            r_first = recipient.split()[0].lower() if recipient.split() else ''
            for sender, amt in received_by_sender.items():
                if r_first and r_first in sender.lower():
                    received_total = amt
                    break

        if received_total > 0:
            net = total_sent - received_total
            if net <= 0:
                for item in items:
                    results.append({**item, 'counted': False, 'category': 'Reciprocal P2P',
                        'reason': f'Reciprocal with {recipient}: sent ${total_sent:,.0f}, received ${received_total:,.0f} — net ${net:,.0f}, excluded',
                        'confidence': 'high'})
                continue
            else:
                # Count only the net outflow, spread across items proportionally
                ratio = net / total_sent if total_sent > 0 else 0
                for item in items:
                    memo = _extract_p2p_memo(item.get('desc', ''))
                    cat = _categorize_from_memo(memo) or 'other_expense'
                    net_amount = item['amount'] * ratio
                    results.append({**item, 'counted': True, 'amount': round(net_amount, 2),
                        'category': cat.replace('_', ' ').title(),
                        'reason': f'Net P2P to {recipient}: sent ${total_sent:,.0f} - received ${received_total:,.0f} = ${net:,.0f} net outflow',
                        'confidence': 'medium'})
                continue

        # Rule 3 + 4: Recurring or large — count as expense
        is_recurring = len(items) >= 2
        has_large = any(i.get('amount', 0) >= 300 for i in items)

        if is_recurring or has_large:
            for item in items:
                memo = _extract_p2p_memo(item.get('desc', ''))
                cat = _categorize_from_memo(memo) or 'other_expense'
                conf = 'medium' if memo else 'low'
                reason_parts = []
                if is_recurring: reason_parts.append(f'{len(items)}x recurring to {recipient}')
                if has_large: reason_parts.append(f'large payment (>=$300)')
                if memo: reason_parts.append(f'memo: "{memo}"')
                results.append({**item, 'counted': True, 'category': cat.replace('_', ' ').title(),
                    'reason': f'P2P expense: {", ".join(reason_parts)}',
                    'confidence': conf})
            continue

        # Rule 5: Small one-time — exclude unless >= $100 (flag for review)
        for item in items:
            if item.get('amount', 0) >= 100:
                results.append({**item, 'counted': False, 'category': 'P2P Sent',
                    'reason': f'One-time P2P ${item["amount"]:,.0f} to {recipient} — excluded but flagged for review',
                    'confidence': 'low'})
            else:
                results.append({**item, 'counted': False, 'category': 'P2P Sent',
                    'reason': f'Small one-time P2P to {recipient} — excluded',
                    'confidence': 'high'})

    return results


# ══════════════════════════════════════════
# MAIN DECISION ENGINE
# ══════════════════════════════════════════

def run_decision_engine(extracted_data, settings, overrides=None):
    """
    Main decision engine. Takes extracted transaction data and settings,
    returns a complete decision with all calculations shown.
    
    extracted_data: dict from Claude's extraction call or convert_plaid_to_extracted()
    settings: dict from Firebase/Rules Engine
    overrides: optional dict with 'transaction_overrides' list of {index, category} dicts
    """
    
    transactions = extracted_data.get('transactions', [])
    nsf_count = extracted_data.get('nsf_count', 0)
    negative_days = extracted_data.get('negative_days', 0)
    avg_daily_balance = extracted_data.get('avg_daily_balance', 0)
    statement_days = extracted_data.get('statement_days', 30)
    account_closed = extracted_data.get('account_closed', False)
    fraud_indicators = extracted_data.get('fraud_indicators', False)
    
    # Settings
    loan_min = settings.get('loanMin', 100)
    loan_max = settings.get('loanMax', 255)
    t1_amount = settings.get('t1Amount', 100)
    t2_amount = settings.get('t2Amount', 150)
    t3_amount = settings.get('t3Amount', 200)
    t1 = settings.get('t1Fcf', 200)
    t2 = settings.get('t2Fcf', 375)
    t3 = settings.get('t3Fcf', 500)
    t4 = settings.get('t4Fcf', 640)
    nsf_drop = settings.get('nsfDrop', 2)
    nsf_cap = settings.get('nsfCap', 4)
    nsf_dec = settings.get('nsfDecline', 5)
    ft_drop = settings.get('ftDrop', 5)
    ft_cap = settings.get('ftCap', 7)
    ft_dec = settings.get('ftDecline', 9)
    ft_abs = settings.get('ftAbs', 11)
    neg_cap = settings.get('negCap', 7)
    neg_dec = settings.get('negDecline', 10)
    spec_drop = settings.get('specDrop', 35)
    spec_cap = settings.get('specCap', 50)
    atm_threshold = settings.get('atmThreshold', 200)
    atm_pct = settings.get('atmPct', 30) / 100.0
    atm_count_all = settings.get('atmCountAll', True)
    # Expense floor
    expense_floor_on = settings.get('expenseFloorOn', True)
    expense_floor = settings.get('expenseFloor', 500)
    # Expense categories
    exp_rent = settings.get('expRent', True)
    exp_utilities = settings.get('expUtilities', True)
    exp_phone = settings.get('expPhone', True)
    exp_insurance = settings.get('expInsurance', True)
    exp_loans = settings.get('expLoans', True)
    exp_grocery = settings.get('expGrocery', True)
    exp_gas = settings.get('expGas', True)
    exp_subscriptions = settings.get('expSubscriptions', True)
    exp_childcare = settings.get('expChildcare', True)
    exp_restaurants = settings.get('expRestaurants', True)
    exp_transportation = settings.get('expTransportation', True)
    exp_medical = settings.get('expMedical', True)
    exp_other_threshold = settings.get('expOtherThreshold', 50)
    exp_speculative = settings.get('expSpeculative', True)
    # P2P settings
    p2p_received_mode = settings.get('p2pReceivedMode', 'exclude')  # exclude | recurring | all
    p2p_received_pct = settings.get('p2pReceivedPct', 50) / 100.0
    p2p_sent_mode = settings.get('p2pSentMode', 'recurring')  # exclude | recurring
    # Subscription & bounced
    sub_cap = settings.get('subCapPerMerchant', 2)
    bounced_on = settings.get('bouncedDetection', True)
    # Statement age
    ad_stale = settings.get('adStale', 'decline')
    stale_days = settings.get('staleDays', 30)
    # Behavioral
    velocity_on = settings.get('velocityOn', True)
    velocity_drop = settings.get('velocityDrop', 90) / 100.0
    velocity_cap = settings.get('velocityCap', 98) / 100.0
    endbal_on = settings.get('endBalOn', True)
    endbal_flag = settings.get('endBalFlag', 25)
    endbal_drop = settings.get('endBalDrop', 5)
    ft_dep_flag = settings.get('ftDep', 30) / 100.0
    ft_dep_cap = settings.get('ftDepCap', 60) / 100.0
    ad_single_check = settings.get('adSingleCheck', 'flag')
    ad_low_balance = settings.get('adLowBalance', 'flag')
    
    # Condition actions
    ad_no_income = settings.get('adNoIncome', 'decline')
    ad_closed = settings.get('adClosed', 'decline')
    ad_fraud = settings.get('adFraud', 'decline')
    ad_fcf = settings.get('adFcf', 'decline')
    ad_avg_bal = settings.get('adAvgBal', 'decline')

    # New settings
    fintech_fee_pct = settings.get('fintechFeePct', 15) / 100.0
    money_order_threshold = settings.get('moneyOrderThreshold', 200)
    dti_drop = settings.get('dtiDrop', 45) / 100.0
    dti_drop2 = settings.get('dtiDrop2', 60) / 100.0
    
    # ── STEP 1: Classify all transactions ──
    income_items = []
    expense_items = []
    fintech_apps_seen = set()   # unique app names — the real count
    fintech_count = 0           # will be set from unique apps after loop
    total_speculative = 0
    total_atm_large = 0
    total_fintech_full_repayment = 0  # Track full fintech repayment amounts for DTI

    # Build override map if present
    if overrides and overrides.get('transaction_overrides'):
        override_map = {o['index']: o for o in overrides['transaction_overrides']}
    else:
        override_map = {}

    # Known fintech app name -> normalized label for deduplication
    FINTECH_NAME_MAP = {
        'dave': 'Dave', 'dave.com': 'Dave', 'dave sub': 'Dave',
        'brigit': 'Brigit',
        'earnin': 'Earnin',
        'moneylion': 'MoneyLion',
        'klover': 'Klover',
        'albert': 'Albert',
        'cleo': 'Cleo',
        'floatme': 'FloatMe',
        'empower': 'Empower/Tilt', 'tilt': 'Empower/Tilt', 'tilt fka': 'Empower/Tilt', 'tilt finance': 'Empower/Tilt',
        'branch': 'Branch',
        'b9': 'B9',
        'spotme': 'SpotMe',
        'gerald': 'Gerald',
        'payactiv': 'Payactiv',
        'dailypay': 'DailyPay',
        'even': 'Even',
        'rain': 'Rain',
        'possible': 'Possible Finance',
        'opplo': 'OppLoans',
        'netcredit': 'NetCredit',
        'kora': 'Kora',
        'varo': 'Varo',
        'creditgenie': 'CreditGenie',
        'credit genie': 'CreditGenie',
        'moneytree': 'MoneyTree',
        'money tree': 'MoneyTree',
        'beem': 'Beem',
        'clair': 'Clair',
        'kikoff': 'Kikoff',
        'my pay': 'MyPay', 'mypay': 'MyPay',
        'chime spotme': 'SpotMe',
        # ── Cash in Flash commonly seen lenders ──
        'advance america': 'Advance America', 'advance americ': 'Advance America',
        'enableloans': 'Enable Loans', 'enable loans': 'Enable Loans',
        'grant cash': 'Grant', 'grant adv': 'Grant', 'grant repay': 'Grant',
        'oasiscre': 'Grant', 'oasis cre': 'Grant', 'grant sub': 'Grant', 'grant money': 'Grant',
        'money app': 'Money App', 'moneyapp': 'Money App',
        'true finance': 'True Finance', 'truefinance': 'True Finance', 'repaymar': 'True Finance',
        'jointrue': 'True Finance', 'joint true': 'True Finance',
        'bridgecrest': 'Bridgecrest', 'pybridgecrest': 'Bridgecrest',

        # ── Earned Wage Access / Payroll Advance ──
        'pay activ': 'PayActiv',
        'daily pay': 'DailyPay',
        'payfare': 'Payfare',
        'tapcheck': 'TapCheck',
        'rain instant': 'Rain',
        'wagestream': 'Wagestream',
        'flexwage': 'FlexWage',
        'instantpay': 'InstantPay',
        'zenefits': 'Zenefits',
        'gusto wallet': 'Gusto',
        'adp wisely': 'ADP Wisely',

        # ── Major cash advance / neobank apps ──
        'chime spotme': 'Chime SpotMe',
        'current': 'Current', 'current bank': 'Current',
        'one finance': 'ONE Finance', 'one account': 'ONE Finance',
        'sofi': 'SoFi',
        'step': 'Step',
        'greenlight': 'Greenlight',
        'copper': 'Copper',
        'oxygen': 'Oxygen',
        'majority': 'Majority',
        'zeta': 'Zeta',
        'first phase': 'First Phase',
        'extra card': 'Extra Card', 'extra debit': 'Extra Card',

        # ── Credit building / fintech lenders ──
        'credit genie': 'Credit Genie', 'cg connect': 'Credit Genie',
        'self lender': 'Self', 'self inc': 'Self',
        'loqbox': 'Loqbox',
        'net credit': 'NetCredit',
        'opp loans': 'OppLoans', 'oppfi': 'OppLoans', 'opportunity financial': 'OppLoans',
        'possible finance': 'Possible Finance', 'possible loan': 'Possible Finance',
        'fig loans': 'Fig Loans',
        'lendup': 'LendUp',
        'rise credit': 'Rise Credit',
        'elastic': 'Elastic',
        'loanmart': 'LoanMart',
        'world acceptance': 'World Finance', 'world finance': 'World Finance',
        'mariner finance': 'Mariner Finance',
        'oportun': 'Oportun',
        'lendly': 'Lendly',
        'money key': 'MoneyKey', 'moneykey': 'MoneyKey',

        # ── Payday / short-term lenders ──
        'speedy cash': 'Speedy Cash',
        'check into cash': 'Check Into Cash', 'checkngo': 'Check n Go', 'check n go': 'Check n Go',
        'ace cash': 'ACE Cash Express', 'ace express': 'ACE Cash Express',
        'cashnetusa': 'CashNetUSA', 'cash net usa': 'CashNetUSA',
        'lendnation': 'LendNation',
        'titlemax': 'TitleMax',
        'loanmax': 'LoanMax',
        'currency': 'Currency',
        'first cash': 'FirstCash',
        'ezmoney': 'EZMoney', 'ez money': 'EZMoney',
        'rapidcash': 'RapidCash', 'rapid cash': 'RapidCash',
        'national payday': 'National Payday',
        'tribal': 'Tribal Lender',

        # ── BNPL / installment apps ──
        'afterpay': 'Afterpay',
        'klarna': 'Klarna',
        'affirm': 'Affirm',
        'sezzle': 'Sezzle',
        'zip pay': 'Zip', 'zip.co': 'Zip', 'quadpay': 'Zip',
        'zip shein': 'Zip', 'zip temu': 'Zip', 'zip best buy': 'Zip',
        'splitit': 'Splitit',
        'paytomorrow': 'PayTomorrow',
        'acima': 'Acima',
        'sunbit': 'Sunbit',
        'cherry spv': 'Cherry', 'cherry credit': 'Cherry',
        'pypl payin4': 'PayPal Pay4', 'payin4': 'PayPal Pay4',
        'together loans': 'Together Loans',
        'cont finance': 'Continental Finance',
        'concora': 'Concora Credit',
        'mission lane': 'Mission Lane',
        'avant': 'Avant',
        'upstart': 'Upstart',
        'total card': 'Total Card',
        'revvi': 'Revvi', 'gcg/mrv': 'Revvi', 'mrv': 'Revvi',

        # ── BNPL expanded ──
        'perpay': 'Perpay',
        'zebit': 'Zebit',
        'flexshopper': 'FlexShopper',
        'wisetack': 'Wisetack',
        'breadpay': 'Bread Pay', 'bread financial': 'Bread Pay',
        'greensky': 'GreenSky',
        'shop pay': 'Shop Pay', 'shoppay': 'Shop Pay',
        'laybuy': 'Laybuy',
        'cuatro': 'Cuatro',
        'credova': 'Credova',
        'deferit': 'Deferit',
        # ── Additional payday lenders ──
        'sunshine loan': 'Sunshine Loans', 'sunshine loans': 'Sunshine Loans',
        'net pay advance': 'Net Pay Advance', 'netpayadvance': 'Net Pay Advance',
        'maxlend': 'MaxLend',
        'plain green': 'Plain Green Loans',
        'mobiloans': 'MobiLoans',
        'creditninja': 'CreditNinja', 'credit ninja': 'CreditNinja',
        'jora credit': 'Jora Credit',
        'covington credit': 'Covington Credit',
        'regional finance': 'Regional Finance',
        'security finance': 'Security Finance',
        'republic finance': 'Republic Finance',
        'tower loan': 'Tower Loan',
        'heights finance': 'Heights Finance',
        'speedy': 'Speedy Cash',
        'koalafi': 'Koalafi', 'koala fi': 'Koalafi',
        'snap finance': 'Snap Finance', 'snapfinance': 'Snap Finance',
        'progressive leasing': 'Progressive Leasing', 'proglease': 'Progressive Leasing',
        'katapult': 'Katapult', 'zibby': 'Katapult',
        'smartpay': 'SmartPay',
        # ── Robinhood / investment-linked credit ──
        'robinhood': 'Robinhood',
        # ── New additions ──
        'ml plus': 'MoneyLion', 'ml plus llc': 'MoneyLion',
        'same day credit': 'SameDayCredit', 'samedaycredit': 'SameDayCredit',
        'lucent cash': 'Lucent Cash',
        'postlakelend': 'PostLakeLend', 'post lake lend': 'PostLakeLend',
        'atlas debitcard': 'Atlas', 'atlas*debitcard': 'Atlas',
        'creditcube': 'CreditCube', 'credit cube': 'CreditCube',
        'concora credit': 'Concora Credit',
        'betrlink': 'BetrLink',
        'makwa finance': 'Makwa Finance', 'makwa': 'Makwa Finance',
        'vola': 'Vola',
        'grid*paymt': 'Grid', 'grid oakland': 'Grid',
    }

    def get_fintech_name(desc):
        """Extract normalized fintech app name from description. Returns None if not fintech."""
        d = desc.lower()
        for key, name in FINTECH_NAME_MAP.items():
            if key in d:
                return name
        return None

    for i, txn in enumerate(transactions):
        # Skip pending transactions from expense/income calculations
        # They will still be scanned separately for P2P risk flags
        if txn.get('pending') or txn.get('is_pending'):
            continue

        desc = txn.get('description', '')
        amount = abs(float(txn.get('amount', 0)))
        is_credit = txn.get('is_credit', False)
        date = txn.get('date', '')
        # Use Claude's label if provided, otherwise fallback
        claude_category = txn.get('category', '').lower().strip()

        # Apply override if present
        if i in override_map:
            claude_category = override_map[i].get('category', claude_category).lower().strip()

        if is_credit:
            # ── Cash deposit handling ──
            if claude_category == 'cash_deposit':
                income_items.append({
                    'date': date, 'desc': desc, 'amount': amount,
                    'category': 'Cash Deposit',
                    'counted': False,
                    'reason': 'Cash deposit — real funds but unverifiable source',
                    'confidence': txn.get('confidence', 'medium'),
                })
                continue

            # Determine income category — Claude's label takes priority
            if claude_category == 'ppd_unknown':
                # Unverified PPD deposit — track separately for second opinion scenario
                income_items.append({
                    'date': date, 'desc': desc, 'amount': amount,
                    'category': 'Ppd Unknown',
                    'counted': False,
                    'reason': 'PPD deposit from unrecognized employer — requires manual verification',
                    'confidence': txn.get('confidence', 'medium'),
                })
                continue
            elif claude_category in VERIFIED_INCOME_CATEGORIES:
                income_cat = claude_category
                counted = True
                reason = f'Verified {income_cat.replace("_"," ")} income (classified by AI)'
            elif claude_category == 'fintech_advance':
                income_cat = 'fintech_advance'
                counted = False
                app_name = get_fintech_name(desc) or 'Unknown Fintech'
                fintech_apps_seen.add(app_name)
                reason = f'Fintech/payday advance ({app_name}) — not verified income'
            elif claude_category == 'p2p_received' or (not claude_category and classify_transaction_fallback(desc, True, amount) == 'p2p_received'):
                income_cat = 'p2p_received'
                if p2p_received_mode == 'all':
                    counted = True
                    reason = f'P2P received — counted at {int(p2p_received_pct*100)}% per rules'
                    amount = amount * p2p_received_pct  # Apply discount
                else:
                    counted = False
                    reason = 'P2P transfer — excluded from income (recurring analysis shown separately)'
            elif claude_category in ('internal_transfer', 'loan_proceeds', 'tax_refund', 'other_credit', ''):
                # Claude said excluded — but check if fallback finds verified income
                fb = classify_transaction_fallback(desc, True, amount)
                if fb in VERIFIED_INCOME_CATEGORIES:
                    # Fallback found real income that Claude missed (e.g. "Federal Benefit Credit" → govt_benefits)
                    income_cat = fb
                    counted = True
                    reason = f'Verified {fb.replace("_"," ")} income (reclassified by keyword match)'
                else:
                    income_cat = claude_category or fb
                    counted = False
                    reason = 'Internal transfer, loan proceeds, or unverified source'
            else:
                # Fallback for unknown labels
                fb = classify_transaction_fallback(desc, True, amount)
                income_cat = fb
                counted = fb in VERIFIED_INCOME_CATEGORIES
                reason = f'Verified {fb} income' if counted else 'Unverified credit source'

            income_items.append({
                'date': date, 'desc': desc, 'amount': amount,
                'category': income_cat.replace('_', ' ').title(),
                'counted': counted,
                'reason': reason,
                'confidence': txn.get('confidence', 'medium'),
            })

        else:
            # Determine expense category — Claude's label takes priority
            if claude_category:
                mapped = EXPENSE_CATEGORY_MAP.get(claude_category, None)
                if mapped is None:
                    # Unknown label — use fallback
                    claude_category = classify_transaction_fallback(desc, False, amount)
                    mapped = EXPENSE_CATEGORY_MAP.get(claude_category, 'other_expense')
                elif mapped == 'other_expense':
                    # Claude said "other_expense" — check if fallback finds something more specific
                    fb = classify_transaction_fallback(desc, False, amount)
                    fb_mapped = EXPENSE_CATEGORY_MAP.get(fb, 'other_expense')
                    if fb_mapped != 'other_expense':
                        claude_category = fb
                        mapped = fb_mapped
            else:
                claude_category = classify_transaction_fallback(desc, False, amount)
                mapped = EXPENSE_CATEGORY_MAP.get(claude_category, 'other_expense')

            if mapped == 'fintech_repayment':
                app_name = get_fintech_name(desc) or 'Unknown Fintech'
                fintech_apps_seen.add(app_name)
                fee_amount = amount * fintech_fee_pct
                expense_items.append({
                    'date': date, 'desc': desc, 'amount': amount,
                    'counted_amount': fee_amount,
                    'category': f'Fintech App Repayment ({app_name})',
                    'counted': True,
                    'reason': f'Fintech repayment to {app_name} — ${amount:,.2f} x {int(fintech_fee_pct*100)}% fee = ${fee_amount:,.2f} counted',
                    'confidence': txn.get('confidence', 'medium'),
                })
                total_fintech_full_repayment += amount  # Track full amount for DTI
            elif mapped == 'bnpl_payment':
                # BNPL dual-track: counted as verified expense AND tracked as fintech lender
                app_name = get_fintech_name(desc) or 'BNPL'
                fintech_apps_seen.add(app_name)
                expense_items.append({
                    'date': date, 'desc': desc, 'amount': amount,
                    'category': f'BNPL Payment ({app_name})',
                    'counted': exp_loans,
                    'reason': f'BNPL installment to {app_name} — counted as expense and toward fintech lender total',
                    'confidence': txn.get('confidence', 'medium'),
                })
            elif mapped == 'money_order':
                expense_items.append({
                    'date': date, 'desc': desc, 'amount': amount,
                    'category': 'Money Order',
                    'counted': True,
                    'reason': 'Money order/money transfer at retail store',
                    'confidence': txn.get('confidence', 'low'),
                })
            elif mapped in ('internal_transfer', 'p2p_sent', 'fee'):
                expense_items.append({
                    'date': date, 'desc': desc, 'amount': amount,
                    'category': mapped.replace('_', ' ').title(),
                    'counted': False,
                    'reason': 'Internal transfer, P2P outflow, or fee — excluded (mirrors income rule)',
                    'confidence': txn.get('confidence', 'medium'),
                })
            elif mapped == 'speculative':
                total_speculative += amount
                expense_items.append({
                    'date': date, 'desc': desc, 'amount': amount,
                    'category': 'Speculative/Gambling',
                    'counted': exp_speculative,
                    'reason': 'Speculative activity — counted as expense and flagged' if exp_speculative else 'Speculative — excluded from expenses (still flagged for risk)',
                    'confidence': txn.get('confidence', 'medium'),
                })
            elif mapped == 'atm':
                if atm_count_all:
                    # Flat percentage mode: count ALL ATM at configured %
                    counted_amount = amount * atm_pct
                    expense_items.append({
                        'date': date, 'desc': desc, 'amount': amount,
                        'category': 'ATM Withdrawal',
                        'counted': atm_pct > 0,
                        'counted_amount': counted_amount,
                        'reason': f'ATM ${amount:,.2f} x {int(atm_pct*100)}% = ${counted_amount:.2f} counted',
                        'confidence': txn.get('confidence', 'medium'),
                    })
                elif amount >= atm_threshold:
                    total_atm_large += amount
                    counted_amount = amount * atm_pct
                    expense_items.append({
                        'date': date, 'desc': desc, 'amount': amount,
                        'category': 'ATM Withdrawal (Large)',
                        'counted': atm_pct > 0,
                        'counted_amount': counted_amount,
                        'reason': f'Large ATM (>=${atm_threshold}): counting {int(atm_pct*100)}% = ${counted_amount:.2f}',
                        'confidence': txn.get('confidence', 'medium'),
                    })
                else:
                    expense_items.append({
                        'date': date, 'desc': desc, 'amount': amount,
                        'category': 'ATM Withdrawal (Small)',
                        'counted': False,
                        'reason': f'Small ATM under ${atm_threshold} threshold — pocket money',
                        'confidence': txn.get('confidence', 'medium'),
                    })
            elif mapped == 'cash_deposit':
                # Credit-side category appearing on debit — treat as other_expense
                expense_items.append({
                    'date': date, 'desc': desc, 'amount': amount,
                    'category': 'Other Expense',
                    'counted': exp_other_threshold > 0 and amount >= exp_other_threshold,
                    'reason': 'Unclassified debit',
                    'confidence': txn.get('confidence', 'medium'),
                })
            else:
                # Regular verified expense — check if category is enabled in settings
                cat_enabled = {
                    'rent': exp_rent, 'utilities': exp_utilities or exp_phone,
                    'groceries': exp_grocery, 'gas': exp_gas,
                    'subscriptions': exp_subscriptions, 'loan_payment': exp_loans,
                    'insurance': exp_insurance, 'childcare': exp_childcare,
                    'restaurants': exp_restaurants, 'transportation': exp_transportation,
                    'medical': exp_medical,
                }
                if mapped == 'other_expense':
                    # Count other_expense above threshold, exclude small unknowns
                    counted = exp_other_threshold > 0 and amount >= exp_other_threshold
                    reason = (f'Other expense >=${exp_other_threshold} — counted' if counted
                              else f'Other expense below ${exp_other_threshold} threshold — excluded')
                    expense_items.append({
                        'date': date, 'desc': desc, 'amount': amount,
                        'category': (claude_category or mapped).replace('_', ' ').title(),
                        'counted': counted, 'reason': reason,
                        'confidence': txn.get('confidence', 'medium'),
                    })
                else:
                    enabled = cat_enabled.get(mapped, False)
                    expense_items.append({
                        'date': date, 'desc': desc, 'amount': amount,
                        'category': (claude_category or mapped).replace('_', ' ').title(),
                        'counted': enabled,
                        'reason': 'Verified recurring expense' if enabled else
                                  ('Category disabled in Rules Engine' if mapped in cat_enabled else 'Unclassified expense — not counted'),
                        'confidence': txn.get('confidence', 'medium'),
                    })

    # ── Subscription capping: max 2 charges per merchant per statement ──
    sub_merchant_counts = defaultdict(list)
    for idx, e in enumerate(expense_items):
        if e.get('counted') and e.get('category', '').lower() in ('subscriptions', 'subscription'):
            # Normalize merchant name from description
            merchant = re.sub(r'[^a-z]', '', e.get('desc', '').lower())[:6]
            sub_merchant_counts[merchant].append(idx)
    for merchant, indices in sub_merchant_counts.items():
        if sub_cap > 0 and len(indices) > sub_cap:
            for idx in indices[sub_cap:]:
                expense_items[idx]['counted'] = False
                expense_items[idx]['reason'] = f'Subscription capped: max 2 per merchant ({expense_items[idx]["desc"]})'

    # ── Bounced/returned payment detection ──
    RETURN_PATTERNS = ['return of posted check', 'returned item', 'payment reversal',
                       'reversal', 'returned payment', 'chargeback', 'returned check',
                       'return item', 'nsf return', 'returned ach']
    bounced_count = 0
    bounced_total = 0.0
    if bounced_on:
        for inc_item in income_items:
            desc_lower = inc_item.get('desc', '').lower()
            if not any(pat in desc_lower for pat in RETURN_PATTERNS):
                continue
            return_amount = inc_item['amount']
            for exp_item in expense_items:
                if exp_item.get('counted') and abs(exp_item['amount'] - return_amount) < 0.02:
                    exp_item['counted'] = False
                    exp_item['reason'] = f'Payment returned/bounced — offset by ${return_amount:,.2f} credit'
                    inc_item['reason'] = f'Returned payment credit — offsets bounced debit'
                    bounced_count += 1
                    bounced_total += return_amount
                    break

    # ── Duplicate transaction detection ──
    seen_txns = {}
    duplicate_count = 0
    for idx, e in enumerate(expense_items):
        if not e.get('counted'):
            continue
        key = (e.get('desc', '').lower()[:30], round(e.get('amount', 0), 2), e.get('date', ''))
        if key[0] and key[2]:  # only check if we have desc and date
            if key in seen_txns:
                duplicate_count += 1
                e['reason'] = f'Possible duplicate of transaction on {key[2]} — flagged'
            else:
                seen_txns[key] = idx

    # ── STEP 2: Calculate verified income and expenses ──
    # Set fintech count = number of UNIQUE apps (not total interactions)
    fintech_count = len(fintech_apps_seen)
    fintech_apps_list = sorted(fintech_apps_seen)

    # Collect PPD unknown deposits for manual review + scenario calculation
    ppd_unknown_items = [
        i for i in income_items
        if i.get('category', '').lower() in ('ppd unknown', 'ppd_unknown')
    ]

    # Also flag large other_credit items as potential missed income
    other_credit_items = [i for i in income_items
                          if i.get('category', '').lower() in ('other credit', 'other_credit')
                          and i.get('amount', 0) >= 500]

    # Find sources that appear 2+ times (recurring = likely income)
    other_credit_sources = Counter()
    for item in other_credit_items:
        src = item.get('desc', '')[:30].strip().upper()
        other_credit_sources[src] += 1

    recurring_other_credits = [
        i for i in other_credit_items
        if other_credit_sources.get(i.get('desc', '')[:30].strip().upper(), 0) >= 2
    ]

    # Add recurring large other_credits to ppd_unknown for second opinion
    ppd_already = {i['desc'][:30] for i in ppd_unknown_items}
    for item in recurring_other_credits:
        if item['desc'][:30] not in ppd_already:
            ppd_item = dict(item)
            ppd_item['category'] = 'Ppd Unknown'
            ppd_item['reason'] = 'Large recurring credit ($500+) — possible undetected income, requires verification'
            ppd_unknown_items.append(ppd_item)

    ppd_unknown_total = sum(i['amount'] for i in ppd_unknown_items)

    # FIX B: Collect ALL p2p_sent (including pending) for notable P2P flagging
    all_p2p_by_recipient = {}
    for txn in transactions:
        cat = txn.get('category', '').lower()
        if not txn.get('is_credit') and cat in ('p2p_sent', 'p2p sent'):
            desc_p2p = txn.get('description', '')
            m = re.search(r'(?:to|TO)\s+([A-Za-z][A-Za-z\s]{1,25}?)(?:\s+Conf|\s+#|\s+for\s|$)', desc_p2p)
            recipient = m.group(1).strip() if m else desc_p2p[:30]
            if recipient not in all_p2p_by_recipient:
                all_p2p_by_recipient[recipient] = {'count': 0, 'total': 0.0}
            all_p2p_by_recipient[recipient]['count'] += 1
            all_p2p_by_recipient[recipient]['total'] += float(txn.get('amount', 0))
    notable_p2p_all = {k: v for k, v in all_p2p_by_recipient.items() if v['total'] >= 500}

    # Recurring P2P sent — detect potential hidden obligations (flagged in adjustments later)
    recurring_p2p_sent = {k: v for k, v in all_p2p_by_recipient.items() if v['count'] >= 2 and v['total'] >= 200}

    # Recurring P2P received analysis — identify potential informal income patterns
    p2p_by_sender = {}
    for txn in transactions:
        cat = txn.get('category', '').lower()
        if txn.get('is_credit') and cat in ('p2p_received', 'p2p received'):
            desc_p2p = txn.get('description', '')
            m = re.search(r'(?:from|FROM)\s+([A-Za-z][A-Za-z\s]{1,25}?)(?:\s+Conf|\s+#|\s+for\s|$)', desc_p2p)
            sender = m.group(1).strip() if m else desc_p2p[:30]
            if sender not in p2p_by_sender:
                p2p_by_sender[sender] = {'count': 0, 'total': 0.0}
            p2p_by_sender[sender]['count'] += 1
            p2p_by_sender[sender]['total'] += abs(float(txn.get('amount', 0)))
    recurring_p2p_received = {k: v for k, v in p2p_by_sender.items() if v['count'] >= 2}
    recurring_p2p_total = sum(v['total'] for v in recurring_p2p_received.values())
    recurring_sender_names = set(recurring_p2p_received.keys())

    # If P2P mode is 'recurring', retroactively count recurring P2P received at discount
    if p2p_received_mode == 'recurring' and recurring_sender_names:
        for item in income_items:
            if item.get('category', '').lower() in ('p2p received', 'p2p_received') and not item.get('counted'):
                d = item.get('desc', '')
                m = re.search(r'(?:from|FROM)\s+([A-Za-z][A-Za-z\s]{1,25}?)(?:\s+Conf|\s+#|\s+for\s|$)', d)
                sender = m.group(1).strip() if m else d[:30]
                if sender in recurring_sender_names:
                    item['counted'] = True
                    item['amount'] = item['amount'] * p2p_received_pct
                    item['reason'] = f'Recurring P2P from {sender} — counted at {int(p2p_received_pct*100)}%'

    # Smart P2P classification — replaces simple "recurring" logic
    if p2p_sent_mode == 'recurring':
        # Collect P2P items for classification
        p2p_sent_for_classify = [e for e in expense_items if e.get('category', '').lower() in ('p2p sent', 'p2p_sent')]
        p2p_received_for_classify = [i for i in income_items if i.get('category', '').lower() in ('p2p received', 'p2p_received')]
        holder = extracted_data.get('account_holder_name', '')

        p2p_results = classify_p2p_sent(p2p_sent_for_classify, p2p_received_for_classify, holder)

        # Apply classification results back to expense_items
        # First, un-count all P2P sent items (the classifier owns their disposition)
        for item in expense_items:
            if item.get('category', '').lower() in ('p2p sent', 'p2p_sent'):
                item['counted'] = False
        # Add classified items as new entries
        for r in p2p_results:
            if r.get('counted'):
                expense_items.append({
                    'date': r.get('date', ''),
                    'desc': r.get('desc', ''),
                    'amount': r.get('amount', 0),
                    'category': r.get('category', 'Other Expense'),
                    'counted': True,
                    'reason': r.get('reason', ''),
                    'confidence': r.get('confidence', 'medium'),
                })
            else:
                # Update the reason on the original item
                for item in expense_items:
                    if item.get('desc') == r.get('desc') and item.get('amount') == r.get('original_amount', r.get('amount')):
                        item['reason'] = r.get('reason', item.get('reason', ''))
                        item['confidence'] = r.get('confidence', 'medium')
                        break

        # Remove original P2P sent items that were reclassified as counted
        # (prevents same transaction appearing twice — once counted, once excluded)
        counted_p2p = {(r.get('desc',''), r.get('amount',0)) for r in p2p_results if r.get('counted')}
        if counted_p2p:
            expense_items = [e for e in expense_items
                             if not (e.get('category','').lower() in ('p2p sent','p2p_sent')
                                     and not e.get('counted')
                                     and (e.get('desc',''), e.get('amount',0)) in counted_p2p)]

    period_income = sum(i['amount'] for i in income_items if i['counted'])
    
    period_expenses = 0
    for e in expense_items:
        if e.get('counted'):
            if 'counted_amount' in e:
                period_expenses += e['counted_amount']
            else:
                period_expenses += e['amount']
    
    # Annualize to 30-day month
    multiplier = 30 / max(statement_days, 1)
    monthly_income = period_income * multiplier
    monthly_expenses_raw = period_expenses * multiplier
    
    # Apply expense floor if enabled and expenses are below floor
    if expense_floor_on and monthly_expenses_raw < expense_floor:
        monthly_expenses = expense_floor
        expense_floor_applied = True
        expense_floor_note = f'Expense floor applied: actual ${monthly_expenses_raw:.2f} < floor ${expense_floor}. Using ${expense_floor} as minimum.'
    else:
        monthly_expenses = monthly_expenses_raw
        expense_floor_applied = False
        expense_floor_note = ''
    
    # Velocity: only count real economic activity — exclude internal transfers, P2P, and fintech
    VELOCITY_EXCLUDE_CREDITS = {'internal_transfer', 'p2p_received', 'fintech_advance', 'loan_proceeds', 'other_credit', 'tax_refund'}
    VELOCITY_EXCLUDE_DEBITS  = {'internal_transfer', 'p2p_sent', 'fintech_repayment', 'fee'}

    real_inflows  = sum(t['amount'] for t in transactions
                       if t.get('is_credit') and t.get('category','').lower() not in VELOCITY_EXCLUDE_CREDITS)
    real_outflows = sum(t['amount'] for t in transactions
                       if not t.get('is_credit') and t.get('category','').lower() not in VELOCITY_EXCLUDE_DEBITS)

    # Fallback: if Claude didn't label categories, use verified income vs verified expenses
    if real_inflows == 0:
        real_inflows  = period_income
        real_outflows = period_expenses

    velocity_ratio = (real_outflows / real_inflows) if real_inflows > 0 else 0
    
    # Ending balance
    ending_balance = extracted_data.get('ending_balance', 999)
    
    # Paycheck count
    paycheck_count = sum(1 for i in income_items if i['counted'])

    # ── STEP 3: Calculate FCF ──
    fcf = monthly_income - monthly_expenses
    
    # ── STEP 3b: PPD verified scenario — what if unverified PPD income counted? ──
    ppd_scenario = None
    if ppd_unknown_items and ppd_unknown_total > 0:
        ppd_monthly = ppd_unknown_total * multiplier
        ppd_fcf = fcf + ppd_monthly
        ppd_total_income = monthly_income + ppd_monthly
        # Run tier waterfall with PPD income included
        if ppd_fcf >= t4:
            ppd_tier, ppd_amount = 4, loan_max
        elif ppd_fcf >= t3:
            ppd_tier, ppd_amount = 3, 200
        elif ppd_fcf >= t2:
            ppd_tier, ppd_amount = 2, 150
        elif ppd_fcf >= t1:
            ppd_tier, ppd_amount = 1, 100
        else:
            ppd_tier, ppd_amount = 0, 0
        ppd_scenario = {
            'ppd_monthly': round(ppd_monthly, 2),
            'ppd_total_income': round(ppd_total_income, 2),
            'ppd_fcf': round(ppd_fcf, 2),
            'ppd_tier': ppd_tier,
            'ppd_amount': ppd_amount,
            'ppd_total': round(ppd_unknown_total, 2),
            'sources': list({i['desc'][:60] for i in ppd_unknown_items}),
        }

    # ── STEP 3c: P2P recurring income scenario — what if recurring P2P counted at 50%? ──
    p2p_scenario = None
    if recurring_p2p_received and recurring_p2p_total > 0:
        p2p_monthly_add = (recurring_p2p_total * multiplier) * 0.5  # count at 50%
        p2p_fcf = fcf + p2p_monthly_add
        p2p_total_income = monthly_income + p2p_monthly_add
        if p2p_fcf >= t4:
            p2p_tier, p2p_amount = 4, loan_max
        elif p2p_fcf >= t3:
            p2p_tier, p2p_amount = 3, 200
        elif p2p_fcf >= t2:
            p2p_tier, p2p_amount = 2, 150
        elif p2p_fcf >= t1:
            p2p_tier, p2p_amount = 1, 100
        else:
            p2p_tier, p2p_amount = 0, 0
        p2p_scenario = {
            'recurring_senders': {k: v for k, v in recurring_p2p_received.items()},
            'recurring_total': round(recurring_p2p_total, 2),
            'monthly_add': round(p2p_monthly_add, 2),
            'scenario_income': round(p2p_total_income, 2),
            'scenario_fcf': round(p2p_fcf, 2),
            'scenario_tier': p2p_tier,
            'scenario_amount': p2p_amount,
        }

    # ── STEP 4: Calculate speculative % ──
    total_tracked_expenses = sum(e['amount'] for e in expense_items if e.get('counted') and e.get('category') != 'Speculative/Gambling')
    spec_pct = (total_speculative / monthly_income * 100) if monthly_income > 0 else 0
    
    # ── STEP 5: Tier waterfall ──
    tier_amounts = [0, t1_amount, t2_amount, t3_amount, loan_max]
    if fcf >= t4:
        base_tier = 4
        base_amount = loan_max
    elif fcf >= t3:
        base_tier = 3
        base_amount = t3_amount
    elif fcf >= t2:
        base_tier = 2
        base_amount = t2_amount
    elif fcf >= t1:
        base_tier = 1
        base_amount = t1_amount
    else:
        base_tier = 0
        base_amount = 0

    # ── DTI calculation ──
    total_debt = 0
    for e in expense_items:
        cat = e.get('category', '').lower()
        if 'loan' in cat or 'fintech' in cat or 'bnpl' in cat:
            total_debt += e.get('amount', 0)  # Full amount, not fee portion
    # Add recurring P2P sent
    for name, info in recurring_p2p_sent.items():
        total_debt += info.get('total', 0)
    monthly_debt = total_debt * multiplier
    dti_ratio = (monthly_debt / monthly_income * 100) if monthly_income > 0 else 999
    
    # ── STEP 6: Risk adjustments ──
    adjustments = []
    current_tier = base_tier
    current_amount = base_amount
    decline_reasons = []

    # Flag recurring P2P sent as potential obligations
    for name, info in recurring_p2p_sent.items():
        adjustments.append(f'Recurring P2P to {name}: {info["count"]} payments totaling ${info["total"]:,.2f} — potential obligation')

    # Check hard declines — ONLY for critical conditions
    if account_closed and ad_closed == 'decline':
        decline_reasons.append('Account is closed or restricted')
    if fraud_indicators and ad_fraud == 'decline':
        decline_reasons.append('Fraud indicators detected')
    if period_income == 0 and ad_no_income == 'decline':
        decline_reasons.append('No verified income found in statement')
    # Statement age check
    if ad_stale != 'off':
        statement_end = extracted_data.get('statement_end', '')
        if statement_end:
            try:
                from datetime import date as _date
                end_date = datetime.strptime(statement_end, '%Y-%m-%d').date()
                days_old = (_date.today() - end_date).days
                if days_old > stale_days:
                    if ad_stale == 'decline':
                        decline_reasons.append(f'Statement is {days_old} days old (max {stale_days})')
                    else:
                        adjustments.append(f'Statement is {days_old} days old (max {stale_days})')
            except:
                pass
    # Require 2+ paychecks
    require_2 = settings.get('require2Checks', False)
    
    # NSF adjustment — tier drop only, no auto-decline
    if nsf_count >= nsf_dec:
        adjustments.append(f'{nsf_count} NSFs >= {nsf_dec} → Cap at $100 (was decline)')
        current_amount = min(current_amount, 100)
        current_tier = min(current_tier, 1)
    elif nsf_count >= nsf_cap:
        adjustments.append(f'{nsf_count} NSFs → Cap at $100')
        current_amount = min(current_amount, 100)
        current_tier = min(current_tier, 1)
    elif nsf_count >= nsf_drop:
        adjustments.append(f'{nsf_count} NSFs → Drop 1 tier')
        current_tier = max(0, current_tier - 1)
        current_amount = tier_amounts[current_tier]
    else:
        adjustments.append(f'{nsf_count} NSFs → No adjustment')
    
    # Fintech adjustment — tier drops only, no auto-decline
    ft_apps_str = f"{fintech_count} unique app{'s' if fintech_count != 1 else ''} ({', '.join(fintech_apps_list)})" if fintech_apps_list else '0 apps'
    if fintech_count >= ft_abs:
        adjustments.append(f'{ft_apps_str} >= {ft_abs} → Cap at $100 (was absolute decline)')
        current_amount = min(current_amount, 100)
        current_tier = min(current_tier, 1)
    elif fintech_count >= ft_dec:
        adjustments.append(f'{ft_apps_str} >= {ft_dec} → Cap at $100 (was decline)')
        current_amount = min(current_amount, 100)
        current_tier = min(current_tier, 1)
    elif fintech_count >= ft_cap:
        adjustments.append(f'{ft_apps_str} → Cap at $100')
        current_amount = min(current_amount, 100)
        current_tier = min(current_tier, 1)
    elif fintech_count >= ft_drop:
        adjustments.append(f'{ft_apps_str} → Drop 1 tier')
        current_tier = max(0, current_tier - 1)
        current_amount = tier_amounts[current_tier]
    else:
        adjustments.append(f'{ft_apps_str} → No adjustment')
    
    # Negative balance days — tier drop only, no auto-decline
    if negative_days >= neg_dec:
        adjustments.append(f'{negative_days} negative days >= {neg_dec} → Cap at $100 (was decline)')
        current_amount = min(current_amount, 100)
        current_tier = min(current_tier, 1)
    elif negative_days >= neg_cap:
        adjustments.append(f'{negative_days} negative days → Cap at $100')
        current_amount = min(current_amount, 100)
        current_tier = min(current_tier, 1)
    else:
        adjustments.append(f'{negative_days} negative days → No adjustment')

    # Average daily balance — tier drop only, no auto-decline
    if avg_daily_balance < 0:
        adjustments.append(f'Avg daily balance ${avg_daily_balance:.2f} negative → Drop 1 tier (was decline)')
        current_tier = max(0, current_tier - 1)
        current_amount = tier_amounts[current_tier]
    
    # Speculative activity
    if spec_pct >= spec_cap:
        adjustments.append(f'{spec_pct:.1f}% speculative → Cap at $100')
        current_amount = min(current_amount, 100)
        current_tier = min(current_tier, 1)
    elif spec_pct >= spec_drop:
        adjustments.append(f'{spec_pct:.1f}% speculative → Drop 1 tier')
        current_tier = max(0, current_tier - 1)
        current_amount = tier_amounts[current_tier]
    else:
        adjustments.append(f'{spec_pct:.1f}% speculative → No adjustment')
    
    # Velocity adjustment
    if velocity_on and velocity_ratio > 0:
        if velocity_ratio >= velocity_cap:
            adjustments.append(f'Account velocity {velocity_ratio*100:.1f}% → Cap at $100 (money flowing through account)')
            current_amount = min(current_amount, 100)
            current_tier = min(current_tier, 1)
        elif velocity_ratio >= velocity_drop:
            adjustments.append(f'Account velocity {velocity_ratio*100:.1f}% → Drop 1 tier')
            current_tier = max(0, current_tier - 1)
            current_amount = tier_amounts[current_tier]
        else:
            adjustments.append(f'Account velocity {velocity_ratio*100:.1f}% → No adjustment')
    
    # Ending balance adjustment
    if endbal_on:
        if ending_balance <= endbal_drop:
            adjustments.append(f'Ending balance ${ending_balance:.2f} → Drop 1 tier (very low)')
            current_tier = max(0, current_tier - 1)
            current_amount = tier_amounts[current_tier]
        elif ending_balance <= endbal_flag:
            adjustments.append(f'Ending balance ${ending_balance:.2f} → Flagged (low balance)')
        else:
            adjustments.append(f'Ending balance ${ending_balance:.2f} → OK')
    
    # Single paycheck flag
    if paycheck_count == 1:
        if ad_single_check == 'decline':
            decline_reasons.append('Only 1 paycheck found — employment pattern unconfirmed')
        elif ad_single_check == 'drop':
            adjustments.append('Single paycheck only → Drop 1 tier')
            current_tier = max(0, current_tier - 1)
            current_amount = tier_amounts[current_tier]
        elif ad_single_check == 'cap':
            adjustments.append('Single paycheck only → Cap at $100')
            current_amount = min(current_amount, 100)
        elif ad_single_check == 'flag':
            adjustments.append('Single paycheck only → Flagged for review')
    
    # DTI risk adjustment
    if dti_ratio >= dti_drop2 * 100:
        adjustments.append(f'DTI {dti_ratio:.0f}% >= {int(dti_drop2*100)}% → Drop 2 tiers')
        current_tier = max(0, current_tier - 2)
        current_amount = tier_amounts[current_tier]
    elif dti_ratio >= dti_drop * 100:
        adjustments.append(f'DTI {dti_ratio:.0f}% >= {int(dti_drop*100)}% → Drop 1 tier')
        current_tier = max(0, current_tier - 1)
        current_amount = tier_amounts[current_tier]

    # Expense floor note
    if expense_floor_applied:
        adjustments.append(f'Expense floor applied: ${expense_floor}/mo minimum used (actual ${monthly_expenses_raw:.2f})')

    # Bounced payment flag
    if bounced_count > 0:
        adjustments.append(f'{bounced_count} bounced/returned payment{"s" if bounced_count>1 else ""} detected (${bounced_total:,.2f} offset)')

    # Duplicate transaction flag
    if duplicate_count > 0:
        adjustments.append(f'{duplicate_count} possible duplicate transaction{"s" if duplicate_count>1 else ""} detected')

    # Expense-to-income ratio warning per category
    multiplier_exp = 30 / max(statement_days, 1)
    if monthly_income > 0:
        for e in expense_items:
            if not e.get('counted'):
                continue
        # Check grouped categories
        cat_totals = defaultdict(float)
        for e in expense_items:
            if e.get('counted'):
                cat = e.get('category', 'Other').split('(')[0].strip()
                cat_totals[cat] += abs(e.get('counted_amount', e.get('amount', 0)))
        for cat, total in cat_totals.items():
            monthly_cat = total * multiplier_exp
            ratio = monthly_cat / monthly_income * 100
            if ratio >= 100:
                adjustments.append(f'{cat} expense ${monthly_cat:,.0f}/mo = {ratio:.0f}% of income — extreme')

    # Balance validation
    beginning_balance = extracted_data.get('beginning_balance', 0) or 0
    total_credits = sum(i['amount'] for i in income_items)
    total_debits = sum(e['amount'] for e in expense_items)
    expected_ending = beginning_balance + total_credits - total_debits
    balance_diff = abs(expected_ending - ending_balance)
    if balance_diff > 50:
        adjustments.append(f'Balance mismatch: expected ${expected_ending:,.2f}, actual ${ending_balance:,.2f} (diff ${balance_diff:,.2f}) — possible missing transactions')

    # Income stability: P2P received vs verified income
    total_p2p_received = sum(i['amount'] for i in income_items if 'p2p' in i.get('category', '').lower())
    if monthly_income > 0 and total_p2p_received * multiplier_exp > monthly_income:
        adjustments.append(f'P2P received (${total_p2p_received * multiplier_exp:,.0f}/mo) exceeds verified income — possible informal income reliance')

    # Tier floor: if FCF qualified for a tier (base_tier > 0), risk adjustments
    # can drop/cap but never below Tier 1 ($100). Ensures positive-FCF applicants
    # always get at least the minimum loan.
    if base_tier > 0 and current_tier < 1:
        current_tier = 1
        current_amount = t1_amount
        adjustments.append(f'Tier floor applied: FCF ${fcf:,.2f} qualifies — minimum Tier 1 (${t1_amount})')

    # FCF check — if below minimum tier (this is the primary financial decline reason)
    if base_tier == 0:
        decline_reasons.append(f'FCF ${fcf:.2f} is below minimum threshold ${t1} for Tier 1')

    # ── Build flagged_transactions list ──
    flagged_transactions = []
    all_items = income_items + expense_items
    for fi, item in enumerate(all_items):
        if item.get('confidence') == 'low':
            flagged_transactions.append({
                'index': fi,
                'date': item.get('date', ''),
                'description': item.get('desc', ''),
                'amount': item.get('amount', 0),
                'current_category': item.get('category', ''),
                'confidence': 'low',
                'reason': item.get('reason', ''),
            })

    # ── Determine review tier ──
    if not flagged_transactions and current_tier > 0:
        review_tier = 'auto'
    elif len(flagged_transactions) <= 2:
        review_tier = 'quick'
    else:
        review_tier = 'full'

    # ── STEP 7: Final decision ──
    if decline_reasons:
        decision = 'DECLINED'
        final_amount = 0
        decline_reason_text = decline_reasons[0]  # Primary reason
    elif current_tier == 0:
        # Tier was dropped to 0 by risk adjustments
        decision = 'DECLINED'
        final_amount = 0
        drop_adjs = [a for a in adjustments if 'Drop' in a or 'Cap' in a]
        if drop_adjs:
            decline_reason_text = 'Risk adjustments reduced tier below minimum: ' + '; '.join(drop_adjs)
        else:
            decline_reason_text = 'Risk adjustments reduced qualification below minimum tier'
    else:
        decision = 'APPROVED'
        final_amount = current_amount
        decline_reason_text = ''
    
    return {
        'decision': decision,
        'amount': final_amount,
        'fcf': round(fcf, 2),
        'monthly_income': round(monthly_income, 2),
        'monthly_expenses': round(monthly_expenses, 2),
        'period_income': round(period_income, 2),
        'period_expenses': round(period_expenses, 2),
        'statement_days': statement_days,
        'base_tier': base_tier,
        'base_amount': base_amount,
        'final_tier': current_tier,
        'adjustments': adjustments,
        'decline_reasons': decline_reasons,
        'decline_reason_text': decline_reason_text,
        'nsf_count': nsf_count,
        'fintech_count': fintech_count,
        'fintech_apps_list': fintech_apps_list,
        'negative_days': negative_days,
        'avg_daily_balance': avg_daily_balance,
        'spec_pct': round(spec_pct, 1),
        'income_items': income_items,
        'expense_items': expense_items,
        'expense_floor_applied': expense_floor_applied,
        'expense_floor_note': expense_floor_note,
        'velocity_ratio': round(velocity_ratio * 100, 1),
        'ending_balance': ending_balance,
        'paycheck_count': paycheck_count,
        'settings': {
            't1': t1, 't2': t2, 't3': t3, 't4': t4,
            'loan_max': loan_max
        },
        'ppd_unknown_items': ppd_unknown_items,
        'ppd_unknown_total': round(ppd_unknown_total, 2),
        'ppd_scenario': ppd_scenario,
        'notable_p2p_all': notable_p2p_all,
        'available_balance': extracted_data.get('available_balance', None),
        'bounced_count': bounced_count,
        'bounced_total': round(bounced_total, 2),
        'duplicate_count': duplicate_count,
        'account_holder_name': extracted_data.get('account_holder_name', ''),
        'p2p_scenario': p2p_scenario,
        'recurring_p2p_sent': recurring_p2p_sent,
        # ── New fields ──
        'flagged_transactions': flagged_transactions,
        'has_flagged': len(flagged_transactions) > 0,
        'review_tier': review_tier,
        'dti_ratio': round(dti_ratio, 1),
        'total_debt_obligations': round(monthly_debt, 2),
        'total_fintech_repayments': round(total_fintech_full_repayment * multiplier, 2),
        'overrides_applied': len(override_map),
        'data_source': extracted_data.get('data_source', 'pdf_claude'),
    }
