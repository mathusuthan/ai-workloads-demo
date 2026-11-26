"""Category 4 scaled deal-room corpus: deterministic distractor suppliers (no model calls).

`build_scaled_corpus(1)` is the app's 7-document Deccan deal room exactly as `hydrate_deal_room_index()` returns
it. `build_scaled_corpus(3)` adds the same deal room for two other suppliers (Kaveri, Narmada) — documents
DOC-08…DOC-14 and DOC-15…DOC-21, 56 more chunks — produced from the base documents by one deterministic
single-pass text transform per supplier:

* an ENTITY map (supplier names, counterparties, banks, auditors, plants/cities, cloud provider, contract and
  certificate identifiers), applied to every occurrence, so "Deccan" never appears in a distractor;
* NUMERIC rules for commercial terms (INR amounts and their words, percentages, ratios, durations, counts, dates)
  with a per-supplier factor / integer map / day shift, while a PROTECT list keeps statutory constants (45-day
  MSMED ceiling, 6-hour CERT-In window, 18% GST, 30% SoC, 100 Wh threshold, Rule 37A 180-day / Sept 30 cutoffs,
  INR 250/200 Cr DPDP maxima, fiscal-year dates, …) unchanged. Clause/section numbering, Act names and years,
  and unit words are never touched;
* a few phrase OVERRIDES where a mechanical rule would break the sense (e.g. the intra-state GST sentence).

Every transformed token is recorded (`mapping[supplier]`: original → distractor, with kind and location).
Document order at scale 3 is INTERLEAVED BY TYPE (fixed): DOC-01, DOC-08, DOC-15, DOC-02, DOC-09, DOC-16, …

The SKUs (NM-LFP-1200W, NM-AIR-H14), NovaMart's own fulfilment centres, brands and systems are the same for every
supplier (NovaMart dual-sources the same private-label SKUs); only supplier-side terms differ.
"""

from __future__ import annotations

import copy
import datetime as _dt
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from functools import lru_cache
from typing import Any

from app.data.cat4_fixtures import DEAL_ROOM_PROFILE, SUPPLIER_DEAL_ROOM_DOCS

BASE_SUPPLIER = "deccan"
DISTRACTOR_SUPPLIERS: tuple[str, ...] = ("kaveri", "narmada")
SCALES: tuple[int, ...] = (1, 3)
DOCUMENT_ORDER = "interleaved_by_type"  # DOC-01, DOC-08, DOC-15, DOC-02, DOC-09, DOC-16, ...
CHARS_PER_TOKEN_ESTIMATE = 2.4  # the app's own estimate (runner: total_chars / 2.4)

# --------------------------------------------------------------------------------------------------
# Number words
# --------------------------------------------------------------------------------------------------

_ONES = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve",
         "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen"]
_TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]


def int_words(n: int) -> str:
    """0..999 in lowercase English words with hyphenated tens ('forty-eight')."""
    if n < 0 or n > 999:
        raise ValueError(n)
    if n < 20:
        return _ONES[n]
    if n < 100:
        t, o = divmod(n, 10)
        return _TENS[t] + (f"-{_ONES[o]}" if o else "")
    h, rest = divmod(n, 100)
    return f"{_ONES[h]} hundred" + (f" {int_words(rest)}" if rest else "")


def _word_value(word: str) -> int | None:
    w = word.lower()
    for n in range(0, 1000):
        if int_words(n) == w:
            return n
    return None


def _title_words(s: str) -> str:
    return " ".join("-".join(p.capitalize() for p in w.split("-")) for w in s.split(" "))


def indian_amount_words(rupees: int) -> str:
    """'Four Crore Fifty Lakh' style words for a rupee amount (crore / lakh / thousand / rest)."""
    parts = []
    crore, rem = divmod(rupees, 10_000_000)
    lakh, rem = divmod(rem, 100_000)
    thousand, rest = divmod(rem, 1000)
    if crore:
        parts.append(f"{int_words(crore)} crore")
    if lakh:
        parts.append(f"{int_words(lakh)} lakh")
    if thousand:
        parts.append(f"{int_words(thousand)} thousand")
    if rest:
        parts.append(int_words(rest))
    return _title_words(" ".join(parts) or "zero")


def _case_like(src: str, new: str) -> str:
    """Upper-case `new` when `src` is all upper-case (headings), otherwise keep `new` as written."""
    letters = [c for c in src if c.isalpha()]
    return new.upper() if letters and all(c.isupper() for c in letters) else new


# --------------------------------------------------------------------------------------------------
# Supplier specs
# --------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class SupplierSpec:
    key: str
    legal_name: str
    short_name: str
    doc_id_offset: int  # DOC-01 -> DOC-(01 + offset)
    amount_factor: float
    pct_low_factor: float  # percentages below 90
    pct_high_delta: float  # percentages >= 90 (OTIF-style), added
    ratio_factor: float
    count_factor: float
    date_shift_days: int
    duration_map: dict[int, int]
    entities: tuple[tuple[str, str], ...]  # case-insensitive, case-preserving, word-boundary guarded
    overrides: tuple[tuple[str, str], ...]  # exact (case-sensitive) phrases, highest priority
    keyword_map: dict[str, str] = field(default_factory=dict)  # whole-keyword replacements


