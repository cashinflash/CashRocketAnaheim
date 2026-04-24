#!/usr/bin/env python3
"""
Cash Rocket Anaheim — Loan Application Backend (fork of cif-apply).
Hardcodes source_site='cashrocket_anaheim' on every /submit so the shared
dashboard can tell these submissions apart from apply.cashinflash.com ones.
All underwriting logic + Firebase writes are identical to cif-apply main.
"""

import json, os, ssl, base64, time, re, http.client, threading, sys
from datetime import datetime
from zoneinfo import ZoneInfo

PACIFIC = ZoneInfo("America/Los_Angeles")
def now_pacific():
    return datetime.now(PACIFIC)
from http.server import HTTPServer, BaseHTTPRequestHandler

# ══════════════════════════════════════════
# CONFIG — set via Railway environment variables
# ══════════════════════════════════════════
PLAID_CLIENT_ID    = os.environ.get('PLAID_CLIENT_ID', '691b887592e1e300248c43af')
PLAID_SECRET       = os.environ.get('PLAID_SECRET', 'f1ea4f105261ab1e3f9c05d01b815f')
PLAID_ENV          = os.environ.get('PLAID_ENV', 'production')  # production or sandbox
ANTHROPIC_API_KEY  = os.environ.get('ANTHROPIC_API_KEY', '')
FIREBASE_HOST      = 'cashinflash-a1dce-default-rtdb.firebaseio.com'
PORT               = int(os.environ.get('PORT', 8080))

PLAID_HOST = f'{PLAID_ENV}.plaid.com'

# ══════════════════════════════════════════
# EMAIL NOTIFICATIONS
# ══════════════════════════════════════════
EMAIL_SENDER   = os.environ.get('EMAIL_SENDER', 'notifications@cashinflash.com')
EMAIL_PASSWORD = os.environ.get('EMAIL_PASSWORD', '')
EMAIL_TO       = os.environ.get('EMAIL_TO', 'info@cashinflash.com')
EMAIL_ENABLED  = os.environ.get('EMAIL_ENABLED', 'true').lower() == 'true'

def send_notification(form_data, firebase_id):
    """Send email notification via SendGrid HTTP API."""
    print(f'[EMAIL] Sending via SendGrid... to={EMAIL_TO}', flush=True)
    if not EMAIL_ENABLED or not EMAIL_PASSWORD:
        print('[EMAIL] Disabled or no API key', flush=True)
        return
    try:
        name = f"{form_data.get('firstName','')} {form_data.get('lastName','')}".strip()
        amount = f"${form_data.get('loanAmount','?')}"
        phone = form_data.get('phone','')
        email = form_data.get('email','')
        bank_method = form_data.get('bankMethod','')
        submitted_at = now_pacific().strftime('%B %d, %Y at %I:%M %p')
        subject = f"New Loan Application — {name} ({amount})"
        html = f"""<!DOCTYPE html>
<html><body style="margin:0;padding:0;background:#f0f4f1;font-family:Arial,sans-serif">
<div style="max-width:580px;margin:32px auto;background:#ffffff;border-radius:16px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,.10)">

  <!-- HEADER -->
  <div style="background:#ffffff;padding:24px 32px 20px;text-align:center;border-bottom:3px solid #1a6b3c">
    <img src="https://cashrocketanaheim.com/images/logo.png"
         alt="Cash Rocket Anaheim" width="160" style="display:block;margin:0 auto 16px;height:auto">
    <div style="display:inline-block;background:#e8f5ee;border:1px solid #b2d9c0;border-radius:20px;padding:6px 16px">
      <span style="color:#1a6b3c;font-size:13px;font-weight:600;letter-spacing:.05em;text-transform:uppercase">New Application Received</span>
    </div>
  </div>

  <!-- BODY -->
  <div style="padding:28px 32px">
    <h2 style="margin:0 0 20px;font-size:20px;color:#0d1a12;font-weight:700">{name}</h2>

    <!-- Amount highlight -->
    <div style="background:linear-gradient(135deg,#e8f5ee,#f0faf4);border:1.5px solid #b2d9c0;border-radius:12px;padding:16px 20px;margin-bottom:20px;display:flex;align-items:center;justify-content:space-between">
      <span style="font-size:14px;color:#6b7c72;font-weight:600">Loan Amount Requested</span>
      <span style="font-size:26px;font-weight:800;color:#1a6b3c">{amount}</span>
    </div>

    <!-- Details table -->
    <table style="width:100%;border-collapse:collapse;margin-bottom:24px">
      <tr style="background:#f8faf8">
        <td style="padding:12px 14px;font-size:13px;color:#7a8f82;font-weight:600;width:140px;border-bottom:1px solid #e8f0eb">📞 Phone</td>
        <td style="padding:12px 14px;font-size:14px;color:#0d1a12;font-weight:600;border-bottom:1px solid #e8f0eb">{phone}</td>
      </tr>
      <tr>
        <td style="padding:12px 14px;font-size:13px;color:#7a8f82;font-weight:600;border-bottom:1px solid #e8f0eb">✉️ Email</td>
        <td style="padding:12px 14px;font-size:14px;color:#0d1a12;font-weight:600;border-bottom:1px solid #e8f0eb">{email}</td>
      </tr>
      <tr style="background:#f8faf8">
        <td style="padding:12px 14px;font-size:13px;color:#7a8f82;font-weight:600;border-bottom:1px solid #e8f0eb">🏦 Bank Method</td>
        <td style="padding:12px 14px;font-size:14px;color:#0d1a12;font-weight:600;border-bottom:1px solid #e8f0eb">{bank_method}</td>
      </tr>
      <tr>
        <td style="padding:12px 14px;font-size:13px;color:#7a8f82;font-weight:600">🕐 Submitted</td>
        <td style="padding:12px 14px;font-size:14px;color:#0d1a12;font-weight:600">{submitted_at}</td>
      </tr>
    </table>

    <!-- CTA Button -->
    <div style="text-align:center;margin:8px 0 4px">
      <a href="https://app.cashinflash.com"
         style="display:inline-block;background:#1a6b3c;color:#ffffff;padding:16px 40px;border-radius:10px;font-size:16px;font-weight:700;text-decoration:none;letter-spacing:.02em;box-shadow:0 4px 16px rgba(26,107,60,.35)">
        Review Application →
      </a>
      <p style="margin:12px 0 0;font-size:12px;color:#a0b0a8">app.cashinflash.com</p>
    </div>
  </div>

  <!-- FOOTER -->
  <div style="background:#f4f8f5;border-top:1px solid #dce8e0;padding:16px 32px;text-align:center">
    <p style="margin:0;font-size:12px;color:#a0b0a8">Cash in Flash · 13937B Van Nuys Blvd, Arleta, CA 91331 · (747) 270-7121</p>
  </div>

</div>
</body></html>"""

        payload = json.dumps({
            "personalizations": [{"to": [{"email": EMAIL_TO}]}],
            "from": {"email": EMAIL_SENDER, "name": "Cash Rocket Anaheim"},
            "subject": subject,
            "content": [{"type": "text/html", "value": html}]
        }).encode('utf-8')

        ctx = ssl.create_default_context()
        conn = http.client.HTTPSConnection('api.sendgrid.com', timeout=30, context=ctx)
        conn.request('POST', '/v3/mail/send', body=payload, headers={
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {EMAIL_PASSWORD}',
            'Content-Length': str(len(payload))
        })
        resp = conn.getresponse()
        resp.read()
        conn.close()
        if resp.status in (200, 202):
            print(f'[EMAIL] Sent successfully to {EMAIL_TO} for {name}', flush=True)
        else:
            print(f'[EMAIL ERROR] SendGrid status {resp.status}', flush=True)
    except Exception as e:
        print(f'[EMAIL ERROR] {e}', flush=True)

# In-memory store for Plaid results from mobile new-tab flow
plaid_results = {}  # link_token -> {asset_report_token, institution}

# ══════════════════════════════════════════
# CORS HEADERS
# ══════════════════════════════════════════
CORS = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type',
}

# ══════════════════════════════════════════
# HTTP HELPERS
# ══════════════════════════════════════════
def https_post(host, path, payload, headers=None):
    ctx = ssl.create_default_context()
    conn = http.client.HTTPSConnection(host, timeout=60, context=ctx)
    body = json.dumps(payload, ensure_ascii=True).encode('utf-8')
    h = {'Content-Type': 'application/json', 'Content-Length': str(len(body))}
    if headers:
        h.update(headers)
    conn.request('POST', path, body=body, headers=h)
    resp = conn.getresponse()
    data = json.loads(resp.read().decode('utf-8'))
    conn.close()
    return resp.status, data

def https_get(host, path, headers=None):
    ctx = ssl.create_default_context()
    conn = http.client.HTTPSConnection(host, timeout=30, context=ctx)
    conn.request('GET', path, headers=headers or {})
    resp = conn.getresponse()
    data = resp.read()
    conn.close()
    return resp.status, data

# ══════════════════════════════════════════
# PLAID
# ══════════════════════════════════════════
def plaid_create_link_token(client_name='Cash Rocket Anaheim'):
    status, data = https_post(PLAID_HOST, '/link/token/create', {
        'client_id': PLAID_CLIENT_ID,
        'secret': PLAID_SECRET,
        'client_name': client_name,
        'user': {'client_user_id': f'user_{int(time.time())}'},
        'products': ['assets'],
        'country_codes': ['US'],
        'language': 'en',
    })
    if status == 200:
        return data.get('link_token')
    raise Exception(f'Plaid link token error: {data}')

def plaid_exchange_token(public_token):
    status, data = https_post(PLAID_HOST, '/item/public_token/exchange', {
        'client_id': PLAID_CLIENT_ID,
        'secret': PLAID_SECRET,
        'public_token': public_token,
    })
    if status == 200:
        return data.get('access_token')
    raise Exception(f'Plaid exchange error: {data}')

def plaid_create_asset_report(access_token, days_requested=30):
    status, data = https_post(PLAID_HOST, '/asset_report/create', {
        'client_id': PLAID_CLIENT_ID,
        'secret': PLAID_SECRET,
        'access_tokens': [access_token],
        'days_requested': days_requested,
        'options': {'client_report_id': f'cif_{int(time.time())}'},
    })
    if status == 200:
        return data.get('asset_report_token'), data.get('asset_report_id')
    raise Exception(f'Asset report error: {data}')

def plaid_get_asset_report_pdf(asset_report_token, max_retries=30):
    """Poll until asset report is ready then get PDF. Retries for up to 5 minutes."""
    print(f'[INFO] Waiting for Plaid asset report (up to 5 min)...')
    for i in range(max_retries):
        time.sleep(10)
        print(f'[INFO] Asset report attempt {i+1}/{max_retries}...')
        ctx = ssl.create_default_context()
        conn = http.client.HTTPSConnection(PLAID_HOST, timeout=60, context=ctx)
        payload = json.dumps({
            'client_id': PLAID_CLIENT_ID,
            'secret': PLAID_SECRET,
            'asset_report_token': asset_report_token,
        }, ensure_ascii=True).encode('utf-8')
        conn.request('POST', '/asset_report/pdf/get', body=payload,
            headers={'Content-Type': 'application/json', 'Content-Length': str(len(payload))})
        resp = conn.getresponse()
        raw = resp.read()
        conn.close()
        if resp.status == 200:
            print(f'[INFO] Asset report PDF ready! Size: {len(raw)} bytes')
            return raw
        # Try to parse as JSON error
        try:
            err = json.loads(raw.decode('utf-8'))
            ec = err.get('error_code','')
            if ec == 'PRODUCT_NOT_READY':
                print(f'[INFO] Report not ready yet, waiting...')
                continue
            raise Exception(f'Asset report PDF error: {err}')
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise Exception(f'Asset report returned unexpected response (status {resp.status})')
    raise Exception('Asset report timed out after 5 minutes')

def plaid_get_asset_report_json(asset_report_token):
    status, data = https_post(PLAID_HOST, '/asset_report/get', {
        'client_id': PLAID_CLIENT_ID,
        'secret': PLAID_SECRET,
        'asset_report_token': asset_report_token,
        'include_insights': True,
    })
    if status == 200:
        return data
    raise Exception(f'Asset report JSON error: {data}')

# ══════════════════════════════════════════
# FIREBASE
# ══════════════════════════════════════════
def firebase_save(path, data):
    payload = json.dumps(data, ensure_ascii=True).encode('utf-8')
    ctx = ssl.create_default_context()
    conn = http.client.HTTPSConnection(FIREBASE_HOST, timeout=15, context=ctx)
    conn.request('POST', f'/{path}.json', body=payload,
        headers={'Content-Type': 'application/json', 'Content-Length': str(len(payload))})
    resp = conn.getresponse()
    result = json.loads(resp.read().decode('utf-8'))
    conn.close()
    return result.get('name')

def firebase_get(path):
    ctx = ssl.create_default_context()
    conn = http.client.HTTPSConnection(FIREBASE_HOST, timeout=15, context=ctx)
    conn.request('GET', f'/{path}.json')
    resp = conn.getresponse()
    data = json.loads(resp.read().decode('utf-8'))
    conn.close()
    return data

def firebase_patch(path, data):
    payload = json.dumps(data, ensure_ascii=True).encode('utf-8')
    ctx = ssl.create_default_context()
    conn = http.client.HTTPSConnection(FIREBASE_HOST, timeout=15, context=ctx)
    conn.request('PATCH', f'/{path}.json', body=payload,
        headers={'Content-Type': 'application/json', 'Content-Length': str(len(payload))})
    resp = conn.getresponse()
    conn.close()

FIREBASE_STORAGE_BUCKET = 'cashinflash-a1dce.firebasestorage.app'

def firebase_storage_upload(path, data_bytes, content_type='application/pdf'):
    """Upload file to Firebase Storage and return download URL."""
    import urllib.parse
    ctx = ssl.create_default_context()
    encoded_path = urllib.parse.quote(path, safe='')
    conn = http.client.HTTPSConnection('firebasestorage.googleapis.com', timeout=60, context=ctx)
    conn.request('POST',
        f'/v0/b/{FIREBASE_STORAGE_BUCKET}/o?uploadType=media&name={encoded_path}',
        body=data_bytes,
        headers={
            'Content-Type': content_type,
            'Content-Length': str(len(data_bytes))
        }
    )
    resp = conn.getresponse()
    result = json.loads(resp.read().decode('utf-8'))
    conn.close()
    if 'name' in result:
        encoded_name = urllib.parse.quote(result['name'], safe='')
        download_url = f'https://firebasestorage.googleapis.com/v0/b/{FIREBASE_STORAGE_BUCKET}/o/{encoded_name}?alt=media'
        return download_url
    raise Exception(f'Storage upload failed: {result}')