_DOC_CODE_SUFFIX = {"kaveri": "KHE", "narmada": "NCE"}


def _doc_codes(sfx: str, sl: str) -> tuple[tuple[str, str], ...]:
    return (
        ("MSA-NM-DSA-2026", f"MSA-NM-{sfx}-2026"),
        ("SLA-PEAK-2026", f"SLA-PEAK-{sfx}-2026"),
        ("DPA-DPDP-2026", f"DPA-DPDP-{sfx}-2026"),
        ("REG-BIS-EPR-2026", f"REG-BIS-EPR-{sfx}-2026"),
        ("TAX-GST-ITC-2026", f"TAX-GST-ITC-{sfx}-2026"),
        ("MCA-AOC4-FY26", f"MCA-AOC4-FY26-{sfx}"),
        ("SL-2026-09", sl),
    )


SUPPLIERS: dict[str, SupplierSpec] = {
    "kaveri": SupplierSpec(
        key="kaveri",
        legal_name="Kaveri Home Electricals & Power Pvt. Ltd.",
        short_name="Kaveri",
        doc_id_offset=7,
        amount_factor=0.8,
        pct_low_factor=0.8,
        pct_high_delta=-1.0,
        ratio_factor=0.9,
        count_factor=0.8,
        date_shift_days=-3,
        duration_map={2: 3, 3: 2, 4: 3, 5: 4, 7: 6, 8: 6, 9: 7, 10: 8, 12: 10, 15: 12, 24: 18, 30: 21, 36: 30,
                      43: 41, 45: 40, 48: 36, 60: 45, 72: 60, 90: 75, 120: 90},
        entities=(
            ("Deccan Smart Appliances & Energy Pvt. Ltd.", "Kaveri Home Electricals & Power Pvt. Ltd."),
            ("Deccan", "Kaveri"),
            ("U29300KA2019PTC128441", "U31900MH2017PTC294117"),
            ("29AABCD8841M1Z5", "27AAECK5523R1Z8"),
            ("KroneVolt Energy Systems GmbH (Munich, Germany)", "Solvane Energie SAS (Lyon, France)"),
            ("KroneVolt GmbH (Germany)", "Solvane SAS (France)"),
            ("KroneVolt GmbH", "Solvane SAS"),
            ("KroneVolt", "Solvane"),
            ("Munich R&D", "Lyon R&D"),
            ("Series-C", "Series-B"),
            ("State Bank of India ('SBI')", "HDFC Bank Ltd. ('HDFC')"),
            ("State Bank of India", "HDFC Bank"),
            ("SBI", "HDFC"),
            ("Negative Covenant Clause 14.3", "Negative Covenant Clause 11.2"),
            ("K. Raghavan & Associates LLP", "Mehta Kulkarni & Co. LLP"),
            ("100884129", "100912377"),
            ("AB9920411", "AB8817302"),
            ("R-41209877", "R-41388205"),
            ("EPR-KA-2025-08814", "EPR-MH-2025-11427"),
            ("Peenya-Unit-2", "Chakan-Unit-1"),
            ("Peenya (Bengaluru)", "Chakan (Pune)"),
            ("Peenya Bengaluru", "Chakan Pune"),
            ("Peenya", "Chakan"),
            ("plot #44", "plot #17"),
            ("Mid-Corporate Branch Bengaluru", "Mid-Corporate Branch Pune"),
            ("Courts at Bengaluru, Karnataka", "Courts at Pune, Maharashtra"),
            ("seated in Bengaluru", "seated in Pune"),
            ("Bengaluru Arbitration", "Pune Arbitration"),
            ("Karnataka and Maharashtra", "Maharashtra and Gujarat"),
            ("Maharashtra GST, Mazgaon Division", "Telangana GST, Begumpet Division"),
            ("Maharashtra GST", "Telangana GST"),
            ("MH GST", "TG GST"),
            ("CGST/MGST Act", "CGST/TGST Act"),
            ("Mumbai Bench", "Hyderabad Bench"),
            ("AWS Asia Pacific ap-south-1 (Mumbai)", "Microsoft Azure Central India (Pune)"),
            ("ap-south-2 (Hyderabad)", "South India (Chennai)"),
            ("via AWS KMS", "via Azure Key Vault"),
            ("AWS SCP guardrails", "Azure Policy guardrails"),
            ("cross-region S3 replication or EBS snapshot sharing",
             "cross-region Blob Storage replication or managed-disk snapshot sharing"),
            ("CloudTrail/VPC logs", "Azure Activity Log/NSG flow logs"),
            ("AWS ap-south-1/ap-south-2 KMS realms", "Azure Central India/South India Key Vault realms"),
            ("AWS ap-south-1/ap-south-2", "Azure Central India/South India"),
            ("AWS Mumbai/Hyderabad", "Azure Pune/Chennai"),
            ("ap-south-1 / ap-south-2", "Central India / South India"),
            ("ap-south-1", "Central India"),
            ("ap-south-2", "South India"),
            *_doc_codes("KHE", "SL-KHE-2026-11"),
        ),
        overrides=(
            ("intra-Karnataka Peenya-to-FC-BLR-01 supplies, or IGST 18% on inter-state dispatches to FC-BOM-02/FC-HYD-01/FC-DEL-03",
             "intra-Maharashtra Chakan-to-FC-BOM-02 supplies, or IGST 18% on inter-state dispatches to FC-BLR-01/FC-HYD-01/FC-DEL-03"),
            ("2-day buffer", "4-day buffer"),
            ("55%/45%", "60%/40%"),
            ("driven 62% by LFP portable storage and 38% by smart purifiers",
             "driven 57% by LFP portable storage and 43% by smart purifiers"),
            ("3,100 early Gen-1", "2,400 early Gen-1"),
            ("every 180 days", "every 150 days"),
        ),
        keyword_map={"Mumbai": "Pune", "Hyderabad": "Chennai", "KMS": "Key Vault", "GmbH": "SAS", "Bengaluru": "Pune",
                     "3,100": "2,400", "45 days": "45 days"},
    ),
    "narmada": SupplierSpec(
        key="narmada",
        legal_name="Narmada Consumer Electronics & Storage Pvt. Ltd.",
        short_name="Narmada",
        doc_id_offset=14,
        amount_factor=1.35,
        pct_low_factor=1.2,
        pct_high_delta=0.6,
        ratio_factor=1.1,
        count_factor=1.2,
        date_shift_days=-8,
        duration_map={2: 5, 3: 4, 4: 5, 5: 7, 7: 10, 8: 10, 9: 12, 10: 14, 12: 16, 15: 20, 24: 30, 30: 45, 36: 48,
                      43: 40, 45: 60, 48: 60, 60: 90, 72: 96, 90: 120, 120: 150},
        entities=(
            ("Deccan Smart Appliances & Energy Pvt. Ltd.", "Narmada Consumer Electronics & Storage Pvt. Ltd."),
            ("Deccan", "Narmada"),
            ("U29300KA2019PTC128441", "U27100GJ2018PTC103562"),
            ("29AABCD8841M1Z5", "24AAFCN7719Q1Z2"),
            ("KroneVolt Energy Systems GmbH (Munich, Germany)", "Hanbit Cell Technologies Co. (Busan, South Korea)"),
            ("KroneVolt GmbH (Germany)", "Hanbit Co. (South Korea)"),
            ("KroneVolt GmbH", "Hanbit Co."),
            ("KroneVolt", "Hanbit"),
            ("Munich R&D", "Busan R&D"),
            ("Series-C", "Series-D"),
            ("State Bank of India ('SBI')", "Bank of Baroda ('BoB')"),
            ("State Bank of India", "Bank of Baroda"),
            ("SBI", "BoB"),
            ("Negative Covenant Clause 14.3", "Negative Covenant Clause 8.6"),
            ("K. Raghavan & Associates LLP", "Desai Shah & Associates LLP"),
            ("100884129", "100765402"),
            ("AB9920411", "AB9104526"),
            ("R-41209877", "R-41075519"),
            ("EPR-KA-2025-08814", "EPR-GJ-2025-06352"),
            ("Peenya-Unit-2", "Sanand-Unit-3"),
            ("Peenya (Bengaluru)", "Sanand (Ahmedabad)"),
            ("Peenya Bengaluru", "Sanand Ahmedabad"),
            ("Peenya", "Sanand"),
            ("plot #44", "plot #62"),
            ("Mid-Corporate Branch Bengaluru", "Mid-Corporate Branch Ahmedabad"),
            ("Courts at Bengaluru, Karnataka", "Courts at Ahmedabad, Gujarat"),
            ("seated in Bengaluru", "seated in Ahmedabad"),
            ("Bengaluru Arbitration", "Ahmedabad Arbitration"),
            ("Karnataka and Maharashtra", "Gujarat and Rajasthan"),
            ("Maharashtra GST, Mazgaon Division", "Tamil Nadu GST, Ambattur Division"),
            ("Maharashtra GST", "Tamil Nadu GST"),
            ("MH GST", "TN GST"),
            ("CGST/MGST Act", "CGST/TNGST Act"),
            ("Mumbai Bench", "Chennai Bench"),
            ("AWS Asia Pacific ap-south-1 (Mumbai)", "Google Cloud asia-south1 (Mumbai)"),
            ("ap-south-2 (Hyderabad)", "asia-south2 (Delhi)"),
            ("via AWS KMS", "via Cloud KMS"),
            ("AWS SCP guardrails", "Organization Policy guardrails"),
            ("cross-region S3 replication or EBS snapshot sharing",
             "cross-region Cloud Storage replication or persistent-disk snapshot sharing"),
            ("CloudTrail/VPC logs", "Cloud Audit Logs/VPC Flow Logs"),
            ("AWS ap-south-1/ap-south-2 KMS realms", "Google Cloud asia-south1/asia-south2 Cloud KMS realms"),
            ("AWS ap-south-1/ap-south-2", "Google Cloud asia-south1/asia-south2"),
            ("AWS Mumbai/Hyderabad", "Google Cloud Mumbai/Delhi"),
            ("ap-south-1 / ap-south-2", "asia-south1 / asia-south2"),
            ("ap-south-1", "asia-south1"),
            ("ap-south-2", "asia-south2"),
            *_doc_codes("NCE", "SL-NCE-2026-07"),
        ),
        overrides=(
            ("CGST 9% + SGST 9% on intra-Karnataka Peenya-to-FC-BLR-01 supplies, or IGST 18% on inter-state dispatches to FC-BOM-02/FC-HYD-01/FC-DEL-03",
             "CGST 9% + SGST 9% on intra-Gujarat Sanand bonded-warehouse supplies, or IGST 18% on inter-state dispatches to FC-BLR-01/FC-BOM-02/FC-HYD-01/FC-DEL-03"),
            ("2-day buffer", "5-day buffer"),
            ("55%/45%", "50%/50%"),
            ("driven 62% by LFP portable storage and 38% by smart purifiers",
             "driven 66% by LFP portable storage and 34% by smart purifiers"),
            ("3,100 early Gen-1", "3,800 early Gen-1"),
            ("every 180 days", "every 120 days"),
        ),
        keyword_map={"Hyderabad": "Delhi", "GmbH": "Co.", "Bengaluru": "Ahmedabad", "3,100": "3,800", "45 days": "45 days"},
    ),
}

# Statutory constants and calendar facts that must read the same for every supplier (regex, case-insensitive).
PROTECTED_PATTERNS: tuple[str, ...] = (
    r"\b45-day", r"\bDay 45\b", r"\bsix \(6\) hours", r"(?<![\d.])6[- ]hours?\b", r"\b6-Hr\b",
    r"retained for 180 days", r"180[- ]day", r"180 calendar days", r"(?<![\d.])180 days\b",
    r"\bsept(?:ember)? 30(?!,? 20\d\d)", r"\bmarch 31(?:,? 20\d\d)?", r"\bapril 1, 2025", r"\bapril 28, 2022",
    r"\bnovember 30 annual", r"(?<![\d.])18 ?%", r"(?<![\d.])9 ?%", r"(?<![\d.])100 ?%", r"(?<![\d.])10 ?%",
    r"(?<![\d.])30 ?%", r"\b100 Wh\b", r"\b12x\b", r"\beight \(8\) years", r"\b8-year", r">6-month",
    r"\b21 days prior", r"\bfive days prior", r"\bINR 250 ?(?:Crore|Cr)\b", r"\bINR 200 ?(?:Crore|Cr)\b",
    r"\bINR 250(?![\d.,])", r"(?<![\w.])250 ?(?:Crore|Cr)\b", r"(?<![\w.])200 ?(?:Crore|Cr)\b",
    r"\b24x7x365\b",
)