# ══════════════════════════════════════════
# DYNAMIC UNDERWRITING SETTINGS
# ══════════════════════════════════════════
UNDERWRITING_DEFAULTS = {
    'loanMin':100,'loanMax':255,
    't1Fcf':200,'t2Fcf':375,'t3Fcf':500,'t4Fcf':640,
    't1Amount':100,'t2Amount':150,'t3Amount':200,
    'nsfDrop':2,'nsfCap':4,'nsfDecline':5,
    'ftDrop':5,'ftCap':7,'ftDecline':9,'ftAbs':11,
    'negCap':7,'negDecline':10,
    'specDrop':35,'specCap':50,
    'atmThreshold':200,'atmPct':30,'atmCountAll':True,
    'p2pReceivedMode':'exclude','p2pReceivedPct':50,
    'p2pSentMode':'recurring',
    'subCapPerMerchant':2,'bouncedDetection':True,
    'expSpeculative':True,'staleDays':30,
    'adNoIncome':'decline','adClosed':'decline','adFraud':'decline','adFcf':'decline',
    'adAvgBal':'decline','adJobLoss':'decline','adBankruptcy':'decline','adStale':'decline',
    'expRent':True,'expUtilities':True,'expPhone':True,'expInsurance':True,
    'expLoans':True,'expGrocery':True,'expGas':True,'expSubscriptions':True,
    'expChildcare':True,'expRestaurants':True,'expTransportation':True,'expMedical':True,
    'fintechFeePct':15,'moneyOrderThreshold':200,
    'dtiDrop':45,'dtiDrop2':60,
    'expenseFloorOn':True,'expenseFloor':500,
    'expOtherThreshold':50,
}

def get_underwriting_settings():
    """Fetch current underwriting settings from Firebase. Falls back to defaults."""
    try:
        data = firebase_get('settings/underwriting')
        if data and isinstance(data, dict) and 'rules' in data:
            merged = {**UNDERWRITING_DEFAULTS, **data['rules']}
            print(f'[SETTINGS] Profile: {data.get("activeProfile","Standard")}', flush=True)
            return merged
    except Exception as e:
        print(f'[SETTINGS] Using defaults: {e}', flush=True)
    return UNDERWRITING_DEFAULTS.copy()

def action_instruction(condition_name, action, decline_text, drop_text=None, cap_text=None, flag_text=None):
    """Convert an action value to Claude instruction text."""
    if action == 'decline' or action is True:
        return f"AUTO-DECLINE if: {decline_text}"
    elif action == 'drop':
        return f"DROP 1 TIER (do not decline) if: {drop_text or decline_text}"
    elif action == 'cap':
        return f"CAP loan at $100 (do not decline) if: {cap_text or decline_text}"
    elif action == 'flag':
        return f"FLAG as risk factor but do NOT decline if: {flag_text or decline_text}"
    else:  # 'off' or False
        return f"IGNORE (do not penalize) if: {decline_text}"

def build_underwriting_prompt(s):
    """Build underwriting instructions from current settings."""
    loan_min = s.get('loanMin', 100)
    loan_max = s.get('loanMax', 255)
    t1 = s.get('t1Fcf', 200)
    t2 = s.get('t2Fcf', 375)
    t3 = s.get('t3Fcf', 500)
    t4 = s.get('t4Fcf', 640)
    nsf_drop = s.get('nsfDrop', 2)
    nsf_cap = s.get('nsfCap', 4)
    nsf_dec = s.get('nsfDecline', 5)
    ft_drop = s.get('ftDrop', 5)
    ft_cap = s.get('ftCap', 7)
    ft_dec = s.get('ftDecline', 9)
    ft_abs = s.get('ftAbs', 11)
    neg_cap = s.get('negCap', 7)
    neg_dec = s.get('negDecline', 10)
    spec_drop = s.get('specDrop', 35)
    spec_cap = s.get('specCap', 50)
    return "\n".join([
        "You are a California DFPI-compliant payday loan underwriting analyst for Cash Rocket Anaheim.",
        "",
        "CRITICAL FORMAT RULE: Output ONLY raw HTML tags. Do NOT wrap in ```html or ``` code blocks. Do NOT use markdown. Start your response directly with <h1> tag. No preamble.",
        "STEP 1: Write the complete HTML report below. STEP 2: After the report, output the DECISION_BLOCK.",
        "",
        "Begin your HTML output now with exactly this structure:",
        "<h1>CASH IN FLASH — UNDERWRITING ANALYSIS</h1>",
        "<h2>Applicant Summary</h2><hr>",
        "<h2>1 Statement Verification</h2><hr>",
        "<h2>2 Income Analysis (Verified Deposits Only)</h2><hr>",
        "<h2>3 Expense and Cash-Flow Analysis</h2><hr>",
        "<h2>4 FCF Calculation — Show Your Work</h2><hr>",
        "<h2>5 DTI and Affordability</h2><hr>",
        "<h2>6 Risk Flags and Compliance</h2><hr>",
        "<h2>7 Final Decision</h2>",
        "",
        f"LOAN LIMITS: ${loan_min} min, ${loan_max} max.",
        "VERIFIED INCOME: payroll, govt benefits, pension, consistent gig only.",
        "NOT income: P2P transfers, internal transfers, refunds, loan proceeds, crypto, ATM, gambling.",
        "IMPORTANT: Ignore any self-reported gross pay from the application form. Base ALL income analysis solely on actual deposits visible in the bank statement or Plaid asset report.",
        "",
        "FCF TIERS:",
        f"T1: $100 loan requires FCF >= ${t1}",
        f"T2: $150 loan requires FCF >= ${t2}",
        f"T3: $200 loan requires FCF >= ${t3}",
        f"T4: $255 loan requires FCF >= ${t4}",
        "",
        "FINTECH DEFINITION: Only count known payday/cash-advance loan apps: Dave, Brigit, Earnin, MoneyLion, Klover, Albert, Cleo, FloatMe, Empower, Branch, B9, Chime SpotMe, Gerald, Payactiv, DailyPay, Even, Rain, Flex, Possible Finance, OppLoans, NetCredit, Kora, Varo Advance.",
        "DO NOT count as fintech: CashApp transfers, Venmo, Zelle, PayPal, Apple Pay, Google Pay, Amazon, Netflix, Spotify, Uber, DoorDash, or any P2P/subscription service.",
        "",
        "RISK ADJUSTMENTS:",
        f"NSF: 0-{nsf_drop-1}=none | {nsf_drop}-{nsf_cap-1}=drop 1 tier | {nsf_cap}=cap $100 | {nsf_dec}+=decline",
        f"Fintech apps: 0-{ft_drop-1}=none | {ft_drop}-{ft_cap-1}=drop 1 tier | {ft_cap}-{ft_dec-1}=cap $100 | {ft_dec}-{ft_abs-1}=decline | {ft_abs}+=absolute decline",
        f"Negative balance days: 0-{neg_cap-1}=none | {neg_cap}-{neg_dec-1}=cap $100 | {neg_dec}+=decline | avg below $0=decline",
        f"Speculative activity: 0-{spec_drop-1}%=none | {spec_drop}-{spec_cap-1}%=drop 1 tier | {spec_cap}%+=cap $100",
        "",
        "",
        "CONDITION ACTIONS — follow these exactly for each condition:",
        action_instruction("income", s.get("adNoIncome","decline"),
            "no verified payroll, government benefits, pension, or consistent gig income found"),
        action_instruction("closed", s.get("adClosed","decline"),
            "bank account is closed or restricted"),
        action_instruction("fraud", s.get("adFraud","decline"),
            "fraud indicators or suspicious patterns detected"),
        action_instruction("fcf", s.get("adFcf","decline"),
            f"free cash flow is below ${t1} (minimum tier threshold)"),
        action_instruction("avgbal", s.get("adAvgBal","decline"),
            "average daily balance is below $0"),
        action_instruction("jobloss", s.get("adJobLoss","decline"),
            "recent job loss or employment termination is indicated"),
        action_instruction("bankruptcy", s.get("adBankruptcy","decline"),
            "active bankruptcy filing is in progress"),
        action_instruction("stale", s.get("adStale","decline"),
            "bank statement is older than 30 days"),
        "IMPORTANT: Follow the CONDITION ACTIONS above precisely. If action is DROP/CAP/FLAG, do not decline for that reason alone.",
        "",
        "Section 4 MUST include a structured calculation table showing your work:",
        "<h3>Income Line Items</h3>",
        "<table><thead><tr><th>Date</th><th>Description</th><th>Amount</th><th>Category</th><th>Counted?</th><th>Reason</th></tr></thead><tbody>",
        "[One row per deposit — include ALL deposits, mark each as COUNTED or EXCLUDED with reason]",
        "</tbody></table>",
        "<p><b>Total Verified Income:</b> $[sum of all COUNTED deposits]</p>",
        "",
        "<h3>Expense Line Items — VERIFIED EXPENSES ONLY</h3>",
        "<p><b>COUNT as expenses:</b> Rent/mortgage ACH, utility bills, phone/telecom, insurance, loan/credit card payments, grocery stores (card), gas stations, subscriptions (Netflix/Adobe/etc).</p>",
        f"<p><b>ATM rule:</b> Withdrawals above ${s.get('atmThreshold',200)} — count {s.get('atmPct',50)}% of total as estimated cash expenses.</p>",
        "<p><b>DO NOT COUNT as expenses</b> (mirrors income exclusion): Zelle/Venmo/PayPal/CashApp outflows, internal transfers, transfers to self, loan repayments to fintech/payday apps, gambling/crypto, small ATM under threshold.</p>",
        "<table><thead><tr><th>Category</th><th>Amount</th><th>Counted?</th><th>Reason</th></tr></thead><tbody>",
        "[One row per expense category — COUNTED or EXCLUDED with reason]",
        "</tbody></table>",
        "<p><b>Total Verified Monthly Expenses:</b> $[sum of COUNTED only — do NOT include Zelle outflows or P2P transfers]</p>",
        "",
        "<p><b>FCF FORMULA: Verified Monthly Income − Verified Monthly Expenses = Free Cash Flow</b></p>",
        "<p><b>FCF Calculation: $[income] − $[expenses] = $[FCF]</b></p>",
        "",
        "Section 6 MUST include step-by-step tier breakdown:",
        "<p><b>Free Cash Flow:</b> $[amount]</p>",
        "<p><b>Base Tier Qualified:</b> Tier [X] - $[amount]</p>",
        "<p><b>NSF Adjustment:</b> [X] NSFs - [result]</p>",
        "<p><b>Fintech Adjustment:</b> [X] apps - [result]</p>",
        "<p><b>Negative Days Adjustment:</b> [X] days - [result]</p>",
        "<p><b>Speculative Adjustment:</b> [X]% - [result]</p>",
        "<p><b>Final Tier:</b> Tier [X] - $[amount] / Declined</p>",
        "<p><b>Final Decision:</b> [Approved $X / Declined]</p>",
        "<p><b>Compliance:</b> CDDTL compliant.</p>",
        "",
        "After the full report, output this block using the EXACT numbers from your Section 6 analysis above:",
        "DECISION_BLOCK_START",
        "APPLICANT_NAME: [Full name from document]",
        "APPLICANT_SSN: [Full SSN from document in XXX-XX-XXXX format, or from applicant info if provided]",
        "DECISION: [APPROVED or DECLINED — must match your Section 6 Final Decision]",
        "APPROVED_AMOUNT: [exact dollar amount from Section 6 or N/A]",
        "DECLINE_REASON: [1-2 plain English sentences summarizing Section 6 decline reason, or N/A if approved]",
        "APPROVAL_REASON: [1-2 plain English sentences summarizing why approved — include FCF amount, tier qualified, and key positive factors. Or N/A if declined]",
        "SCORE: [0-100 overall creditworthiness]",
        "DECISION_BLOCK_END",
    ])

def claude_api_call(system_prompt, user_content, max_tokens=8000):
    """Generic Claude API call — reusable for both extraction and narration."""
    payload = json.dumps({
        "model": "claude-haiku-4-5-20251001",
        "max_tokens": max_tokens,
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_content}]
    }, ensure_ascii=True).encode('utf-8')
    ctx = ssl.create_default_context()
    conn = http.client.HTTPSConnection('api.anthropic.com', timeout=300, context=ctx)
    conn.request('POST', '/v1/messages', body=payload, headers={
        'Content-Type': 'application/json',
        'x-api-key': ANTHROPIC_API_KEY,
        'anthropic-version': '2023-06-01',
        'Content-Length': str(len(payload))
    })
    resp = conn.getresponse()
    result = json.loads(resp.read().decode('utf-8'))
    conn.close()
    if 'error' in result:
        raise Exception(str(result['error']))
    return result['content'][0]['text']