_MONTHS_FULL = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
                "November", "December"]
_MONTH_ABBR = {"Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "Jun": 6, "Jul": 7, "Aug": 8, "Sep": 9, "Sept": 9, "Oct": 10,
               "Nov": 11, "Dec": 12}
_MONTH_RE = "|".join([*_MONTHS_FULL, "Sept", *[k for k in _MONTH_ABBR if k != "Sept"]])
_DUR_UNITS = r"(?:days?|hours?|months?|Mo\b|minutes?|Min\b|years?|weeks?|Hr\b|h\b)"
_DUR_ADJ = r"(?:calendar |business |consecutive |working )?"

RULE_PATTERNS: dict[str, re.Pattern[str]] = {
    "amount": re.compile(
        r"(?P<cur>INR) ?(?P<num>\d[\d,]*(?:\.\d+)?)(?P<unit> ?(?:Crore|Cr|Lakh)\b)?"
        r"(?P<words> \(Rupees (?:[A-Z][a-z]+(?:-[A-Z][a-z]+)? ?)+?(?=Only\)|\)|landed))?"
    ),
    "amount_bare": re.compile(r"(?<![\w.,])(?P<num>\d+(?:\.\d+)?)(?P<unit> ?(?:Crore|Cr)\b)"),
    "date_full": re.compile(rf"\b(?P<m>{_MONTH_RE})\.? (?P<d>\d{{1,2}})(?!\d)(?P<y>,? 20\d\d)?", re.I),
    "date_iso": re.compile(r"\b(?P<y>20\d\d)-(?P<m>\d\d)-(?P<d>\d\d)\b"),
    "word_duration": re.compile(
        rf"\b(?P<w>[A-Za-z]+(?:-[A-Za-z]+)?) \((?P<n>\d+)\)(?= {_DUR_ADJ}{_DUR_UNITS})", re.I
    ),
    "t_plus": re.compile(r"\bT\+(?P<n>\d+)\b"),
    "duration": re.compile(rf"(?<![\d.,+#/])(?P<n>\d+)(?P<sep>[ -]|)(?={_DUR_ADJ}{_DUR_UNITS})", re.I),
    "pct": re.compile(r"(?<![\d.])(?P<sign>\+)?(?P<num>\d+(?:\.\d+)?)(?P<sp> ?)%"),
    "ratio": re.compile(r"(?<![\d.])(?P<num>\d+\.\d+)x\b"),
    "count": re.compile(r"(?<![\d.,])(?P<num>\d{1,3}(?:,\d{3})+|\d+)(?=-unit| finished units| units)"),
}