def call_claude_extract(pdf_b64, applicant_info=''):
    """
    CALL 1 — Claude reads the document and extracts structured transaction data as JSON.
    No decision making. Pure extraction only.
    """
    extraction_prompt = """You are a bank statement data extraction specialist and transaction classifier. Your job is to extract ALL transaction data AND classify each transaction accurately.

DO NOT make any lending decisions. DO NOT approve or decline. Just extract and classify accurately.

Return ONLY a valid JSON object — no markdown, no explanation, no code fences. Start directly with {

Extract this exact structure:
{
  "account_holder_name": "Full name from statement",
  "account_number_last4": "last 4 digits only",
  "bank_name": "bank name",
  "statement_start": "YYYY-MM-DD",
  "statement_end": "YYYY-MM-DD",
  "statement_days": 30,
  "beginning_balance": 0.00,
  "ending_balance": 0.00,
  "avg_daily_balance": 0.00,
  "nsf_count": 0,
  "negative_days": 0,
  "account_closed": false,
  "fraud_indicators": false,
  "transactions": [
    {
      "date": "YYYY-MM-DD",
      "description": "exact description from statement",
      "amount": 0.00,
      "is_credit": true,
      "category": "payroll"
    }
  ]
}

IMPORTANT: "amount" must ALWAYS be a POSITIVE number (no negatives). Use "is_credit" to indicate direction (true=deposit, false=withdrawal).

TRANSACTION CLASSIFICATION RULES — assign exactly one category per transaction:

FOR CREDITS (is_credit=true), use these income categories:
- "payroll" — employer direct deposit, salary, wages (ACH from identifiable employer, payroll processor like ADP/Paychex/Gusto)
- "gig_income" — DoorDash, Uber, Lyft, Instacart, Amazon Flex, GrubHub, Shipt, TaskRabbit, Fiverr, Upwork
- "govt_benefits" — Social Security (SSA/SSI), disability, EDD, unemployment, CalWORKs, SNAP, veterans benefits, "Federal Benefit Credit" (this is SSA/SSI), VA payments, Treasury deposits, TANF, welfare, child tax credit, IHSS (In-Home Supportive Services), DPSS, General Relief, CalFresh
- "pension" — retirement payments, pension, annuity
- "child_support" — child support, alimony, spousal support
- "fintech_advance" — Dave, Brigit, Earnin, MoneyLion, Klover, Albert, Cleo, FloatMe, Empower/Tilt, Branch, B9, SpotMe, Gerald, Payactiv, DailyPay, Even, Rain, Flex, Possible Finance, OppLoans, NetCredit, Kora, Varo, MyPay, MyPayAdvance, Beem, Clair, Kikoff, CreditGenie, MoneyTree, TILT CASH ADVANCE
- "internal_transfer" — transfer between own accounts, from savings, from checking, from secured deposit
- "p2p_received" — Zelle received, Venmo received, CashApp received, PayPal received
- "loan_proceeds" — personal loan disbursement, installment loan, Upstart, LendingClub, Marcus, SoFi loan
- "tax_refund" — IRS, state tax refund, FTB
- "other_credit" — anything that doesn't fit above

FOR DEBITS (is_credit=false), use these expense categories:
- "rent" — rent, lease, property management, landlord payment
- "mortgage" — mortgage payment, home loan
- "utilities" — electric (SCE, SDG&E, PG&E, LADWP), gas (SoCalGas), water, trash, sewer
- "phone" — AT&T, Verizon, T-Mobile, Sprint, Cricket, MetroPCS, Boost, Total Wireless, Straight Talk, Mint Mobile, Visible, Consumer Cellular, any prepaid wireless
- "internet" — Spectrum, Comcast, Cox, AT&T Internet, Google Fiber, Starlink
- "insurance" — AAA, State Farm, Geico, Progressive, Allstate, Liberty Mutual, Farmers, USAA, health insurance, renters insurance, auto insurance, life insurance
- "groceries" — Walmart, Target (grocery), Kroger, Vons, Ralphs, Stater Bros, Food4Less, El Super, Aldi, Trader Joe's, Whole Foods, Costco, Smart & Final, WinCo, 99 Ranch, Superior Grocers, any supermarket or grocery store
- "gas_fuel" — Chevron, Shell, Arco, BP, Mobil, Exxon, Valero, Texaco, 76, Circle K fuel, Speedway, QuikTrip, Wawa fuel, Ace Fuels, any gas station
- "restaurants" — restaurants, fast food, food delivery (DoorDash charge, Uber Eats charge, GrubHub charge)
- "subscriptions" — Netflix, Hulu, Disney+, Spotify, Apple Music, YouTube Premium, HBO, Paramount+, Amazon Prime, Adobe, Microsoft 365, iCloud, Google One, Dropbox, ExpressVPN, NordVPN, Lucid, BeenVerified, any recurring subscription
- "loan_payment" — credit card payment, auto loan, student loan, personal loan payment, Capital One payment, Chase payment, Synchrony, Discover, American Express, any lender payment
- "childcare" — daycare, preschool, after school, childcare provider
- "transportation" — public transit, Uber ride, Lyft ride, bus pass, metro, parking
- "medical" — pharmacy, doctor, hospital, dental, vision, Walgreens Rx, CVS Rx
- "atm" — ATM withdrawal, cash withdrawal
- "fintech_repayment" — repayment to Dave, Brigit, Earnin, MoneyLion, Albert, Cleo, Empower/Tilt, Klover, MyPay repayment, Branch, any payday/advance app repayment, Cleo subscription
- "internal_transfer" — transfer to savings, transfer to checking, transfer to secured deposit, Round Up, own account transfer, Chime savings transfer
- "p2p_sent" — Zelle sent, Venmo sent, CashApp sent, PayPal sent, Apple Cash sent
- "speculative" — casino, gambling, lottery, bet, DraftKings, FanDuel, Bovada, crypto exchange (Coinbase, Binance, Kraken), NFT
- "fee" — bank fee, overdraft fee, ATM fee, wire fee, monthly service fee, outbound instant transfer fee
- "other_expense" — anything that doesn't fit above

IMPORTANT CLASSIFICATION NOTES:
- "Return of posted check item", "Returned item", "Payment reversal" = other_credit (bounced payment return — the decision engine handles offsetting)
- "Koalafi", "Snap Finance", "Progressive Leasing", "Katapult" = fintech_repayment (lease-to-own / BNPL providers)
- "Moved from/to Secured Deposit Account" = internal_transfer
- "Round Up to Savings" = internal_transfer
- "Transfer to/from Visa/Mastercard [number]" = internal_transfer (own credit card)
- "Transfer to Mom/Dad/[name]" = p2p_sent (personal transfer)
- "Wilshire Consumer", "Atlas Financial" = loan_payment (installment lender)
- "Upstart Network" = loan_payment or fintech_repayment
- "Albert" direct debit = fintech_repayment
- "Pnm*Consumer Portfolio" = loan_payment
- "Apple Com" = subscriptions
- "Tilt Finance" fee = fintech_repayment
- When in doubt between loan_payment and fintech_repayment: if it's a payday/cash advance app = fintech_repayment; if it's an installment/personal lender = loan_payment

Rules:
- is_credit=true for deposits/additions, is_credit=false for withdrawals/subtractions
- Include EVERY transaction — do not skip any
- Keep descriptions SHORT — max 50 characters, trim long merchant names
- nsf_count = number of NSF fees, returned items, or overdraft fees charged
- negative_days = number of days the ending daily balance was below $0
- fraud_indicators = true only if you see obvious fraud (large same-day round-trip transfers, multiple failed/returned transactions suggesting kiting)
- avg_daily_balance = calculate from ending daily balances shown in statement
- IMPORTANT: Be concise in descriptions to keep response size small
"""
    if applicant_info:
        extraction_prompt += f"\n\nAPPLICANT CONTEXT (for name matching only):\n{applicant_info}"

    user_content = [
        {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": pdf_b64}},
        {"type": "text", "text": "Extract all transaction data from this document as JSON:"}
    ]
    raw = claude_api_call(extraction_prompt, user_content, max_tokens=32000)
    # Clean any accidental fences
    raw = re.sub(r'^```[a-z]*\n?', '', raw.strip(), flags=re.MULTILINE)
    raw = re.sub(r'```\s*$', '', raw.strip(), flags=re.MULTILINE)
    raw = raw.strip()
    # Find JSON object boundaries in case Claude added any preamble
    start = raw.find('{')
    end = raw.rfind('}')
    if start >= 0 and end > start:
        raw = raw[start:end+1]
    try:
        return json.loads(raw)
    except Exception as e:
        print(f'[ENGINE ERROR] JSON parse failed: {e}', flush=True)
        print(f'[ENGINE ERROR] Raw length: {len(raw)} chars', flush=True)
        print(f'[ENGINE ERROR] Raw (last 300): {raw[-300:]}', flush=True)
        # Try to recover truncated JSON
        try:
            opens = raw.count('[') - raw.count(']')
            braces = raw.count('{') - raw.count('}')
            recovery = raw
            last_complete = recovery.rfind('},')
            if last_complete > 0:
                recovery = recovery[:last_complete+1]
                opens = recovery.count('[') - recovery.count(']')
                braces = recovery.count('{') - recovery.count('}')
            recovery += ']' * opens + '}' * braces
            result = json.loads(recovery)
            print(f'[ENGINE] Recovered truncated JSON with {len(result.get("transactions",[]))} transactions', flush=True)
            return result
        except Exception as e2:
            print(f'[ENGINE ERROR] Recovery failed: {e2}', flush=True)
            raise Exception(f'Transaction extraction failed — JSON truncated. Statement may be too large.')


def build_report_html(engine_result, applicant_info, settings):
    """Build complete HTML underwriting report — pure Python, no Claude needed."""
    s = settings
    er = engine_result

    # Tag items with indices for override mapping
    for idx, item in enumerate(er.get('income_items', [])):
        item['_idx'] = idx
        raw = item.get('category', '').lower().replace(' ', '_')
        if not item.get('_raw_cat'): item['_raw_cat'] = raw
    for idx, item in enumerate(er.get('expense_items', [])):
        item['_idx'] = 1000 + idx  # offset to avoid collision with income indices
        raw = item.get('category', '').lower().replace(' ', '_')
        if not item.get('_raw_cat'): item['_raw_cat'] = raw

    def cd(d, maxlen=40):
        d = re.sub(r'\s+(REF|ID|PPD ID|TRN|IID|RECD)[:\s#]\S+', '', d, flags=re.IGNORECASE)
        d = re.sub(r'\s+[A-Z0-9]{10,}\s*$', '', d.strip())
        d = re.sub(r'\s+\d{5,}\s*\d{2}/\d{2}$', '', d.strip())
        return d[:maxlen] + ('…' if len(d) > maxlen else '')

    G = '#1a6b3c'  # green
    R = '#c0392b'  # red
    ok = er['decision'] == 'APPROVED'
    dc = G if ok else R

    # ── Helper: group items by category ──
    def group_items(items):
        groups = {}
        for i in items:
            cat = i.get('category', 'Other').split('(')[0].strip()
            amt = abs(i.get('counted_amount', i.get('amount', 0)))
            groups[cat] = groups.get(cat, {'count': 0, 'total': 0.0, 'items': []})
            groups[cat]['count'] += 1
            groups[cat]['total'] += amt
            groups[cat]['items'].append(i)
        return groups

    # ── Income rows ──
    counted_inc = [i for i in er['income_items'] if i['counted']]
    excluded_inc = [i for i in er['income_items'] if not i['counted']]
    inc_groups = group_items(counted_inc)
    exc_inc_groups = group_items(excluded_inc)

    CATS_INC = ['payroll','gig_income','govt_benefits','pension','child_support','p2p_received','fintech_advance','internal_transfer','cash_deposit','other_credit']
    CATS_EXP = ['rent','utilities','insurance','groceries','gas_fuel','restaurants','subscriptions','loan_payment','fintech_repayment','bnpl_payment','atm','money_order','p2p_sent','medical','transportation','childcare','speculative','other_expense','internal_transfer']

    # Helper JS functions injected once at top of report (not in a script tag — using onclick calls)
    js_helpers = """<div id="cif-helpers" style="display:none" data-init="true"></div>"""

    def detail_rows(items, color, section='income'):
        cats = CATS_INC if section == 'income' else CATS_EXP
        rows = ''
        for it in items:
            idx = it.get('_idx', 0)
            raw_cat = it.get('_raw_cat', '')
            counted = it.get('counted', False)
            conf = it.get('confidence', 'medium')
            # Confidence badge
            cc = {'high':'#27ae60','medium':'#f39c12','low':'#e74c3c'}.get(conf, '#999')
            cb = f"<span style='background:{cc};color:#fff;padding:1px 5px;border-radius:8px;font-size:9px;font-weight:700;margin-left:4px'>{conf}</span>"
            # Category dropdown
            opts = ''.join(f"<option value='{c}'{' selected' if c==raw_cat else ''}>{c.replace('_',' ').title()}</option>" for c in cats)
            dd = (f"<select data-idx='{idx}' "
                  f"onchange=\"if(!window._ov)window._ov={{}};if(!window._ov['{idx}'])window._ov['{idx}']={{}};window._ov['{idx}'].category=this.value;window.__txnOverrides=window._ov;var b=document.getElementById('recalc-bar');if(b)b.style.display='block';var c=document.getElementById('recalc-count');if(c)c.textContent=Object.keys(window._ov).length+' changes pending'\" "
                  f"style='font-size:11px;padding:2px 4px;border:1px solid #ddd;border-radius:4px;background:#fff;max-width:140px'>{opts}</select>")
            # Toggle button
            tl = '&#10003; Counted' if counted else '&#10007; Excluded'
            tc = '#27ae60' if counted else '#e74c3c'
            tb = '#d4edda' if counted else '#fde8e8'
            tog = (f"<button data-idx='{idx}' data-counted='{'true' if counted else 'false'}' "
                   f"onclick=\"event.stopPropagation();var t=this;var was=(t.getAttribute('data-counted')==='true');var nw=!was;t.setAttribute('data-counted',nw?'true':'false');t.innerHTML=nw?'&#10003; Counted':'&#10007; Excluded';t.style.background=nw?'#d4edda':'#fde8e8';t.style.color=nw?'#27ae60':'#e74c3c';t.style.borderColor=nw?'#27ae60':'#e74c3c';if(!window._ov)window._ov={{}};if(!window._ov['{idx}'])window._ov['{idx}']={{}};window._ov['{idx}'].counted=nw;window.__txnOverrides=window._ov;var b=document.getElementById('recalc-bar');if(b)b.style.display='block';var c=document.getElementById('recalc-count');if(c)c.textContent=Object.keys(window._ov).length+' changes pending'\" "
                   f"style='font-size:10px;padding:2px 8px;border:1px solid {tc};border-radius:12px;background:{tb};color:{tc};cursor:pointer;font-weight:600;white-space:nowrap'>{tl}</button>")
            rows += (
                f"<tr data-idx='{idx}' style='font-size:12px;color:#666'>"
                f"<td style='padding-left:24px'>{cd(it.get('desc',''),50)}{cb}</td>"
                f"<td>{it.get('date','')}</td>"
                f"<td style='color:{color}'>${abs(it.get('counted_amount', it.get('amount',0))):,.2f}</td>"
                f"<td>{dd}</td>"
                f"<td>{tog}</td>"
                f"<td style='font-size:11px;max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap'>{it.get('reason','')[:60]}</td>"
                f"</tr>"
            )
        return rows

    income_rows = ''
    grp_id = 0
    for cat, v in inc_groups.items():
        gid = f'ig{grp_id}'; grp_id += 1
        detail_html = detail_rows(v['items'], G, 'income')
        income_rows += (
            f"<tr style='background:#f0fff4;cursor:pointer' onclick=\"var d=document.getElementById('{gid}');d.style.display=d.style.display==='none'?'':'none'\">"
            f"<td><b>{cat}</b></td><td>{v['count']} deposit{'s' if v['count']>1 else ''}</td>"
            f"<td style='color:{G};font-weight:700'>${v['total']:,.2f}</td>"
            f"<td colspan='3'><span style='background:#d4edda;color:{G};padding:2px 8px;border-radius:12px;font-size:12px;font-weight:700'>✓ Counted</span></td></tr>"
            f"<tr id='{gid}' style='display:none'><td colspan='6' style='padding:0'><table style='width:100%;border-collapse:collapse'>{detail_html}</table></td></tr>"
        )
    for cat, v in exc_inc_groups.items():
        gid = f'ig{grp_id}'; grp_id += 1
        detail_html = detail_rows(v['items'], R, 'income')
        income_rows += (
            f"<tr style='background:#fff8f8;cursor:pointer' onclick=\"var d=document.getElementById('{gid}');d.style.display=d.style.display==='none'?'':'none'\">"
            f"<td style='color:#888;font-style:italic'>{cat}</td><td style='color:#888'>{v['count']}×</td>"
            f"<td style='color:{R}'>${v['total']:,.2f}</td><td colspan='3' style='color:#888;font-size:12px'>Excluded</td></tr>"
            f"<tr id='{gid}' style='display:none'><td colspan='6' style='padding:0'><table style='width:100%;border-collapse:collapse'>{detail_html}</table></td></tr>"
        )

    # ── Expense rows ──
    counted_exp = [e for e in er['expense_items'] if e.get('counted')]
    excluded_exp = [e for e in er['expense_items'] if not e.get('counted')]
    exp_groups = group_items(counted_exp)
    exc_exp_groups = group_items(excluded_exp)

    expense_rows = ''
    for cat, v in exp_groups.items():
        gid = f'eg{grp_id}'; grp_id += 1
        detail_html = detail_rows(v['items'], G, 'expense')
        expense_rows += (
            f"<tr style='background:#f0fff4;cursor:pointer' onclick=\"var d=document.getElementById('{gid}');d.style.display=d.style.display==='none'?'':'none'\">"
            f"<td><b>{cat}</b></td><td>{v['count']} txn{'s' if v['count']>1 else ''}</td>"
            f"<td style='color:{G};font-weight:700'>${v['total']:,.2f}</td>"
            f"<td colspan='3'><span style='background:#d4edda;color:{G};padding:2px 8px;border-radius:12px;font-size:12px;font-weight:700'>✓ Counted</span></td></tr>"
            f"<tr id='{gid}' style='display:none'><td colspan='6' style='padding:0'><table style='width:100%;border-collapse:collapse'>{detail_html}</table></td></tr>"
        )
    for cat, v in exc_exp_groups.items():
        gid = f'eg{grp_id}'; grp_id += 1
        detail_html = detail_rows(v['items'], R, 'expense')
        expense_rows += (
            f"<tr style='background:#fff8f8;cursor:pointer' onclick=\"var d=document.getElementById('{gid}');d.style.display=d.style.display==='none'?'':'none'\">"
            f"<td style='color:#888;font-style:italic'>{cat}</td><td style='color:#888'>{v['count']}×</td>"
            f"<td style='color:{R}'>${v['total']:,.2f}</td><td colspan='3' style='color:#888;font-size:12px'>Excluded</td></tr>"
            f"<tr id='{gid}' style='display:none'><td colspan='6' style='padding:0'><table style='width:100%;border-collapse:collapse'>{detail_html}</table></td></tr>"
        )

    # ── Tier waterfall ──
    tiers = [
        (4, s.get('loanMax', 255), s.get('t4Fcf', 640)),
        (3, s.get('t3Amount', 200), s.get('t3Fcf', 500)),
        (2, s.get('t2Amount', 150), s.get('t2Fcf', 375)),
        (1, s.get('t1Amount', 100), s.get('t1Fcf', 200)),
    ]
    tier_rows = ''.join(
        f"<tr><td>Tier {t} (${a})</td><td>FCF ≥ ${thresh}</td>"
        f"<td style='color:{G if er['fcf']>=thresh else R};font-weight:700'>{'✓ PASS' if er['fcf']>=thresh else '✗ FAIL'}</td></tr>"
        for t, a, thresh in tiers
    )

    adj_items = ''.join(f"<li style='margin-bottom:6px'>{a}</li>" for a in er['adjustments']) if er['adjustments'] else '<li>No adjustments applied</li>'
    if er['decline_reasons']:
        decline_items = ''.join(f"<li style='margin-bottom:6px'>{r}</li>" for r in er['decline_reasons'])
    elif er.get('decline_reason_text'):
        decline_items = f"<li style='margin-bottom:6px'>{er['decline_reason_text']}</li>"
    else:
        decline_items = '<li>None</li>'

    # ── Fintech apps table ──
    ft_list = er.get('fintech_apps_list', [])
    ft_html = ''
    if ft_list:
        ft_html = '<p><b>Fintech apps detected:</b> ' + ', '.join(ft_list) + f' ({len(ft_list)} unique)</p>'

    # ── Expense floor note ──
    floor_note = ''
    if er.get('expense_floor_applied'):
        floor_note = f"<p style='color:#888;font-style:italic'>Expense floor of ${s.get('expenseFloor',800):,}/month was applied (actual counted expenses were lower).</p>"

    # ── P2P scenario section ──
    p2p_section = ''
    p2p_sc = er.get('p2p_scenario')
    if p2p_sc:
        sender_rows = ''.join(
            f"<tr><td>{name}</td><td>{info['count']} deposits</td><td>${info['total']:,.2f}</td></tr>"
            for name, info in p2p_sc['recurring_senders'].items()
        )
        p2p_section = f"""<h2>P2P Income Scenario (For Reviewer Reference)</h2><hr>
<p style="color:#888;font-style:italic">This section shows what the decision would look like if recurring P2P deposits (same sender, 2+ times) were counted at 50%. This is NOT part of the official decision — it's for manual review consideration only.</p>
<table style="width:100%;border-collapse:collapse"><thead><tr style="background:#f8f8f8"><th style="text-align:left;padding:8px">Sender</th><th>Deposits</th><th>Total</th></tr></thead>
<tbody>{sender_rows}</tbody></table>
<p><b>Recurring P2P Total:</b> ${p2p_sc['recurring_total']:,.2f} (counted at 50% = ${p2p_sc['monthly_add']:,.2f}/mo added to income)</p>
<p><b>Scenario Income:</b> ${p2p_sc['scenario_income']:,.2f}/mo | <b>Scenario FCF:</b> ${p2p_sc['scenario_fcf']:,.2f} | <b>Scenario Tier:</b> {'Tier ' + str(p2p_sc['scenario_tier']) + ' ($' + str(p2p_sc['scenario_amount']) + ')' if p2p_sc['scenario_tier'] > 0 else 'Still Tier 0 (Declined)'}</p>"""

    # ── Annualization note ──
    ann_note = ''
    if er['statement_days'] != 30:
        multiplier = 30 / max(er['statement_days'], 1)
        ann_note = f'<p style="font-size:12px;color:#888;font-style:italic;margin-top:4px">Statement covers {er["statement_days"]} days — amounts normalized to 30-day month (×{multiplier:.2f})</p>'

    # ── Build full report ──
    return f"""<div class="report-card">
<h2>1. Statement Verification</h2>
<p>Account holder <b>{er.get('account_holder_name', 'N/A')}</b> — {er['statement_days']}-day statement — <b>{len(er.get('income_items',[]))+len(er.get('expense_items',[]))}</b> classified transactions.</p>
</div>

<div class="report-card">
<h2>2. Income Analysis</h2>
<p>Only verified recurring income is counted. P2P transfers, internal transfers, fintech advances, and other credits are excluded.</p>
<p style="font-size:12px;color:#888;margin-bottom:4px">Click any row to expand — reclassify transactions and recalculate ▾</p>
<table style="width:100%;border-collapse:collapse"><thead><tr style="background:#f8f8f8"><th style="text-align:left;padding:8px">Category</th><th>Count</th><th>Amount</th><th>Reclassify</th><th>Action</th><th>Reason</th></tr></thead>
<tbody>{income_rows}</tbody></table>
<p style="margin-top:12px"><b>Total Verified Monthly Income: <span style="color:{G}">${er['monthly_income']:,.2f}</span></b></p>
{ann_note}
</div>

<div class="report-card">
<h2>3. Expense Analysis</h2>
<p>Verified recurring expenses counted. Internal transfers, P2P outflows, fees, and fintech repayments excluded.</p>
<p style="font-size:12px;color:#888;margin-bottom:4px">Click any row to expand — reclassify transactions and recalculate ▾</p>
<table style="width:100%;border-collapse:collapse"><thead><tr style="background:#f8f8f8"><th style="text-align:left;padding:8px">Category</th><th>Count</th><th>Amount</th><th>Reclassify</th><th>Action</th><th>Reason</th></tr></thead>
<tbody>{expense_rows}</tbody></table>
<p style="margin-top:12px"><b>Total Verified Monthly Expenses: <span style="color:{R}">${er['monthly_expenses']:,.2f}</span></b></p>
{ann_note}
{floor_note}
</div>

<div class="report-card">
<h2>4. Free Cash Flow & Tier Qualification</h2>
<p style="font-size:16px"><b>FCF = ${er['monthly_income']:,.2f} − ${er['monthly_expenses']:,.2f} = <span style="color:{G if er['fcf']>=0 else R}">${er['fcf']:,.2f}</span></b></p>
<table style="width:100%;border-collapse:collapse;margin:12px 0"><thead><tr style="background:#f8f8f8"><th style="text-align:left;padding:8px">Tier</th><th>Requirement</th><th>Result</th></tr></thead>
<tbody>{tier_rows}</tbody></table>
<p><b>Base Tier: Tier {er['base_tier']} (${er['base_amount']})</b></p>
<p><b>Final Tier: {'Declined' if er['amount']==0 else f"Tier {er['final_tier']} (${er['amount']})"}</b></p>
</div>

<div class="report-card">
<h2>5. Risk Adjustments</h2>
<ul>{adj_items}</ul>
{ft_html}
</div>

<div class="report-card">
<h2>6. Risk Flags</h2>
<ul>
<li><b>NSF Events:</b> {er['nsf_count']}</li>
<li><b>Fintech Apps:</b> {er['fintech_count']} unique</li>
<li><b>Negative Balance Days:</b> {er['negative_days']}</li>
<li><b>Speculative Activity:</b> {er['spec_pct']}%</li>
<li><b>Ending Balance:</b> ${er.get('ending_balance', 0):,.2f}</li>
<li><b>Bounced Payments:</b> {er.get('bounced_count', 0)}{f" (${er.get('bounced_total', 0):,.2f} offset)" if er.get('bounced_count', 0) > 0 else ""}</li>
</ul>
</div>

{f'<div class="report-card">{p2p_section}</div>' if p2p_section else ''}

<div class="report-card">
<h2>7. Final Decision</h2>
{'<p><b>Decline Reasons:</b></p><ul>' + decline_items + '</ul>' if not ok else f'<p style="color:{G};font-size:16px;font-weight:700">✓ Approved for ${er["amount"]}</p>'}
</div>
<p style="font-size:11px;color:#aaa;margin-top:12px;text-align:center">Deterministic underwriting engine — all numbers are calculated, not AI-generated.</p>

<div id="recalc-bar" style="position:sticky;bottom:0;background:linear-gradient(180deg,rgba(255,255,255,0) 0%,#fff 12%);padding:16px 18px 12px;text-align:center;z-index:10;display:none;border-top:2px solid #1a6b3c">
  <button id="recalc-btn" onclick="if(window.recalculateDecision)window.recalculateDecision()" style="background:#1a6b3c;color:#fff;border:none;padding:10px 32px;border-radius:8px;font-size:14px;font-weight:700;cursor:pointer;font-family:inherit;box-shadow:0 2px 8px rgba(0,0,0,.15)">↻ Recalculate Decision</button>
  <span id="recalc-count" style="margin-left:12px;font-size:13px;color:#666">0 changes pending</span>
</div>"""


def call_claude(pdf_b64, applicant_info=''):
    """
    LEGACY WRAPPER — kept for compatibility.
    Now calls the hybrid two-step system internally.
    """
    settings = get_underwriting_settings()
    # Step 1: Extract
    print('[ENGINE] Step 1 — Extracting transactions...', flush=True)
    extracted = call_claude_extract(pdf_b64, applicant_info)
    print(f'[ENGINE] Extracted {len(extracted.get("transactions",[]))} transactions, '
          f'{extracted.get("nsf_count",0)} NSFs, {extracted.get("negative_days",0)} neg days', flush=True)

    # Step 2: Decision engine
    print('[ENGINE] Step 2 — Running decision engine...', flush=True)
    from decision_engine import run_decision_engine
    engine_result = run_decision_engine(extracted, settings)
    print(f'[ENGINE] Decision={engine_result["decision"]} FCF=${engine_result["fcf"]} '
          f'Tier={engine_result["final_tier"]} Amount=${engine_result["amount"]}', flush=True)

    # Step 3: Build report (deterministic — no Claude needed)
    print('[ENGINE] Step 3 — Building report...', flush=True)
    report_html = build_report_html(engine_result, applicant_info, settings)

    # Build decision block from engine result (not Claude)
    score = calculate_score(engine_result)
    approval_reason = ''
    decline_reason = ''
    if engine_result['decision'] == 'APPROVED':
        approval_reason = (f"FCF ${engine_result['fcf']:,.2f} qualifies for Tier {engine_result['final_tier']} "
                          f"(${engine_result['amount']}). {engine_result['adjustments'][0] if engine_result['adjustments'] else ''}")
    else:
        decline_reason = engine_result['decline_reason_text']

    decision_block = f"""
DECISION_BLOCK_START
APPLICANT_NAME: {extracted.get('account_holder_name','Unknown')}
APPLICANT_SSN: N/A
DECISION: {engine_result['decision']}
APPROVED_AMOUNT: {'$'+str(engine_result['amount']) if engine_result['decision']=='APPROVED' else 'N/A'}
DECLINE_REASON: {decline_reason if decline_reason else 'N/A'}
APPROVAL_REASON: {approval_reason if approval_reason else 'N/A'}
SCORE: {score}
DECISION_BLOCK_END
"""
    # Stash engine metrics for process_submission to save to Firebase
    call_claude._last_metrics = {
        'fcf': round(engine_result['fcf'], 2),
        'monthlyIncome': round(engine_result['monthly_income'], 2),
        'monthlyExpenses': round(engine_result['monthly_expenses'], 2),
        'fintechCount': engine_result['fintech_count'],
        'nsfCount': engine_result['nsf_count'],
        'dti_ratio': round(engine_result.get('dti_ratio', 0), 1),
        'review_tier': engine_result.get('review_tier', 'full'),
    }
    call_claude._last_extracted = extracted
    return report_html + '\n' + decision_block


def calculate_score(er):
    """Calculate a 0-100 credit score from engine results."""
    score = 50  # base
    # FCF contribution (up to +30)
    if er['fcf'] > 0:
        score += min(30, int(er['fcf'] / 100))
    else:
        score += max(-20, int(er['fcf'] / 100))
    # NSF penalty
    score -= er['nsf_count'] * 5
    # Fintech penalty
    score -= er['fintech_count'] * 3
    # Negative days penalty
    score -= er['negative_days'] * 2
    # Tier bonus
    score += er['final_tier'] * 5
    return min(100, max(0, score))


def parse_decision(text):
    m = re.search(r'DECISION_BLOCK_START([\s\S]*?)DECISION_BLOCK_END', text)
    if not m:
        return {'name':'Unknown','decision':'PENDING','amount':'','reason':'','approvalReason':'','score':50}
    b = m.group(1)
    def g(pat): r=re.search(pat,b); return r.group(1).strip() if r else ''
    score_m = re.search(r'SCORE:\s*(\d+)', b)
    amt = g(r'APPROVED_AMOUNT:\s*(.+)')
    reason = g(r'DECLINE_REASON:\s*(.+)')
    approval_reason = g(r'APPROVAL_REASON:\s*(.+)')
    ssn_val = g(r'APPLICANT_SSN:\s*(.+)')
    return {
        'name':           g(r'APPLICANT_NAME:\s*(.+)') or 'Unknown',
        'ssn':            ssn_val if ssn_val and ssn_val != 'N/A' else '',
        'decision':       (g(r'DECISION:\s*(.+)') or 'PENDING').upper(),
        'amount':         '' if amt in ('N/A','') else amt.replace('$','').strip(),
        'reason':         '' if reason in ('N/A','') else reason,
        'approvalReason': '' if approval_reason in ('N/A','') else approval_reason,
        'score':          min(100,max(0,int(score_m.group(1)))) if score_m else 50
    }

# ══════════════════════════════════════════
# PROCESS SUBMISSION (runs in background thread)
# ══════════════════════════════════════════
_SKIPLIST_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    'engine_v2', 'categorization', 'entities_skip.json',
)


def _load_skiplist() -> set:
    try:
        with open(_SKIPLIST_PATH, 'r') as f:
            data = json.load(f)
        return set(data.get('patterns') or [])
    except (FileNotFoundError, json.JSONDecodeError):
        return set()


def _save_skiplist(patterns: set) -> None:
    payload = {
        '_meta': {'description': 'Patterns dismissed from the Review Queue as non-merchants/noise.'},
        'patterns': sorted(patterns),
    }
    with open(_SKIPLIST_PATH, 'w') as f:
        json.dump(payload, f, indent=2)


# Light-touch suggestion engine — looks at Plaid PFC majority + cheap keyword hints
# to pre-fill the Review Queue dropdowns. Underwriter still confirms before save.
_PLAID_PFC_TO_CATEGORY = {
    # Credit (money in)
    ('INCOME', True): 'payroll',
    ('TRANSFER_IN', True): 'internal_transfer',
    # Debit (money out)
    ('LOAN_PAYMENTS', False): 'loan_payment',
    ('BANK_FEES', False): 'fee',
    ('TRANSFER_OUT', False): 'internal_transfer',
    ('RENT_AND_UTILITIES', False): 'utilities',
    ('FOOD_AND_DRINK', False): 'restaurants',
    ('MEDICAL', False): 'medical',
    ('TRANSPORTATION', False): 'transportation',
    ('ENTERTAINMENT', False): 'subscriptions',
    ('GENERAL_MERCHANDISE', False): 'other_expense',
}