# --------------------------------------------------------------------------------------------------
# Value transforms
# --------------------------------------------------------------------------------------------------


def _round(value: float, decimals: int) -> Decimal:
    q = Decimal(1).scaleb(-decimals) if decimals else Decimal(1)
    return Decimal(str(value)).quantize(q, rounding=ROUND_HALF_UP)


def _decimals(num: str) -> int:
    return len(num.split(".")[1]) if "." in num else 0


def _indian_group(n: int) -> str:
    s = str(n)
    if len(s) <= 3:
        return s
    head, tail = s[:-3], s[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    return ",".join(groups + [tail])


def _scale_decimal(num: str, factor: float) -> str:
    """Scale a decimal literal keeping its decimals; use 2 decimals when keeping them would lose the value."""
    v = float(num.replace(",", "")) * factor
    d = _decimals(num)
    a, b = _round(v, d), _round(v, max(d, 2))
    return format(a if a == b else b, "f")


def _scale_rupees(num: str, factor: float) -> tuple[str, int]:
    v = int(num.replace(",", ""))
    raw = v * factor
    step = 100_000 if v >= 10_000_000 else (1000 if v >= 10_000 else 10)
    new = int(_round(raw / step, 0)) * step
    if new == v:
        new = v + step
    return _indian_group(new), new


def _pct(num: str, spec: SupplierSpec) -> str:
    v = float(num)
    d = _decimals(num)
    if v >= 90:
        new = min(v + spec.pct_high_delta, 99.6)
    else:
        new = v * spec.pct_low_factor
    out = _round(new, d)
    if out == _round(v, d) or out <= 0:
        out = _round(new, d + 1)
    return format(out, "f")


def _int_map(n: int, spec: SupplierSpec) -> int:
    if n in spec.duration_map:
        return spec.duration_map[n]
    new = int(_round(n * spec.amount_factor, 0))
    return new if new != n and new > 0 else n + 1


def _shift_date(y: int, m: int, d: int, spec: SupplierSpec) -> _dt.date:
    return _dt.date(y, m, d) + _dt.timedelta(days=spec.date_shift_days)


# --------------------------------------------------------------------------------------------------
# Single-pass transform engine
# --------------------------------------------------------------------------------------------------


@dataclass
class _Cand:
    start: int
    end: int
    priority: int
    new: str
    kind: str
    orig_num: str | None = None
    new_num: str | None = None


def _bounded_literal_re(lit: str) -> re.Pattern[str]:
    pre = r"(?<![A-Za-z0-9])" if lit[0].isalnum() else ""
    post = r"(?![A-Za-z0-9])" if lit[-1].isalnum() else ""
    return re.compile(pre + re.escape(lit) + post, re.I)


@lru_cache(maxsize=None)
def _compiled_entities(key: str) -> list[tuple[re.Pattern[str], str, str]]:
    spec = SUPPLIERS[key]
    return [(_bounded_literal_re(old), old, new) for old, new in spec.entities]


_PROTECT_RES = [re.compile(p, re.I) for p in PROTECTED_PATTERNS]


def _rule_candidates(text: str, spec: SupplierSpec) -> list[_Cand]:
    out: list[_Cand] = []
    for m in RULE_PATTERNS["amount"].finditer(text):
        num, unit, words = m.group("num"), m.group("unit") or "", m.group("words")
        if unit or ("," not in num and float(num.replace(",", "")) < 1000):
            new_num = _scale_decimal(num, spec.amount_factor)
            rupees = int(_round(float(new_num) * (1e7 if "Cr" in unit else 1e5 if "Lakh" in unit else 1e7), 0))
        else:
            new_num, rupees = _scale_rupees(num, spec.amount_factor)
        new = f"{m.group('cur')} {new_num}{unit}" if text[m.start() + 3:m.start() + 4] == " " else f"{m.group('cur')}{new_num}{unit}"
        if words:
            new += f" (Rupees {indian_amount_words(rupees)}" + (" " if words.endswith(" ") else "")
        out.append(_Cand(m.start(), m.end(), 3, new, "amount", num, new_num))
    for m in RULE_PATTERNS["amount_bare"].finditer(text):
        new_num = _scale_decimal(m.group("num"), spec.amount_factor)
        out.append(_Cand(m.start(), m.end(), 3, new_num + m.group("unit"), "amount", m.group("num"), new_num))
    for m in RULE_PATTERNS["date_full"].finditer(text):
        mon = m.group("m")
        mon_key = mon[:1].upper() + mon[1:].lower()
        month = _MONTHS_FULL.index(mon_key) + 1 if mon_key in _MONTHS_FULL else _MONTH_ABBR.get(mon_key)
        if not month:
            continue
        ytxt = m.group("y") or ""
        year = int(re.sub(r"\D", "", ytxt)) if ytxt else 2026
        try:
            nd = _shift_date(year, month, int(m.group("d")), spec)
        except ValueError:
            continue
        if mon_key in _MONTHS_FULL or nd.month == 5:
            new_mon = _MONTHS_FULL[nd.month - 1]
        elif nd.month == 9 and mon_key == "Sept":
            new_mon = "Sept"
        else:
            new_mon = next(k for k, v in _MONTH_ABBR.items() if v == nd.month)
        new = _case_like(mon, new_mon) + f" {nd.day}"
        if ytxt:
            new += ("," if "," in ytxt else "") + f" {nd.year}"
        out.append(_Cand(m.start(), m.end(), 3, new, "date"))
    for m in RULE_PATTERNS["date_iso"].finditer(text):
        nd = _shift_date(int(m.group("y")), int(m.group("m")), int(m.group("d")), spec)
        out.append(_Cand(m.start(), m.end(), 3, nd.isoformat(), "date"))
    for m in RULE_PATTERNS["word_duration"].finditer(text):
        n = int(m.group("n"))
        if _word_value(m.group("w")) != n:
            continue
        nn = _int_map(n, spec)
        out.append(_Cand(m.start(), m.end(), 3, f"{_case_like(m.group('w'), int_words(nn))} ({nn})", "duration",
                         str(n), str(nn)))
    for m in RULE_PATTERNS["t_plus"].finditer(text):
        nn = _int_map(int(m.group("n")), spec)
        out.append(_Cand(m.start(), m.end(), 3, f"T+{nn}", "duration", m.group("n"), str(nn)))
    for m in RULE_PATTERNS["duration"].finditer(text):
        n = int(m.group("n"))
        nn = _int_map(n, spec)
        out.append(_Cand(m.start(), m.end(), 3, f"{nn}{m.group('sep')}", "duration", str(n), str(nn)))
    for m in RULE_PATTERNS["pct"].finditer(text):
        new_num = _pct(m.group("num"), spec)
        out.append(_Cand(m.start(), m.end(), 3, f"{m.group('sign') or ''}{new_num}{m.group('sp')}%", "percent",
                         m.group("num") + "%", new_num + "%"))
    for m in RULE_PATTERNS["ratio"].finditer(text):
        new_num = format(_round(float(m.group("num")) * spec.ratio_factor, _decimals(m.group("num"))), "f")
        out.append(_Cand(m.start(), m.end(), 3, f"{new_num}x", "ratio", m.group("num") + "x", new_num + "x"))
    for m in RULE_PATTERNS["count"].finditer(text):
        num = m.group("num")
        v = int(num.replace(",", ""))
        nv = int(_round(v * spec.count_factor / 100, 0)) * 100
        new_num = f"{nv:,}" if "," in num else str(nv)
        out.append(_Cand(m.start(), m.end(), 3, new_num, "count", num, new_num))
    return out


def transform_text(text: str, supplier: str) -> tuple[str, list[dict[str, Any]]]:
    """Deterministic single-pass transform; returns (new_text, [replacement records])."""
    spec = SUPPLIERS[supplier]
    cands: list[_Cand] = []
    for old, new in spec.overrides:
        for m in re.finditer(re.escape(old), text):
            cands.append(_Cand(m.start(), m.end(), 0, new, "override"))
    for rx in _PROTECT_RES:
        for m in rx.finditer(text):
            cands.append(_Cand(m.start(), m.end(), 1, m.group(0), "protected"))
    for rx, _old, new in _compiled_entities(supplier):
        for m in rx.finditer(text):
            cands.append(_Cand(m.start(), m.end(), 2, _case_like(m.group(0), new), "entity"))
    cands += _rule_candidates(text, spec)

    accepted: list[_Cand] = []
    for c in sorted(cands, key=lambda c: (c.priority, c.start, -(c.end - c.start))):
        if any(c.start < a.end and a.start < c.end for a in accepted):
            continue
        accepted.append(c)
    accepted.sort(key=lambda c: c.start)

    out, cursor, records = [], 0, []
    for c in accepted:
        out.append(text[cursor:c.start])
        out.append(c.new)
        cursor = c.end
        if c.kind != "protected" and c.new != text[c.start:c.end]:
            records.append({"kind": c.kind, "original": text[c.start:c.end], "distractor": c.new,
                            "original_number": c.orig_num, "distractor_number": c.new_num})
    out.append(text[cursor:])
    return "".join(out), records


def _transform_keyword(kw: str, supplier: str, numeric_pairs: dict[str, str]) -> str:
    spec = SUPPLIERS[supplier]
    if kw in spec.keyword_map:
        return spec.keyword_map[kw]
    new, _ = transform_text(kw, supplier)
    if new == kw and re.fullmatch(r"[\d,.]+%?x?", kw) and kw in numeric_pairs:
        return numeric_pairs[kw]
    return new


def _date_iso_shift(iso: str, supplier: str) -> str:
    y, m, d = (int(x) for x in iso.split("-"))
    return _shift_date(y, m, d, SUPPLIERS[supplier]).isoformat()


def build_distractor_docs(supplier: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """(raw docs in SUPPLIER_DEAL_ROOM_DOCS schema, mapping records with location) for one distractor supplier."""
    spec = SUPPLIERS[supplier]
    docs: list[dict[str, Any]] = []
    mapping: list[dict[str, Any]] = []

    def tx(s: str, where: str) -> str:
        new, recs = transform_text(s, supplier)
        for r in recs:
            mapping.append({**r, "where": where})
        return new

    for base in SUPPLIER_DEAL_ROOM_DOCS:
        base_num = int(base["doc_id"].split("-")[1])
        new_doc_id = f"DOC-{base_num + spec.doc_id_offset:02d}"
        doc = {
            "doc_id": new_doc_id,
            "doc_code": tx(base["doc_code"], f"{new_doc_id}.doc_code"),
            "title": tx(base["title"], f"{new_doc_id}.title"),
            "doc_type": base["doc_type"],
            "effective_date": _date_iso_shift(base["effective_date"], supplier),
            "summary": tx(base["summary"], f"{new_doc_id}.summary"),
            "source_doc_id": base["doc_id"],
            "supplier": supplier,
            "chunks": [],
        }
        for ch in base["chunks"]:
            new_cid = ch["chunk_id"].replace(base["doc_id"], new_doc_id)
            text, recs = transform_text(ch["text"], supplier)
            for r in recs:
                mapping.append({**r, "where": f"{new_cid}.text"})
            pairs = {r["original_number"]: r["distractor_number"] for r in recs if r.get("original_number")}
            doc["chunks"].append(
                {
                    "chunk_id": new_cid,
                    "source_chunk_id": ch["chunk_id"],
                    "clause_ref": tx(ch["clause_ref"], f"{new_cid}.clause_ref"),
                    "section_heading": tx(ch["section_heading"], f"{new_cid}.section_heading"),
                    "keywords": [_transform_keyword(k, supplier, pairs) for k in ch["keywords"]],
                    "text": text,
                }
            )
        docs.append(doc)
    return docs, mapping


# --------------------------------------------------------------------------------------------------
# Hydration (mirrors cat4_fixtures.hydrate_deal_room_index exactly, for any document list)
# --------------------------------------------------------------------------------------------------


def hydrate_docs(raw_docs: Sequence[dict[str, Any]], supplier_names: Sequence[str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
    hydrated_docs: list[dict[str, Any]] = []
    flat_chunks: list[dict[str, Any]] = []
    total_chars = 0
    for doc_idx, (doc, supplier_name) in enumerate(zip(raw_docs, supplier_names)):
        full_parts: list[str] = []
        cursor = 0
        doc_chunks_out: list[dict[str, Any]] = []
        for c_idx, ch in enumerate(doc["chunks"]):
            header_prefix = f"[{ch['chunk_id']} · {ch['clause_ref']}]\n"
            block_str = header_prefix + ch["text"]
            doc_char_start = cursor
            doc_char_end = cursor + len(block_str)
            chunk_rec = {
                **ch,
                "doc_index": doc_idx,
                "doc_id": doc["doc_id"],
                "doc_code": doc["doc_code"],
                "doc_title": doc["title"],
                "doc_type": doc["doc_type"],
                "doc_char_start": doc_char_start,
                "doc_char_end": doc_char_end,
                "header_len": len(header_prefix),
                "full_block_text": block_str,
                "char_count": len(block_str),
                "approx_tokens": max(1, round(len(block_str) / 2.6)),
            }
            doc_chunks_out.append(chunk_rec)
            flat_chunks.append(chunk_rec)
            full_parts.append(block_str)
            cursor = doc_char_end + (2 if c_idx < len(doc["chunks"]) - 1 else 0)
        full_text = "\n\n".join(full_parts)
        total_chars += len(full_text)
        hydrated_docs.append(
            {
                "doc_index": doc_idx,
                "doc_id": doc["doc_id"],
                "doc_code": doc["doc_code"],
                "title": doc["title"],
                "doc_type": doc["doc_type"],
                "effective_date": doc["effective_date"],
                "summary": doc["summary"],
                "block_title": f"{doc['doc_id']} :: {doc['doc_code']} — {doc['title']}",
                "block_context": (
                    f"{doc['doc_type']} (Effective {doc['effective_date']}) for supplier {supplier_name}"
                ),
                "full_text": full_text,
                "char_count": len(full_text),
                "approx_tokens": max(1, round(len(full_text) / 2.6)),
                "chunks": doc_chunks_out,
            }
        )
    return hydrated_docs, flat_chunks, total_chars


@dataclass(frozen=True)
class ScaledCorpus:
    scale: int
    hydrated_docs: list[dict[str, Any]]
    flat_chunks: list[dict[str, Any]]
    total_chars: int
    supplier_by_doc: dict[str, str]
    mapping: dict[str, list[dict[str, Any]]]

    @property
    def doc_by_id(self) -> dict[str, dict[str, Any]]:
        return {d["doc_id"]: d for d in self.hydrated_docs}

    @property
    def chunk_by_id(self) -> dict[str, dict[str, Any]]:
        return {c["chunk_id"]: c for c in self.flat_chunks}

    def supplier_of_chunk(self, chunk_id: str) -> str:
        return self.supplier_by_doc.get(chunk_id.split("#")[0], "unknown")

    def size(self) -> dict[str, Any]:
        return corpus_size(self)


@lru_cache(maxsize=None)
def _scaled(scale: int) -> ScaledCorpus:
    if scale not in SCALES:
        raise ValueError(f"scale must be one of {SCALES}")
    base_docs = list(SUPPLIER_DEAL_ROOM_DOCS)
    base_name = str(DEAL_ROOM_PROFILE["supplier_legal_name"])
    if scale == 1:
        docs, names, sup = base_docs, [base_name] * len(base_docs), {d["doc_id"]: BASE_SUPPLIER for d in base_docs}
        hydrated, flat, total = hydrate_docs(docs, names)
        return ScaledCorpus(1, hydrated, flat, total, sup, {})
    extra = {s: build_distractor_docs(s) for s in DISTRACTOR_SUPPLIERS}
    docs, names, sup = [], [], {}
    for i, base in enumerate(base_docs):  # interleaved by document type
        docs.append(base)
        names.append(base_name)
        sup[base["doc_id"]] = BASE_SUPPLIER
        for s in DISTRACTOR_SUPPLIERS:
            d = extra[s][0][i]
            docs.append(d)
            names.append(SUPPLIERS[s].legal_name)
            sup[d["doc_id"]] = s
    hydrated, flat, total = hydrate_docs(docs, names)
    return ScaledCorpus(scale, hydrated, flat, total, sup, {s: extra[s][1] for s in DISTRACTOR_SUPPLIERS})


def build_scaled_corpus(scale: int) -> ScaledCorpus:
    """Deterministic corpus for `scale` (1 = the app's deal room; 3 = + two distractor suppliers). Deep copy."""
    return copy.deepcopy(_scaled(scale))


def estimate_tokens(chars: int) -> int:
    return max(1, round(chars / CHARS_PER_TOKEN_ESTIMATE))


def corpus_size(corpus: ScaledCorpus) -> dict[str, Any]:
    base = _scaled(1)
    return {
        "scale": corpus.scale,
        "documents": len(corpus.hydrated_docs),
        "chunks": len(corpus.flat_chunks),
        "chars": corpus.total_chars,
        "estimated_tokens": estimate_tokens(corpus.total_chars),
        "ratio_to_base_chars": round(corpus.total_chars / base.total_chars, 3),
        "chars_per_token_assumed": CHARS_PER_TOKEN_ESTIMATE,
    }


# --------------------------------------------------------------------------------------------------
# Contamination detector
# --------------------------------------------------------------------------------------------------


def distractor_values_for_fact(fact: dict[str, Any], supplier: str, alternatives: Sequence[str]) -> list[str]:
    """The fact's value as the distractor supplier states it: each alternative through the supplier transform."""
    out = []
    for alt in alternatives:
        new, _ = transform_text(alt, supplier)
        if new.lower() != alt.lower() and new not in out:
            out.append(new)
    return out


def build_contamination_index(
    facts: Sequence[dict[str, Any]],
    alternatives_of: Callable[[dict[str, Any]], list[str]],
    matcher: Callable[[str, Sequence[str]], bool],
) -> dict[str, dict[str, Any]]:
    """fact_id -> {supplier: [distractor values]}, dropping values that also occur in the Deccan corpus."""
    base_texts = [c["full_block_text"] for c in _scaled(1).flat_chunks]
    index: dict[str, dict[str, Any]] = {}
    for f in facts:
        if not f.get("supplier_specific"):
            continue
        entry: dict[str, Any] = {"by_supplier": {}, "excluded_ambiguous": {}}
        for s in DISTRACTOR_SUPPLIERS:
            vals = distractor_values_for_fact(f, s, alternatives_of(f))
            keep = [v for v in vals if not any(matcher(t, [v]) for t in base_texts)]
            entry["by_supplier"][s] = keep
            if len(keep) != len(vals):
                entry["excluded_ambiguous"][s] = [v for v in vals if v not in keep]
        index[f["id"]] = entry
    return index