_KEYWORD_HINTS = [
    # (substring, credit_cat, debit_cat)
    # Order matters — more specific patterns FIRST so they win over generic ones.
    # Zelle / Faster-Payments truncations MUST come before WITHDRAWAL or ATM.
    ('FASTER PAYMENTS', 'p2p_received', 'p2p_sent'),
    ('ZEL*', 'p2p_received', 'p2p_sent'),
    ('ZELLE', 'p2p_received', 'p2p_sent'),
    ('VENMO', 'p2p_received', 'p2p_sent'),
    ('CASHAPP', 'p2p_received', 'p2p_sent'),
    ('CASH APP', 'p2p_received', 'p2p_sent'),
    # Proper ATM (requires ATM token explicitly, not just "WITHDRAWAL")
    ('ATM WITHDRAWAL', None, 'atm'),
    ('ATM WDRL', None, 'atm'),
    ('CASH WITHDRAWAL', None, 'atm'),
    ('ATM DEBIT', None, 'atm'),
    ('ATM', None, 'atm'),
    ('PAYROLL', 'payroll', None),
    ('DIRECT DEP', 'payroll', None),
    ('PAYCHECK', 'payroll', None),
    ('UBER', 'gig_income', 'transportation'),
    ('LYFT', 'gig_income', 'transportation'),
    ('DOORDASH', 'gig_income', 'restaurants'),
    ('INSTACART', 'gig_income', 'groceries'),
    ('TRANSFER', 'internal_transfer', 'internal_transfer'),
    ('DEPOSIT', 'cash_deposit', None),
    ('FEE', None, 'fee'),
    ('OVERDRAFT', None, 'fee'),
    ('LOAN', 'loan_proceeds', 'loan_payment'),
    ('FINANCE', 'loan_proceeds', 'loan_payment'),
    ('CREDIT CARD', None, 'loan_payment'),
    ('RENT', None, 'rent'),
    ('APART', None, 'rent'),
    ('INSUR', None, 'insurance'),
    ('SSA ', 'govt_benefits', None),
    ('SOCIAL SECURITY', 'govt_benefits', None),
    ('IRS', 'govt_benefits', None),
    ('EDD', 'govt_benefits', None),
    ('UNEMPLOYMENT', 'govt_benefits', None),
]


def _suggest_categories(merchant: dict) -> tuple[str | None, str | None, str]:
    """Return (credit_suggestion, debit_suggestion, source).
    Picks the most confident of: Plaid PFC majority → keyword hint → none."""
    pattern = (merchant.get('pattern') or '').upper()
    plaid_pfcs = merchant.get('plaid_pfcs') or {}
    credit = debit = None
    source = 'none'

    # Plaid-majority wins if we have any
    if plaid_pfcs:
        top_pfc, _ = max(plaid_pfcs.items(), key=lambda kv: kv[1])
        if merchant.get('credit_count'):
            credit = _PLAID_PFC_TO_CATEGORY.get((top_pfc, True))
        if merchant.get('debit_count'):
            debit = _PLAID_PFC_TO_CATEGORY.get((top_pfc, False))
        if credit or debit:
            source = f'plaid:{top_pfc.lower()}'

    # Fall back (or supplement) with keyword hints on the pattern itself
    if not credit or not debit:
        for kw, cr, db in _KEYWORD_HINTS:
            if kw in pattern:
                if not credit and cr:
                    credit = cr
                if not debit and db:
                    debit = db
                if source == 'none':
                    source = f'keyword:{kw.strip().lower()}'
                if credit and debit:
                    break

    return credit, debit, source


def _extract_v2_unclassified(v2_result):
    """Pull compact summary of unclassified transactions for the Review Queue."""
    items = []
    for t in (v2_result.categorized_transactions or [])[:500]:
        if t.get('v2_category') == 'unclassified':
            pfc = None
            pfc_obj = t.get('personal_finance_category')
            if isinstance(pfc_obj, dict):
                pfc = pfc_obj.get('primary')
            pfc = pfc or t.get('plaid_pfc_primary') or None
            items.append({
                'description': (t.get('description') or '')[:120],
                'is_credit': bool(t.get('is_credit')),
                'amount': float(t.get('amount') or 0),
                'date': t.get('date') or '',
                'plaid_pfc': pfc,
            })
    return items


def _run_v2_shadow(firebase_id, extracted_data, application_data):
    """Run engine_v2 in shadow mode and patch v2* fields into the report.

    Never raises — v2 failures must not block v1. If v2 crashes, we log
    and patch a marker field so we know it ran but failed.
    """
    if not extracted_data:
        return
    try:
        from engine_v2 import run_v2
        from engine_v2.report_html import render as render_v2_html
        v2_result = run_v2(extracted_data, application_data or {})
        v2_html = render_v2_html(v2_result, application_data or {})
        unclassified = _extract_v2_unclassified(v2_result)
        firebase_patch(f'reports/{firebase_id}', {
            'v2Decision': v2_result.decision.outcome.upper(),
            'v2TierAmount': v2_result.decision.tier_amount,
            'v2MaxAffordable': v2_result.affordability.max_affordable_loan_amount,
            'v2FcfMonthly': round(v2_result.affordability.fcf_monthly, 2),
            'v2Confidence': v2_result.affordability.confidence,
            'v2Report': v2_html,
            'v2ReasonsJson': json.dumps(v2_result.decision.reasons),
            'v2ReviewFlagsJson': json.dumps(v2_result.decision.review_flags),
            'v2ReconciliationOk': v2_result.reconciliation.ok,
            'v2ReconciliationError': v2_result.reconciliation.error,
            'v2UnclassifiedJson': json.dumps(unclassified),
            'v2UnclassifiedCount': len(unclassified),
            'v2AutoDecide': bool(v2_result.summary.get('auto_decide_candidate')),
            'v2RunAt': int(time.time() * 1000),
            'v2Auto': True,
        })
        print(f'[V2-SHADOW] {firebase_id} -> {v2_result.decision.outcome} ${v2_result.decision.tier_amount} (unclassified: {len(unclassified)})', flush=True)
    except Exception as e:
        print(f'[V2-SHADOW ERROR] {firebase_id}: {e}', flush=True)
        try:
            firebase_patch(f'reports/{firebase_id}', {
                'v2AutoError': str(e)[:500],
                'v2RunAt': int(time.time() * 1000),
            })
        except Exception:
            pass


def process_submission(form_data, pdf_b64, firebase_id):
    """Runs Claude underwriting and updates Firebase record."""
    try:
        print(f'[INFO] Processing {form_data.get("firstName","")} {form_data.get("lastName","")}...')

        # Build applicant info string for Claude
        form_name = f"{form_data.get('firstName','')} {form_data.get('lastName','')}".strip()
        applicant_info = "\n".join([
            f"Name: {form_data.get('firstName','')} {form_data.get('middleName','')} {form_data.get('lastName','')}".strip(),
            f"IMPORTANT: Use this form-submitted name as the APPLICANT_NAME in your report. Flag any mismatch with the document name.",
            f"DOB: {form_data.get('dob','')}",
            f"SSN: [REDACTED — shown only in secure SSN field, do NOT print in report]",
            f"Address: {form_data.get('address','')} {form_data.get('address2','')} {form_data.get('city','')} {form_data.get('state','')} {form_data.get('zip','')}",
            f"Phone: {form_data.get('phone','')}",
            f"Email: {form_data.get('email','')}",
            f"Loan Amount Requested: ${form_data.get('loanAmount','')}",
            f"Source of Income: {form_data.get('sourceOfIncome','')}",
            f"Employer: {form_data.get('employer','')}",
            f"Pay Frequency: {form_data.get('payFrequency','')}",
            f"Pay Day: {form_data.get('payDay','')}",
            f"Last Pay Date: {form_data.get('lastPayDate','')}",
            f"Payment Method: {form_data.get('paymentMethod','')}",
            f"Account Type: {form_data.get('accountType','')}",
            f"Bank Name: {form_data.get('bankName','')}",
            f"Housing Status: {form_data.get('housingStatus','')}",
            f"Bankruptcy: {form_data.get('bankruptcy','')}",
            f"Military: {form_data.get('military','')}",
            f"Bank Connection: {form_data.get('bankMethod','')}",
        ])

        # Call Claude
        raw = call_claude(pdf_b64, applicant_info)
        d = parse_decision(raw)
        print(f'[DECISION] Name={d["name"]} Decision={d["decision"]} Score={d["score"]} Amount={d["amount"]}', flush=True)
        if d['decision'] == 'PENDING':
            print(f'[DECISION WARNING] Could not parse decision block. Raw tail: {raw[-300:]}', flush=True)
        report = re.sub(r'DECISION_BLOCK_START[\s\S]*?DECISION_BLOCK_END\n?', '', raw).strip()

        # Update Firebase record with results
        patch_data = {
            'status': 'Pending',
            'claudeDecision': d['decision'],
            'amount': ('$'+d['amount']) if d['amount'] else 'N/A',
            'reason': d['reason'],
            'score': d['score'],
            'report': report,
            'name': form_name or d['name'] or f"{form_data.get('firstName','')} {form_data.get('lastName','')}",
            'formName': form_name,
            'documentName': d['name'],
            'nameMismatch': bool(form_name and d['name'] and form_name.lower() != d['name'].lower()),
            'processingComplete': True,
            'updatedAt': int(time.time()*1000),
        }
        # Save SSN if extracted
        if d.get('ssn'):
            patch_data['extractedSSN'] = d['ssn']
        if d.get('approvalReason'):
            patch_data['approvalReason'] = d['approvalReason']
        # Save engine metrics for dashboard display
        metrics = getattr(call_claude, '_last_metrics', {})
        if metrics:
            patch_data.update(metrics)
        # Save extracted data for reruns without re-calling Claude
        extracted = getattr(call_claude, '_last_extracted', None)
        if extracted:
            patch_data['extractedData'] = json.dumps(extracted)
        patch_data['dataSource'] = 'pdf_claude'
        patch_data['dtiRatio'] = round(metrics.get('dti_ratio', 0), 1) if metrics else 0
        patch_data['reviewTier'] = metrics.get('review_tier', 'full') if metrics else 'full'
        firebase_patch(f'reports/{firebase_id}', patch_data)
        print(f'[SUCCESS] {d["name"]} -> {d["decision"]}')

        # Run v2 in shadow mode (never blocks v1, never mutates v1 fields)
        _run_v2_shadow(firebase_id, extracted, form_data)

    except Exception as e:
        print(f'[ERROR] Processing failed: {e}')
        firebase_patch(f'reports/{firebase_id}', {
            'status': 'Error',
            'processingComplete': True,
            'error': str(e),
            'updatedAt': int(time.time()*1000),
        })

# ══════════════════════════════════════════
# PROCESS SUBMISSION V2 (Plaid JSON path — no Claude needed)
# ══════════════════════════════════════════
def process_submission_v2(form_data, extracted_data, pdf_b64, firebase_id):
    """Process with pre-extracted data (Plaid JSON path). Skips Claude extraction."""
    try:
        form_name = f"{form_data.get('firstName','')} {form_data.get('lastName','')}".strip()

        settings = get_underwriting_settings()
        from decision_engine import run_decision_engine

        # Run engine directly with pre-extracted data
        engine_result = run_decision_engine(extracted_data, settings)

        # Build applicant info string
        applicant_info = "\n".join([
            f"Name: {form_data.get('firstName','')} {form_data.get('middleName','')} {form_data.get('lastName','')}".strip(),
            f"Loan Amount Requested: ${form_data.get('loanAmount','')}",
            f"Source of Income: {form_data.get('sourceOfIncome','')}",
            f"Pay Frequency: {form_data.get('payFrequency','')}",
        ])

        # Build report HTML
        report_html = build_report_html(engine_result, applicant_info, settings)

        # Calculate score
        score = calculate_score(engine_result)

        # Build patch data
        name = extracted_data.get('account_holder_name', '') or form_name
        ok = engine_result['decision'] == 'APPROVED'

        patch_data = {
            'status': 'Pending',
            'claudeDecision': engine_result['decision'],
            'amount': f"${engine_result['amount']}" if ok else 'N/A',
            'reason': engine_result.get('decline_reason_text', ''),
            'score': score,
            'report': report_html,
            'name': form_name or name,
            'formName': form_name,
            'documentName': name,
            'nameMismatch': bool(form_name and name and form_name.lower() != name.lower()),
            'processingComplete': True,
            'updatedAt': int(time.time()*1000),
            'fcf': round(engine_result['fcf'], 2),
            'monthlyIncome': round(engine_result['monthly_income'], 2),
            'monthlyExpenses': round(engine_result['monthly_expenses'], 2),
            'fintechCount': engine_result['fintech_count'],
            'nsfCount': engine_result['nsf_count'],
            'dtiRatio': round(engine_result.get('dti_ratio', 0), 1),
            'reviewTier': engine_result.get('review_tier', 'full'),
            'dataSource': 'plaid_json',
            'extractedData': json.dumps(extracted_data),
        }
        if ok:
            patch_data['approvalReason'] = f"FCF ${engine_result['fcf']:,.2f} qualifies for Tier {engine_result['final_tier']}"

        firebase_patch(f'reports/{firebase_id}', patch_data)
        print(f'[SUCCESS] {name} -> {engine_result["decision"]} (Plaid JSON path)')

        # Run engine_v2 in shadow mode (never blocks v1, never mutates v1 fields)
        _run_v2_shadow(firebase_id, extracted_data, form_data)

    except Exception as e:
        print(f'[ERROR] V2 processing failed: {e}')
        # Fall back to Claude path
        try:
            process_submission(form_data, pdf_b64, firebase_id)
        except Exception as e2:
            firebase_patch(f'reports/{firebase_id}', {
                'status': 'Error', 'processingComplete': True,
                'error': str(e2), 'updatedAt': int(time.time()*1000)
            })

# ══════════════════════════════════════════
# HTTP HANDLER
# ══════════════════════════════════════════
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def send_json(self, code, data):
        body = json.dumps(data).encode()
        self.send_response(code)
        for k,v in CORS.items(): self.send_header(k,v)
        self.send_header('Content-Type','application/json')
        self.send_header('Content-Length',str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_html(self, code, html):
        body = html.encode()
        self.send_response(code)
        for k,v in CORS.items(): self.send_header(k,v)
        self.send_header('Content-Type','text/html; charset=utf-8')
        self.send_header('Content-Length',str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        for k,v in CORS.items(): self.send_header(k,v)
        self.end_headers()

    def do_GET(self):
        if self.path == '/health':
            self.send_json(200, {'status':'ok','time':datetime.now().isoformat(),'email_enabled':EMAIL_ENABLED,'email_sender':EMAIL_SENDER,'email_to':EMAIL_TO,'has_password':bool(EMAIL_PASSWORD)})
        elif self.path == '/test-email':
            try:
                payload = json.dumps({
                    "personalizations": [{"to": [{"email": EMAIL_TO}]}],
                    "from": {"email": EMAIL_SENDER, "name": "Cash Rocket Anaheim"},
                    "subject": "Cash Rocket Anaheim — Email Test",
                    "content": [{"type": "text/html", "value": "<p style='font-family:Arial,sans-serif;font-size:16px'>Email notifications are working! ✓</p>"}]
                }).encode('utf-8')
                ctx = ssl.create_default_context()
                conn = http.client.HTTPSConnection('api.sendgrid.com', timeout=30, context=ctx)
                conn.request('POST', '/v3/mail/send', body=payload, headers={
                    'Content-Type': 'application/json',
                    'Authorization': f'Bearer {EMAIL_PASSWORD}',
                    'Content-Length': str(len(payload))
                })
                resp = conn.getresponse()
                resp.read()
                conn.close()
                if resp.status in (200, 202):
                    print(f'[EMAIL] Test sent to {EMAIL_TO}', flush=True)
                    self.send_json(200, {'ok': True, 'message': f'Test email sent to {EMAIL_TO}'})
                else:
                    self.send_json(500, {'ok': False, 'error': f'SendGrid status {resp.status}'})
            except Exception as e:
                print(f'[EMAIL TEST ERROR] {e}', flush=True)
                self.send_json(500, {'ok': False, 'error': str(e)})
        elif self.path == '/plaid/link-token':
            try:
                token = plaid_create_link_token()
                self.send_json(200, {'link_token': token})
            except Exception as e:
                self.send_json(500, {'error': str(e)})
        elif self.path.startswith('/plaid/check'):
            from urllib.parse import urlparse, parse_qs
            qs = parse_qs(urlparse(self.path).query)
            token = qs.get('token', [''])[0]
            result = plaid_results.get(token)
            if result:
                self.send_json(200, {'connected': True, 'asset_report_token': result.get('asset_report_token',''), 'institution': result.get('institution','')})
            else:
                self.send_json(200, {'connected': False})
        elif self.path == '/admin/settings':
            try:
                settings = firebase_get('settings') or {}
                self.send_json(200, settings)
            except Exception as e:
                self.send_json(500, {'error': str(e)})
        elif self.path.split('?')[0] in ('/', '/apply'):
            try:
                with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'frontend', 'index.html'), encoding='utf-8') as f:
                    self.send_html(200, f.read())
            except FileNotFoundError:
                self.send_json(404, {'error': 'index.html not found'})
        elif self.path.split('?')[0] == '/styles.css':
            try:
                with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'frontend', 'styles.css'), encoding='utf-8') as f:
                    body = f.read().encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'text/css; charset=utf-8')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except FileNotFoundError:
                self.send_json(404, {'error': 'styles.css not found'})
        elif self.path.split('?')[0] == '/site.css':
            # Serve the marketing site's CSS from the apply origin so the
            # apply landing header/nav/menu matches cashrocketanaheim.com
            # pixel-for-pixel (same-origin avoids cross-origin caching /
            # CSP surprises).
            try:
                with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'css', 'style.css'), encoding='utf-8') as f:
                    body = f.read().encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'text/css; charset=utf-8')
                self.send_header('Content-Length', str(len(body)))
                self.send_header('Cache-Control', 'public, max-age=300')
                self.end_headers()
                self.wfile.write(body)
            except FileNotFoundError:
                self.send_json(404, {'error': 'site.css not found'})
        elif self.path.split('?')[0] == '/script.js':
            try:
                with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'frontend', 'script.js'), encoding='utf-8') as f:
                    body = f.read().encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'application/javascript; charset=utf-8')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except FileNotFoundError:
                self.send_json(404, {'error': 'script.js not found'})
        elif self.path == '/api/v2-unclassified':
            # Aggregate unclassified transactions from all reports that have
            # been run through v2. Groups by normalized description prefix.
            try:
                reports = firebase_get('reports') or {}
                skiplist = _load_skiplist()
                # Live classifier — re-classify every stored-unclassified txn
                # with today's rules so merchants the engine has since learned
                # to handle (new keywords, registry additions, self-P2P flip)
                # drop out of the queue automatically.
                from engine_v2.categorization.rules import (
                    classify_credit, classify_debit,
                )
                merchants = {}
                for rid, rec in reports.items():
                    if not isinstance(rec, dict):
                        continue
                    unclassified_json = rec.get('v2UnclassifiedJson')
                    if not unclassified_json:
                        continue
                    try:
                        items = json.loads(unclassified_json) if isinstance(unclassified_json, str) else unclassified_json
                    except Exception:
                        continue
                    app_data = rec.get('applicationData') or {}
                    if isinstance(app_data, str):
                        try:
                            app_data = json.loads(app_data)
                        except Exception:
                            app_data = {}
                    first_name = (app_data.get('firstName') or '').strip().upper()
                    last_name = (app_data.get('lastName') or '').strip().upper()
                    self_match_ok = len(first_name) >= 2 and len(last_name) >= 2
                    for t in items:
                        desc = (t.get('description') or '').strip()
                        if not desc:
                            continue

                        # Run through today's classifier. If it now resolves
                        # to something other than 'unclassified', the engine
                        # has caught up — skip.
                        is_credit = bool(t.get('is_credit'))
                        amt = float(t.get('amount') or 0)
                        if is_credit:
                            live_cat, _ = classify_credit(desc, amt, t)
                        else:
                            live_cat, _ = classify_debit(desc, amt, t)
                        # Mirror the orchestrator's self-P2P flip so a
                        # self-Zelle (classifier returns p2p_sent/p2p_received)
                        # is recognized as handled.
                        if live_cat in ('p2p_sent', 'p2p_received') and self_match_ok:
                            desc_upper = desc.upper()
                            if first_name in desc_upper and last_name in desc_upper:
                                live_cat = 'internal_transfer'
                        if live_cat != 'unclassified':
                            continue

                        # Normalize: uppercase, strip trailing numeric confirmation codes
                        import re as _re
                        key = desc.upper()
                        key = _re.sub(r'\s+#?\s*[A-Z0-9]{6,}\s*$', '', key)  # strip confirmation IDs
                        key = _re.sub(r'\s+\d{1,2}/\d{1,2}\s*$', '', key)     # strip trailing dates
                        key = key[:60].strip()
                        if key in skiplist:
                            continue
                        m = merchants.setdefault(key, {
                            'pattern': key,
                            'count': 0,
                            'reports': set(),
                            'samples': [],
                            'credit_count': 0,
                            'debit_count': 0,
                            'plaid_pfcs': {},
                        })
                        m['count'] += 1
                        m['reports'].add(rid)
                        if t.get('is_credit'):
                            m['credit_count'] += 1
                        else:
                            m['debit_count'] += 1
                        pfc = t.get('plaid_pfc')
                        if pfc:
                            m['plaid_pfcs'][pfc] = m['plaid_pfcs'].get(pfc, 0) + 1
                        if len(m['samples']) < 5:
                            m['samples'].append({
                                'description': desc,
                                'is_credit': bool(t.get('is_credit')),
                                'amount': float(t.get('amount') or 0),
                                'date': t.get('date') or '',
                                'plaid_pfc': pfc,
                            })

                # Filter out merchants that are NOW handled by the (just-updated)
                # registry. Stored v2UnclassifiedJson reflects a past v2 run;
                # without this filter, a freshly confirmed merchant would stay
                # in the queue until every historical report is re-run.
                from engine_v2.categorization.registry import (
                    category_for, size as registry_size,
                )
                merchants_list = []
                for m in merchants.values():
                    credit_handled = (
                        m['credit_count'] == 0
                        or category_for(m['pattern'], is_credit=True) is not None
                    )
                    debit_handled = (
                        m['debit_count'] == 0
                        or category_for(m['pattern'], is_credit=False) is not None
                    )
                    if credit_handled and debit_handled:
                        continue  # registry now covers every direction this merchant uses
                    sugg = _suggest_categories(m)
                    merchants_list.append({
                        'pattern': m['pattern'],
                        'count': m['count'],
                        'reports': len(m['reports']),
                        'samples': m['samples'],
                        'credit_count': m['credit_count'],
                        'debit_count': m['debit_count'],
                        'suggested_credit': sugg[0],
                        'suggested_debit': sugg[1],
                        'suggestion_source': sugg[2],
                    })
                merchants_list.sort(key=lambda x: -x['count'])
                self.send_json(200, {
                    'merchants': merchants_list,
                    'registry_size': registry_size(),
                    'skiplist_size': len(skiplist),
                })
            except Exception as e:
                import traceback; traceback.print_exc()
                self.send_json(500, {'error': str(e)})
        elif self.path.split('?')[0] in (
            '/favicon.png', '/favicon.ico', '/apple-touch-icon.png',
            '/logo.png', '/logo-white.png',
        ):
            # Static brand assets. Public (no auth). Served from /static.
            # /logo.png and /logo-white.png are used by the denial email so
            # email clients aren't blocked by cashinflash.com's hotlink
            # protection.
            name_map = {
                '/logo.png': 'logo.png',
                '/logo-white.png': 'logo-white.png',
            }
            requested = self.path.split('?')[0]
            fname = name_map.get(requested, 'favicon.png')
            try:
                with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', fname), 'rb') as f:
                    body = f.read()
                self.send_response(200)
                self.send_header('Content-Type', 'image/png')
                self.send_header('Cache-Control', 'public, max-age=86400')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except FileNotFoundError:
                # Send a 1x1 transparent png as graceful fallback
                self.send_response(204); self.end_headers()
        else:
            self.send_json(404, {'error': 'not found'})

    def do_POST(self):
        length = int(self.headers.get('Content-Length', 0))
        raw = self.rfile.read(length) if length else b'{}'

        # ── Plaid: exchange public token ──
        if self.path == '/plaid/exchange':
            try:
                body = json.loads(raw)
                access_token = plaid_exchange_token(body['public_token'])
                report_token, report_id = plaid_create_asset_report(access_token)
                result = {
                    'access_token': access_token,
                    'asset_report_token': report_token,
                    'asset_report_id': report_id,
                    'institution': body.get('institution', '')
                }
                # Store result for mobile polling flow
                link_token = body.get('link_token', '')
                if link_token:
                    plaid_results[link_token] = result
                # Return access_token so it can be saved with the submission
                self.send_json(200, result)
            except Exception as e:
                self.send_json(500, {'error': str(e)})
            return

        # ── Submit application ──
        if self.path == '/submit':
            try:
                body = json.loads(raw)
                form_data = body.get('formData', {})
                pdf_b64 = body.get('pdfBase64', '') or body.get('pdfB64', '')
                asset_report_token = body.get('assetReportToken', '')

                # Fail-closed guards — run BEFORE touching Firebase so
                # malformed / external posts (legacy JotForm webhook, bots)
                # don't land phantom records in the dashboard.
                if not asset_report_token and not pdf_b64:
                    self.send_json(400, {'error': 'No bank data provided'}); return
                _src = form_data.get('source', '')
                if _src not in ('', 'web-apply', 'desktop', 'plaid-rerun'):
                    print(f'[SUBMIT] Rejected unknown source={_src!r}', flush=True)
                    self.send_json(403, {'error': 'Invalid source'}); return
                # Cash Rocket Anaheim single-tenant: force source_site to the
                # known slug regardless of client payload. Clients MAY send it;
                # we validate the shape for defence-in-depth, but this deployment
                # always ends up tagging as 'cashrocket_anaheim'.
                _site_raw = form_data.get('source_site', '') or ''
                if _site_raw and not re.fullmatch(r'[a-z0-9_]{3,40}', _site_raw):
                    print(f'[SUBMIT] Rejected bad source_site={_site_raw!r}', flush=True)
                    self.send_json(400, {'error': 'Invalid source_site'}); return
                _site = 'cashrocket_anaheim'

                now = now_pacific()
                name = f"{form_data.get('firstName','')} {form_data.get('lastName','')}".strip()

                # Save initial record to Firebase immediately
                record = {
                    'id': int(time.time()*1000),
                    'date': now.strftime('%b %d, %Y'),
                    'time': now.strftime('%I:%M %p'),
                    'createdAt': int(time.time()*1000),
                    'source': form_data.get('source', 'web-apply'),
                    'source_site': _site,
                    'status': 'Processing',
                    'name': name or 'Unknown',
                    'amount': f"${form_data.get('loanAmount','')}" if form_data.get('loanAmount') else 'N/A',
                    'claudeDecision': '',
                    'reason': '',
                    'score': 0,
                    'filename': 'Plaid Asset Report' if asset_report_token else 'Bank Statement Upload',
                    'report': '',
                    'notes': '',
                    'profile': 'Standard',
                    'processingComplete': False,
                    'plaidAssetToken': asset_report_token or '',
                    'plaidAccessToken': body.get('plaidAccessToken', ''),
                    'ssn4': form_data.get('ssn4', ''),
                    # Full application data for the Application Details tab
                    'applicationData': {
                        'firstName': form_data.get('firstName',''),
                        'middleName': form_data.get('middleName',''),
                        'lastName': form_data.get('lastName',''),
                        'loanAmount': form_data.get('loanAmount',''),
                        'ssn': form_data.get('ssn',''),
                        'dob': form_data.get('dob',''),
                        'address': form_data.get('address',''),
                        'address2': form_data.get('address2',''),
                        'city': form_data.get('city',''),
                        'state': form_data.get('state',''),
                        'zip': form_data.get('zip',''),
                        'phone': form_data.get('phone',''),
                        'email': form_data.get('email',''),
                        'sourceOfIncome': form_data.get('sourceOfIncome',''),
                        'employer': form_data.get('employer',''),
                        'payFrequency': form_data.get('payFrequency',''),
                        'payDay': form_data.get('payDay',''),
                        'lastPayDate': form_data.get('lastPayDate',''),
                        'paymentMethod': form_data.get('paymentMethod',''),
                        'grossPay': form_data.get('grossPay',''),
                        'accountType': form_data.get('accountType',''),
                        'routingNumber': form_data.get('routingNumber',''),
                        'accountNumber': form_data.get('accountNumber',''),
                        'bankName': form_data.get('bankName',''),
                        'housingStatus': form_data.get('housingStatus',''),
                        'bankruptcy': form_data.get('bankruptcy',''),
                        'military': form_data.get('military',''),
                        'consent': form_data.get('consent',''),
                        'bankMethod': 'Plaid (Connected)' if asset_report_token else 'PDF Upload',
                        'submittedAt': now.isoformat(),
                        'language': form_data.get('language','en'),
                    }
                }

                firebase_id = firebase_save('reports', record)

                # Send email notification in background
                threading.Thread(target=send_notification, args=(form_data, firebase_id), daemon=False).start()

                # Upload documents to Firebase Storage
                gov_id_b64 = body.get('govIdB64', '')
                paystub_b64 = body.get('paystubB64', '') or body.get('paystub_b64', '')

                def upload_docs_async():
                    try:
                        doc_urls = {}
                        if gov_id_b64:
                            img_bytes = base64.b64decode(gov_id_b64)
                            url = firebase_storage_upload(f'documents/{firebase_id}/government_id.jpg', img_bytes, 'image/jpeg')
                            doc_urls['govIdUrl'] = url
                            print(f'[STORAGE] Gov ID uploaded')
                        if paystub_b64:
                            ps_bytes = base64.b64decode(paystub_b64)
                            url = firebase_storage_upload(f'documents/{firebase_id}/paystub.pdf', ps_bytes, 'application/pdf')
                            doc_urls['paystubUrl'] = url
                            print(f'[STORAGE] Paystub uploaded')
                        if pdf_b64:
                            pdf_bytes = base64.b64decode(pdf_b64)
                            url = firebase_storage_upload(f'documents/{firebase_id}/bank_statement.pdf', pdf_bytes, 'application/pdf')
                            doc_urls['bankStatementUrl'] = url
                            print(f'[STORAGE] Bank statement uploaded')
                        if doc_urls:
                            firebase_patch(f'reports/{firebase_id}', doc_urls)
                            print(f'[STORAGE] Saved URLs to Firebase: {list(doc_urls.keys())}', flush=True)
                        else:
                            print(f'[STORAGE] No doc URLs to save — check b64 inputs', flush=True)
                    except Exception as e:
                        print(f'[STORAGE ERROR] {e}', flush=True)
                        import traceback; traceback.print_exc()
                        # Still patch firebase with error flag so we know docs failed
                        try:
                            firebase_patch(f'reports/{firebase_id}', {'docsError': str(e)})
                        except: pass
                threading.Thread(target=upload_docs_async, daemon=True).start()

                # If Plaid, fetch asset report PDF in background
                if asset_report_token and not pdf_b64:
                    def fetch_and_process():
                        try:
                            print('[INFO] Fetching Plaid asset report PDF...')
                            pdf_bytes = plaid_get_asset_report_pdf(asset_report_token)
                            b64 = base64.b64encode(pdf_bytes).decode()
                            # Save asset report PDF to Firebase too
                            try:
                                url = firebase_storage_upload(f'documents/{firebase_id}/plaid_asset_report.pdf', pdf_bytes, 'application/pdf')
                                firebase_patch(f'reports/{firebase_id}', {'bankStatementUrl': url, 'bankStatementType': 'plaid'})
                                print(f'[STORAGE] Plaid asset report uploaded')
                            except Exception as se:
                                print(f'[STORAGE] Asset report upload error: {se}')

                            # Try Plaid JSON path first (faster, more accurate, no Claude needed)
                            plaid_extracted = None
                            try:
                                plaid_json = plaid_get_asset_report_json(asset_report_token)
                                from decision_engine import convert_plaid_to_extracted
                                plaid_extracted = convert_plaid_to_extracted(plaid_json)
                                if plaid_extracted:
                                    print(f'[ENGINE] Plaid JSON path: {len(plaid_extracted["transactions"])} transactions extracted')
                            except Exception as pe:
                                import traceback
                                print(f'[ERROR] Plaid JSON extraction failed: {pe}')
                                traceback.print_exc()
                                print(f'[INFO] Falling back to Claude PDF extraction...')

                            if plaid_extracted:
                                # Plaid path — skip Claude extraction, go straight to engine
                                process_submission_v2(form_data, plaid_extracted, b64, firebase_id)
                            else:
                                # PDF path — use Claude extraction (existing flow)
                                process_submission(form_data, b64, firebase_id)
                        except Exception as e:
                            print(f'[ERROR] Plaid PDF fetch: {e}')
                            firebase_patch(f'reports/{firebase_id}', {
                                'status': 'Error', 'error': str(e),
                                'processingComplete': True,
                                'updatedAt': int(time.time()*1000)
                            })
                    threading.Thread(target=fetch_and_process, daemon=True).start()
                elif pdf_b64:
                    # PDF upload — process in background
                    threading.Thread(target=process_submission,
                        args=(form_data, pdf_b64, firebase_id), daemon=True).start()
                else:
                    self.send_json(400, {'error': 'No bank data provided'}); return

                self.send_json(200, {
                    'success': True,
                    # Browser expects `firebaseId` (camelCase) per the
                    # new two-step submit in form.html; alias both for
                    # backward compat.
                    'firebaseId': firebase_id,
                    'firebase_id': firebase_id,
                    'message': 'Application received! We are processing your information.'
                })

            except Exception as e:
                print(f'[ERROR] Submit: {e}')
                self.send_json(500, {'error': str(e)})
            return

        # ── POST /link-if/<firebase_id> ──────────────────────────
        # Called by the apply form AFTER the card has been submitted
        # directly to the IF vault (cif-portal Lambda). Body is just
        # { ifSubmissionId: "<uuid>" }. No card data ever flows
        # through this endpoint — just the UUID so the dashboard can
        # correlate applications to card submissions.
        if self.path.startswith('/link-if/'):
            try:
                firebase_id = self.path[len('/link-if/'):].strip()
                if not firebase_id or len(firebase_id) > 128:
                    self.send_json(400, {'error': 'bad firebase_id'}); return
                raw_len = int(self.headers.get('Content-Length') or 0)
                body = json.loads(self.rfile.read(raw_len).decode('utf-8')) if raw_len else {}
                if_sub_id = (body.get('ifSubmissionId') or '').strip()
                # UUIDv4 = 36 chars with dashes; keep a small limit.
                if not if_sub_id or len(if_sub_id) > 64:
                    self.send_json(400, {'error': 'bad ifSubmissionId'}); return
                # PATCH the application's applicationData subtree so
                # the dashboard can correlate app ↔ card submission.
                firebase_patch(f'reports/{firebase_id}/applicationData',
                               {'ifSubmissionId': if_sub_id})
                print(f'[LINK-IF] fbId={firebase_id} ifSub={if_sub_id}')
                self.send_json(200, {'success': True})
            except Exception as e:
                print(f'[ERROR] /link-if: {e}')
                self.send_json(500, {'error': str(e)})
            return

        # ── Rerun Plaid asset report ──
        if self.path == '/rerun-plaid':
            try:
                body = json.loads(raw)
                access_token = body.get('accessToken','') or body.get('assetToken','')
                firebase_id = body.get('firebaseId','')
                form_data = body.get('formData', {})
                if not access_token or not firebase_id:
                    self.send_json(400, {'error':'Missing accessToken or firebaseId'}); return
                def do_rerun():
                    try:
                        print(f'[RERUN] Creating fresh Plaid asset report for {firebase_id}...')
                        # Create a brand new asset report from the live access token
                        new_report_token, new_report_id = plaid_create_asset_report(access_token)
                        print(f'[RERUN] Waiting for new asset report...')
                        pdf_bytes = plaid_get_asset_report_pdf(new_report_token)
                        b64 = base64.b64encode(pdf_bytes).decode()
                        # Upload to Firebase Storage
                        try:
                            url = firebase_storage_upload(f'documents/{firebase_id}/plaid_rerun_{int(time.time())}.pdf', pdf_bytes, 'application/pdf')
                            firebase_patch(f'reports/{firebase_id}', {'bankStatementUrl': url, 'plaidAssetToken': new_report_token})
                            print(f'[RERUN] Asset report uploaded to storage')
                        except Exception as se:
                            print(f'[RERUN] Storage upload error: {se}')
                        # Try Plaid JSON path for rerun too
                        try:
                            plaid_json = plaid_get_asset_report_json(new_report_token)
                            from decision_engine import convert_plaid_to_extracted
                            plaid_extracted = convert_plaid_to_extracted(plaid_json)
                            if plaid_extracted:
                                process_submission_v2(form_data, plaid_extracted, b64, firebase_id)
                                print(f'[RERUN] Complete for {firebase_id} (Plaid JSON path)')
                                return
                        except:
                            pass
                        # Fallback to Claude
                        process_submission(form_data, b64, firebase_id)
                        print(f'[RERUN] Complete for {firebase_id}')
                    except Exception as e:
                        print(f'[RERUN ERROR] {e}')
                        firebase_patch(f'reports/{firebase_id}', {
                            'status': 'Error', 'error': str(e),
                            'processingComplete': True,
                            'updatedAt': int(time.time()*1000)
                        })
                threading.Thread(target=do_rerun, daemon=True).start()
                self.send_json(200, {'ok': True})
            except Exception as e:
                self.send_json(500, {'error': str(e)})
            return

        # ── Send denial email ──
        if self.path == '/api/send-denial':
            try:
                body = json.loads(raw)
                to_email = body.get('email', '')
                customer_name = body.get('name', 'Valued Customer')
                first_name = customer_name.split()[0] if customer_name else 'Valued Customer'
                reasons = body.get('reasons', [])
                date_now = now_pacific().strftime('%B %d, %Y')
                if not to_email:
                    self.send_json(400, {'error': 'No email address'}); return
                # Build reason rows HTML
                reason_rows = ''
                for r in reasons:
                    reason_rows += (
                        '<table width="100%" border="0" cellpadding="0" cellspacing="0" style="margin-bottom:12px;">'
                        '<tbody><tr>'
                        '<td style="vertical-align:middle;padding-right:12px;width:30px;">'
                        '<div style="width:18px;height:18px;background:#1aab6d;border-radius:3px;text-align:center;line-height:18px;">'
                        '<span style="color:white;font-size:12px;font-weight:700;">&#10003;</span>'
                        '</div></td>'
                        '<td style="vertical-align:middle;">'
                        '<span style="font-family:Arial,sans-serif;font-size:14px;color:#2d4a38;">' + r + '</span>'
                        '</td></tr></tbody></table>'
                    )
                # Load template
                tmpl_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'denial_email.html')
                denial_html = open(tmpl_path, encoding='utf-8').read()
                denial_html = denial_html.replace('(!CUSTOMER_FNAME!)', first_name)
                denial_html = denial_html.replace('(!DATE_NOW!)', date_now)
                denial_html = denial_html.replace('(!REASON_ROWS!)', reason_rows)
                payload = json.dumps({
                    "personalizations": [{"to": [{"email": to_email, "name": customer_name}]}],
                    "from": {"email": "info@cashinflash.com", "name": "Cash Rocket Anaheim"},
                    "reply_to": {"email": "info@cashinflash.com"},
                    "subject": "Important Information About Your Application - Cash in Flash",
                    "content": [{"type": "text/html", "value": denial_html}]
                }).encode('utf-8')
                ctx = ssl.create_default_context()
                conn = http.client.HTTPSConnection('api.sendgrid.com', timeout=30, context=ctx)
                conn.request('POST', '/v3/mail/send', body=payload, headers={
                    'Content-Type': 'application/json',
                    'Authorization': 'Bearer ' + EMAIL_PASSWORD,
                    'Content-Length': str(len(payload))
                })
                resp = conn.getresponse()
                resp.read()
                conn.close()
                if resp.status in (200, 202):
                    print('[DENIAL EMAIL] Sent to ' + to_email, flush=True)
                    self.send_json(200, {'ok': True})
                else:
                    self.send_json(500, {'ok': False, 'error': 'SendGrid status ' + str(resp.status)})
            except Exception as e:
                print('[DENIAL EMAIL ERROR] ' + str(e), flush=True)
                self.send_json(500, {'error': str(e)})
            return

        # ── Admin: save settings ──
        if self.path == '/admin/settings':
            try:
                settings = json.loads(raw)
                firebase_patch('settings', settings)
                self.send_json(200, {'ok': True})
            except Exception as e:
                self.send_json(500, {'error': str(e)})
            return

        # ── Rerun engine with stored extracted data ──
        if self.path == '/api/rerun-engine':
            try:
                body = json.loads(raw)
                firebase_id = body.get('firebase_id', '')
                overrides = body.get('overrides', {})

                if not firebase_id:
                    self.send_json(400, {'error': 'Missing firebase_id'})
                    return

                # Fetch stored extracted data from Firebase
                record = firebase_get(f'reports/{firebase_id}')
                extracted_json = record.get('extractedData', '')
                if not extracted_json:
                    self.send_json(400, {'error': 'No extracted data stored for this application'})
                    return

                extracted = json.loads(extracted_json)
                settings = get_underwriting_settings()

                from decision_engine import run_decision_engine
                engine_result = run_decision_engine(extracted, settings, overrides=overrides)
                report_html = build_report_html(engine_result, '', settings)
                score = calculate_score(engine_result)

                ok = engine_result['decision'] == 'APPROVED'

                # Update Firebase with new decision
                patch_data = {
                    'claudeDecision': engine_result['decision'],
                    'amount': f"${engine_result['amount']}" if ok else 'N/A',
                    'reason': engine_result.get('decline_reason_text', ''),
                    'score': score,
                    'report': report_html,
                    'fcf': round(engine_result['fcf'], 2),
                    'monthlyIncome': round(engine_result['monthly_income'], 2),
                    'monthlyExpenses': round(engine_result['monthly_expenses'], 2),
                    'updatedAt': int(time.time()*1000),
                    'overridesApplied': len(overrides.get('transaction_overrides', [])),
                }
                if ok:
                    patch_data['approvalReason'] = f"FCF ${engine_result['fcf']:,.2f} (with overrides)"
                firebase_patch(f'reports/{firebase_id}', patch_data)

                self.send_json(200, {
                    'decision': engine_result['decision'],
                    'amount': engine_result['amount'],
                    'score': score,
                    'report_html': report_html,
                    'fcf': round(engine_result['fcf'], 2),
                    'flagged_transactions': engine_result.get('flagged_transactions', []),
                })
            except Exception as e:
                self.send_json(500, {'error': str(e)})
            return

        # ── Rerun with engine_v2 (shadow) — does not mutate stored v1 decision ──
        if self.path == '/api/refresh-from-plaid':
            # Re-fetch the Plaid asset report for an existing record, re-run
            # the (now multi-account) extractor, overwrite extractedData, and
            # re-run v2. Needed for historical records whose extractedData
            # was written by the old single-account extractor — rerunning v2
            # alone wouldn't help because the data stored in Firebase was
            # already partial (only one account's transactions made it).
            try:
                body = json.loads(raw)
                firebase_id = body.get('firebase_id', '')
                if not firebase_id:
                    self.send_json(400, {'error': 'Missing firebase_id'}); return
                record = firebase_get(f'reports/{firebase_id}')
                if not record:
                    self.send_json(404, {'error': 'Report not found'}); return
                asset_token = record.get('plaidAssetToken') or ''
                if not asset_token:
                    self.send_json(400, {'error': 'No Plaid asset token stored on this record'}); return

                # Pull fresh data from Plaid with the stored asset token.
                plaid_json = plaid_get_asset_report_json(asset_token)

                # Run it through the NEW multi-account extractor.
                from decision_engine import convert_plaid_to_extracted
                new_extracted = convert_plaid_to_extracted(plaid_json)
                if not new_extracted:
                    self.send_json(500, {'error': 'Plaid returned no usable accounts'}); return

                # Write the refreshed extractedData back to Firebase, along
                # with a small summary of how many accounts we got this time
                # so admins can spot multi-account applicants at a glance.
                firebase_patch(f'reports/{firebase_id}', {
                    'extractedData': json.dumps(new_extracted),
                    'plaidRefreshedAt': int(time.time() * 1000),
                    'connectedAccountCount': new_extracted.get('connected_account_count', 1),
                })

                # Immediately re-run v2 on the refreshed data.
                application = record.get('applicationData', {}) or {}
                from engine_v2 import run_v2
                from engine_v2.report_html import render as render_v2_html
                v2_result = run_v2(new_extracted, application)
                v2_html = render_v2_html(v2_result, application)
                unclassified = _extract_v2_unclassified(v2_result)
                firebase_patch(f'reports/{firebase_id}', {
                    'v2Decision': v2_result.decision.outcome.upper(),
                    'v2TierAmount': v2_result.decision.tier_amount,
                    'v2MaxAffordable': v2_result.affordability.max_affordable_loan_amount,
                    'v2FcfMonthly': round(v2_result.affordability.fcf_monthly, 2),
                    'v2Confidence': v2_result.affordability.confidence,
                    'v2Report': v2_html,
                    'v2ReasonsJson': json.dumps(v2_result.decision.reasons),
                    'v2ReviewFlagsJson': json.dumps(v2_result.decision.review_flags),
                    'v2ReconciliationOk': v2_result.reconciliation.ok,
                    'v2ReconciliationError': v2_result.reconciliation.error,
                    'v2UnclassifiedJson': json.dumps(unclassified),
                    'v2UnclassifiedCount': len(unclassified),
                    'v2AutoDecide': bool(v2_result.summary.get('auto_decide_candidate')),
                    'v2RunAt': int(time.time() * 1000),
                })

                # Summary payload for the dashboard (what changed?)
                self.send_json(200, {
                    'ok': True,
                    'connected_account_count': new_extracted.get('connected_account_count', 1),
                    'connected_accounts': new_extracted.get('connected_accounts', []),
                    'transaction_count': len(new_extracted.get('transactions', [])),
                    'v2_decision': v2_result.decision.outcome,
                    'v2_tier_amount': v2_result.decision.tier_amount,
                    'v2_max_affordable': v2_result.affordability.max_affordable_loan_amount,
                    'v2_verified_income_monthly': v2_result.affordability.verified_income_monthly,
                    'v2_confidence': v2_result.affordability.confidence,
                    'v2_reasons': v2_result.decision.reasons,
                })
            except Exception as e:
                import traceback; traceback.print_exc()
                self.send_json(500, {'error': str(e)})
            return

        if self.path == '/api/rerun-v2':
            try:
                body = json.loads(raw)
                firebase_id = body.get('firebase_id', '')
                if not firebase_id:
                    self.send_json(400, {'error': 'Missing firebase_id'})
                    return

                record = firebase_get(f'reports/{firebase_id}')
                if not record:
                    self.send_json(404, {'error': 'Report not found'})
                    return

                extracted_json = record.get('extractedData', '')
                if not extracted_json:
                    self.send_json(400, {'error': 'No extracted data stored for this application'})
                    return

                extracted = json.loads(extracted_json) if isinstance(extracted_json, str) else extracted_json
                application = record.get('applicationData', {}) or {}

                from engine_v2 import run_v2
                from engine_v2.report_html import render as render_v2_html
                v2_result = run_v2(extracted, application)
                v2_html = render_v2_html(v2_result, application)
                unclassified = _extract_v2_unclassified(v2_result)

                # Shadow-mode: store v2 result alongside v1 for diffing, but
                # do NOT overwrite v1's decision/amount fields.
                firebase_patch(f'reports/{firebase_id}', {
                    'v2Decision': v2_result.decision.outcome.upper(),
                    'v2TierAmount': v2_result.decision.tier_amount,
                    'v2MaxAffordable': v2_result.affordability.max_affordable_loan_amount,
                    'v2FcfMonthly': round(v2_result.affordability.fcf_monthly, 2),
                    'v2Confidence': v2_result.affordability.confidence,
                    'v2Report': v2_html,
                    'v2ReasonsJson': json.dumps(v2_result.decision.reasons),
                    'v2ReviewFlagsJson': json.dumps(v2_result.decision.review_flags),
                    'v2ReconciliationOk': v2_result.reconciliation.ok,
                    'v2ReconciliationError': v2_result.reconciliation.error,
                    'v2UnclassifiedJson': json.dumps(unclassified),
                    'v2UnclassifiedCount': len(unclassified),
                    'v2AutoDecide': bool(v2_result.summary.get('auto_decide_candidate')),
                    'v2RunAt': int(time.time() * 1000),
                })

                self.send_json(200, {
                    'engine_version': v2_result.engine_version,
                    'decision': v2_result.decision.outcome,
                    'tier_amount': v2_result.decision.tier_amount,
                    'max_affordable_loan': v2_result.affordability.max_affordable_loan_amount,
                    'fcf_monthly': v2_result.affordability.fcf_monthly,
                    'fcf_per_period': v2_result.affordability.fcf_per_period,
                    'confidence': v2_result.affordability.confidence,
                    'reasons': v2_result.decision.reasons,
                    'review_flags': v2_result.decision.review_flags,
                    'applied_adjustments': v2_result.decision.applied_adjustments,
                    'reconciliation_ok': v2_result.reconciliation.ok,
                    'reconciliation_error': v2_result.reconciliation.error,
                    'auto_decide_candidate': bool(v2_result.summary.get('auto_decide_candidate')),
                    'report_html': v2_html,
                    'summary': v2_result.summary,
                })
            except Exception as e:
                import traceback
                traceback.print_exc()
                self.send_json(500, {'error': str(e)})
            return

        # ── Persist a new mapping into entities_overrides.json (Review Queue add) ──
        if self.path == '/api/v2-entities-add':
            try:
                body = json.loads(raw)
                pattern = (body.get('pattern') or '').strip()
                credit = body.get('credit') or None
                debit = body.get('debit') or None
                if not pattern:
                    self.send_json(400, {'error': 'pattern is required'}); return
                if not credit and not debit:
                    self.send_json(400, {'error': 'at least one of credit or debit must be set'}); return
                from engine_v2.categorization.registry import add_override, size as registry_size
                add_override(pattern, credit, debit, added_by='dashboard')
                self.send_json(200, {
                    'ok': True,
                    'pattern': pattern,
                    'credit': credit,
                    'debit': debit,
                    'registry_size': registry_size(),
                })
            except Exception as e:
                import traceback; traceback.print_exc()
                self.send_json(500, {'error': str(e)})
            return

        # ── Dismiss a merchant pattern from the Review Queue (noise / non-merchant) ──
        if self.path == '/api/v2-unclassified-skip':
            try:
                body = json.loads(raw)
                pattern = (body.get('pattern') or '').strip().upper()
                if not pattern:
                    self.send_json(400, {'error': 'pattern is required'}); return
                skiplist = _load_skiplist()
                skiplist.add(pattern)
                _save_skiplist(skiplist)
                self.send_json(200, {'ok': True, 'pattern': pattern, 'skiplist_size': len(skiplist)})
            except Exception as e:
                import traceback; traceback.print_exc()
                self.send_json(500, {'error': str(e)})
            return

        # ── Analyze engine: deterministic underwriting for dashboard ──
        if self.path == '/api/analyze-engine':
            try:
                body = json.loads(raw)
                pdf_b64 = body.get('pdf_b64', '')
                custom_settings = body.get('settings', None)
                if not pdf_b64:
                    self.send_json(400, {'error': 'pdf_b64 is required'}); return

                # Use custom settings from dashboard if provided, otherwise fetch from Firebase
                if custom_settings:
                    settings = {**UNDERWRITING_DEFAULTS, **custom_settings}
                else:
                    settings = get_underwriting_settings()

                # Step 1: Extract transactions
                print('[ANALYZE-ENGINE] Step 1 — Extracting transactions...', flush=True)
                extracted = call_claude_extract(pdf_b64)
                print(f'[ANALYZE-ENGINE] Extracted {len(extracted.get("transactions",[]))} transactions', flush=True)

                # Step 2: Decision engine
                print('[ANALYZE-ENGINE] Step 2 — Running decision engine...', flush=True)
                from decision_engine import run_decision_engine
                engine_result = run_decision_engine(extracted, settings)
                print(f'[ANALYZE-ENGINE] Decision={engine_result["decision"]} FCF=${engine_result["fcf"]} '
                      f'Tier={engine_result["final_tier"]} Amount=${engine_result["amount"]}', flush=True)

                # Step 3: Build report (deterministic — no Claude needed)
                print('[ANALYZE-ENGINE] Step 3 — Building report...', flush=True)
                report_html = build_report_html(engine_result, '', settings)

                score = calculate_score(engine_result)
                self.send_json(200, {
                    'decision': engine_result['decision'],
                    'amount': engine_result['amount'],
                    'score': score,
                    'name': extracted.get('account_holder_name', 'Unknown'),
                    'reason': engine_result.get('decline_reason_text', ''),
                    'approvalReason': (f"FCF ${engine_result['fcf']:,.2f} qualifies for Tier {engine_result['final_tier']} (${engine_result['amount']})"
                                      if engine_result['decision'] == 'APPROVED' else ''),
                    'report_html': report_html,
                    'fcf': round(engine_result['fcf'], 2),
                    'monthly_income': round(engine_result['monthly_income'], 2),
                    'monthly_expenses': round(engine_result['monthly_expenses'], 2),
                    'fintech_count': engine_result['fintech_count'],
                    'nsf_count': engine_result['nsf_count'],
                    'negative_days': engine_result['negative_days'],
                    'base_tier': engine_result['base_tier'],
                    'final_tier': engine_result['final_tier'],
                    'extracted_info': {
                        'account_holder_name': extracted.get('account_holder_name', ''),
                        'bank_name': extracted.get('bank_name', ''),
                        'statement_start': extracted.get('statement_start', ''),
                        'statement_end': extracted.get('statement_end', ''),
                        'beginning_balance': extracted.get('beginning_balance', ''),
                        'ending_balance': extracted.get('ending_balance', ''),
                        'avg_daily_balance': extracted.get('avg_daily_balance', ''),
                    },
                })
            except Exception as e:
                import traceback
                traceback.print_exc()
                self.send_json(500, {'error': str(e)})
            return

        self.send_json(404, {'error': 'not found'})

if __name__ == '__main__':
    print(f'Cash Rocket Anaheim Apply Server starting on port {PORT}...')
    print(f'Plaid environment: {PLAID_ENV}')
    server = HTTPServer(('0.0.0.0', PORT), Handler)
    server.serve_forever()
