"""IT & HR Service Desk knowledge prefix & 10-turn NovaMart employee dialogues for Category 3."""

from __future__ import annotations

from typing import Any

# ~5,300+ Claude 5.5 tokens (~19,500+ chars of structured policy tables, CLI SOPs & ticket runbooks)
# Guaranteed well above Anthropic's 4,096-token ephemeral cacheable prefix threshold on Sonnet 5.5.
IT_HR_HANDBOOK_MARKDOWN = """=== NOVAMART ENTERPRISE · UNIFIED IT & HR SERVICE DESK OPERATIONS HANDBOOK (REV 2026.11) ===
DOCUMENT CONTROL: SD-HANDBOOK-v2026.11 · SCOPE: 18,000 CORPORATE, HUB & TECH EMPLOYEES
RESPONSE GOVERNANCE SLA: Keep Turns 1–9 strictly 110–180 words (max 4 tight bullets, zero preamble) and final summary turns strictly <= 250 words as ONE compact Markdown table with zero extra prose, strictly grounded in Policy IDs and runbook commands below, with exact INR/USD math and target Service Desk queue IDs. NEVER ask employees to paste raw payment cards, full unmasked Aadhaar numbers, or private SSH keys in chat.

================================================================================
MODULE 1 · IT-SEC-SOP-101 · ZERO-TRUST IDENTITY, OKTA FASTPASS, FIDO2 & PAM BASTION
================================================================================
1.1 OKTA FASTPASS & DEVICE POSTURE VALIDATION (ERR_DEVICE_POSTURE_STALE_90D)
- Trigger Condition: Corporate laptops returning from >45 days inactive leave, OS minor upgrades, or expired SCEP device certificates throw `ERR_DEVICE_POSTURE_STALE_90D` inside Okta Verify / Okta FastPass.
- Non-Wipe Guarantee: `ERR_DEVICE_POSTURE_STALE_90D` NEVER requires laptop re-imaging or disk wipe unless Security Incident Response holds a CrowdStrike quarantine flag (`CS_CONTAINED=true`).
- Standard Diagnostic Sequence:
  1. Verify local Okta Verify daemon & MDM SCEP certificate validity:
     `security find-certificate -c "NovaMart-Device-ID" -Z /Library/Keychains/System.keychain`
     `defaults read /Library/Managed\\ Preferences/com.okta.mobile.plist PostureTimestamp`
  2. Check CrowdStrike Falcon sensor heartbeat (must be < 24h for Green Posture):
     `sudo /Applications/Falcon.app/Contents/Resources/falconctl stats agent_info`
  3. Re-attest device posture after Jamf SCEP renewal (Section 2.1):
     `open -a "Okta Verify"` -> Account -> `Re-verify Device Posture`, or CLI `nm-cli okta reattest --device-serial <SERIAL>`.
- Queue & SLA: `IT-IAM-FASTPASS` (Tier-1 automated posture refresh 10 min; manual SCEP bind SLA 30 min P2).

1.2 FIDO2 / YUBIKEY WEBAUTHN ATTESTATION (OKTA_WEBAUTHN_ATTESTATION_MISMATCH)
- Trigger Condition: Chrome/Edge Chromium v130+ or macOS Sequoia updates can reject legacy AAGUID firmware or USB-C hub pass-through, or a replacement YubiKey 5C NFC presents an unregistered AAGUID (`OKTA_WEBAUTHN_ATTESTATION_MISMATCH`), blocking SSH Bastion / SSO logins.
- Immediate CLI & Diagnostics:
  1. List hardware key AAGUID and firmware version:
     `ykman info && ykman fido info`
  2. Inspect local WebAuthn authenticator logs on macOS:
     `log show --predicate 'subsystem == "com.apple.AuthenticationServices"' --last 15m`
  3. Enroll registered backup key or request temporary bypass: DO NOT tell an engineer to disable MFA or bypass conditional access locally.
- Temporary 24-Hour FIDO2 Bypass Policy (`MFA-BYPASS-24H`):
  - Permitted ONLY after dual identity verification: (a) Workday Employee ID + Manager Workday ID + active corporate laptop Okta FastPass green posture (`Posture=TRUSTED`).
  - Bypass code TTL: Strictly **24 hours**, single-use emergency enrollment token enabling `enroll.okta.novamart.internal` to bind a new YubiKey 5C NFC (`AAGUID 2fc0579f-8113-47ea-b116-bb5a8db9202a` or `cb69481e-8ff7-4039-93ec-0a2729a154a8`).
  - Hardware Replacement SLA: 24h in-person IT Genius locker pickup (BLR-RMZ, HYD-HITEC, MUM-BKC hubs) or 48h insured BlueDart courier dispatch.
- Queue & SLA: `IT-IAM-FIDO2` (P1 15 min for SRE/On-Call with active swap; P2 2h standard replacement).

1.3 PRODUCTION KUBERNETES BASTION & PAM JUST-IN-TIME ACCESS (PAM_JIT_ROLE_DENIED_403)
- Policy Rule (`IT-SEC-PAM-09`): Zero standing privileged access exists on `prod-k8s-sre`, `prod-payments-db`, or `prod-checkout-eks`. All sessions require Teleport/BeyondTrust PAM Just-In-Time (JIT) lease elevation.
- Failure Error `PAM_JIT_ROLE_DENIED_403` occurs when ANY ONE of 4 prerequisites is missing:
  1. Active **FIDO2 hardware WebAuthn assertion** (soft OTP/SMS/FastPass-only sessions cannot open `prod-k8s-sre`; `MFA-BYPASS-24H` does NOT unlock `prod-*` clusters!).
  2. Max JIT Lease Cap: **Strictly <= 4 hours (240 minutes)** per request (`ttl_minutes <= 240`). Requests for `8h` or `12h` auto-fail with `PAM_JIT_ROLE_DENIED_403`.
  3. Required Peer Co-Sign: Must include approval from one active **L7 Principal Engineer / Staff SRE / IC Co-Signer** in the same org unit (`cosign_level >= L7` OR on-duty Incident Commander). Peer L6 or L5 self-approvals are rejected.
  4. Active PagerDuty Schedule or Incident/Change Ticket (`INC-*` / `CHG-*`) in `On-Call Shadow` or `Primary` roster.
- CLI Fix Sequence:
  `tsh logout && tsh login --proxy=pam.novamart.internal --auth=okta-fido2`
  `tsh request create --roles=prod-k8s-sre-ro --reason="CHG-2026-8841" --request-ttl=4h`
- Queue & SLA: `IT-PAM-PROD` (P1 10 min during on-call onboarding or live incidents).

================================================================================
MODULE 2 · IT-END-SOP-204 · JAMF PRO MACBOOK MDM, FILEVAULT & LEAVE RETURN
================================================================================
2.1 MDM CERTIFICATE REVOCATION AFTER EXTENDED LEAVE (MDM_CERT_REVOKED_INACTIVE_LEAVE)
- Root Cause: Automated Jamf Pro hygiene job revokes APNs/SCEP MDM client certificates on devices offline **> 60 consecutive days** (`INACTIVE_LEAVE_LOCK`), protecting dormant endpoints during 12w–26w parental/medical leaves.
- FileVault Non-Wipe Safety Rule: Re-enrolling MDM **NEVER erases user data or rotates out FileVault Disk Recovery** when initiated via `profiles renew`. The existing Personal Recovery Key (PRK) stays escrowed in NovaMart Vault under Asset Tag `NM-MAC-*`.
- Recovery CLI Commands (Run in Terminal with local admin token):
  1. Verify FileVault status & escrowed PRK presence before touching profiles:
     `fdesetup status && profiles status -type enrollment`
  2. Purge stale SCEP keychain entries & request Jamf re-enrollment token from `IT-MDM-ENROLL`:
     `sudo profiles renew -type enrollment`
  3. Trigger immediate inventory check & certificate push:
     `sudo jamf manage && sudo jamf recon -verbose`
  4. Re-apply compliance policies & Okta SCEP trust:
     `sudo jamf policy -event reenroll-posture && sudo jamf policy -event sase-root-ca`
- Expected Recovery Time: 8–12 minutes end-to-end once IT-MDM pushes the temporary pre-stage bypass PIN; formal **P2 Unlock SLA: 30 minutes** from ticket creation (`IT-MDM-LEAVE-UNLOCK`).

2.2 SLACK, JIRA, GITHUB & OKTA GROUP RE-PROVISIONING POST LEAVE (WD-REPROVISION-SLK)
- Trigger: When Workday switches worker status from `ON_LEAVE` -> `ACTIVE`, automated SCIM connector `WD-REPROVISION-SLK` restores birthright groups within `15 minutes` (`OKTA-GROUP-SYNC-15M`), EXCEPT high-sensitivity RBAC groups (`k8s-*`, `fin-sap-write`, `seller-escrow-admin`, private `#war-room-*` Slack channels), which require explicit manager confirmation via Workday task `WD-ACCESS-RECERT`.
- Queue & SLA: `IT-IAM-GROUPS` (P2 60 min auto-sync verify after Workday `ACTIVE` timestamp commits).

================================================================================
MODULE 3 · IT-NET-SOP-309 · GLOBALPROTECT SASE VPN & ARTIFACT REGISTRY PROXY
================================================================================
3.1 TLS INTERCEPTION & SPLIT-TUNNEL MISMATCH (TLS_INTERCEPT_SPLIT_TUNNEL_MISMATCH)
- Symptom: Browser or `curl` connections to `https://corp-erp.novamart.internal`, Workday SSO endpoints, or internal APIs fail with `x509: certificate signed by unknown authority` or `TLS_INTERCEPT_SPLIT_TUNNEL_MISMATCH`.
- Root Cause Matrix:
  1. Corporate MacBook lacks **NovaMart Root CA v4** (`SHA256 Fingerprint: 9F:4B:22:C8:11:04:E7:8A`, rotated October 1, 2026 replacing legacy Root CA v3), OR
  2. Home/ISP IPv6 DNS or local WARP/Docker bridge subnet (`172.17.0.0/16` / `198.18.0.0/15`) collides with Prisma/GlobalProtect SASE Gateway gateway VIPs (`10.240.0.0/16`), routing `.novamart.internal` traffic outside the encrypted split-tunnel.
- Required Split-Tunnel Domains (Must route via `tun0` GlobalProtect SASE):
  - `corp-erp.novamart.internal` (SAP S/4HANA & Finance Ledger)
  - `artifacts.novamart.internal` (Docker / OCI / PyPI / npm Mirror)
  - `workday-sso.novamart.internal` (HR & Absence Management Bridge)
  - `pam.novamart.internal` (Teleport JIT Bastion Control Plane)
- Exact Terminal Remediation Steps:
  1. Inspect installed Root CA SHA256 fingerprint:
     `security find-certificate -a -Z -c "NovaMart Root CA" /Library/Keychains/System.keychain | grep -E "labl|SHA-256"`
  2. Refresh SASE Root CA v4 profile & flush split-tunnel DNS cache:
     `nm-cli cert refresh --profile sase-v4 && sudo dscacheutil -flushcache && sudo killall -HUP mDNSResponder`
  3. Reconnect GlobalProtect SASE gateway forcing IPv4 split-tunnel routes:
     `globalprotect disconnect && globalprotect connect --portal sase-in.novamart.com --disable-ipv6-bypass`
  4. Confirm route & TLS trust:
     `curl -sI https://corp-erp.novamart.internal/healthz | head -n 5`
- Queue & SLA: `IT-NET-SASE` (P2 30 min; Root CA v4 profile push via Jamf).

3.2 INTERNAL DOCKER / ARTIFACT REGISTRY mTLS EXPIRY (CORP_DOCKER_PROXY_MTLS_EXPIRED)
- Symptom: `docker pull artifacts.novamart.internal/...` or Helm/uv sync fails with `CORP_DOCKER_PROXY_MTLS_EXPIRED` or `remote error: tls: expired certificate` on client cert `~/.novamart/certs/registry-client.crt`.
- Policy (`IT-NET-MTLS-14`): Developer mTLS client certificates for `artifacts.novamart.internal` auto-issue for **90 days** tied to green Okta FastPass device posture and are stored in `~/.novamart/certs/` + `~/.docker/certs.d/artifacts.novamart.internal/`.
- Exact CLI Fix:
  1. Inspect expiry & issuer:
     `openssl x509 -in ~/.docker/certs.d/artifacts.novamart.internal/client.cert -noout -dates -subject`
  2. Re-issue 90-day client cert + NovaMart Root CA v4 bundle via Okta FIDO2 session:
     `nm-cli registry login --host artifacts.novamart.internal --mtls --install-ca-v4`
  3. Reload Docker Desktop / Colima trust store:
     `docker logout artifacts.novamart.internal && nm-cli registry verify --pull-test`
- Queue & SLA: `IT-NET-REGISTRY` (P2 20 min automated renewal once FIDO2/Okta posture is valid).

================================================================================
MODULE 4 · HR-IND-POL-412 · PARENTAL LEAVE RETURN, PAYROLL RETRO & BRIDGE WIRE
================================================================================
4.1 PARENTAL & MEDICAL LEAVE ENTITLEMENT (IN & US POLICY BASELINE)
- Primary Caregiver Paid Leave: **26 weeks (182 calendar days) at 100% base salary + 100% continuity of health/RSU vesting**.
- Secondary / Paternity Paid Leave: **12 weeks (84 calendar days) at 100% base salary** within 12 months of birth/adoption.
- Bonus Protection Clause (`HR-BON-412C`): Paid statutory parental leave counts **100% as active eligible service days** for the Q3/Diwali Annual Performance Bonus (`BonusEligibilityFactor = 1.00`, zero pro-rata reduction).

4.2 WORKDAY-TO-SAP PAYROLL RETURN SYNC LAG (LEAVE_RETURN_SYNC_LAG_404) & BRIDGE WIRE
- Cutoff Rule: SAP/ADP Monthly Payroll batch freezes on the **18th calendar day of each month at 18:00 IST**.
- Known Defect `LEAVE_RETURN_SYNC_LAG_404`: When Workday Absence triggers `Return-From-Leave` after manual Manager approval (`WD-LV-*`) OR for new hires joining on/between the **15th and 18th** of the month whose tax/bank packet finalizes after the 18th 18:00 IST cutoff, SAP temporarily inherits stale `UNPAID_LOA_HOLD` or `PRORATA_DEFERRED` status until the next cycle.
- Mandatory Compensation Calculation & Off-Cycle Bridge Wire Policy (`HR-PAY-BRIDGE-48H`):
  - Check exact net variance: `Shortfall = Expected_Net_Salary + Protected_Bonus_Component - Disbursed_Net_Salary`.
  - **Off-Cycle Payroll Bridge Wire Threshold**: If verified net salary + bonus shortfall **exceeds ₹25,000 INR (or $300 USD)**, HR Payroll Operations MUST release an **Off-Cycle NEFT/IMPS Payroll Bridge Wire within 48 business hours** (rather than forcing the employee to wait until next month's regular cycle!).
  - Tax withholding reconciliation (TDS Section 192 / Form 16 YTD) adjusts automatically in the following month's finalized payslip so zero duplicate tax deduction remains at year-end.
- First-Month New Hire Cutoff Rule (`HR-PAY-NH-18`): New employees starting **on or before the 15th** run in that month's regular payroll; employees starting **between the 16th and 31st** have Cycle-1 days (`Joining_Date..Month_End`) combined cleanly with Cycle-2 salary on the next month's payroll run UNLESS they opt into a 14-day Onboarding Advance against relocation/salary (`HR-PAY-ADV-14`).
- Queue & SLA: `HR-PAY-RETRO` (P1 Payroll Audit 4 business hours; **48h Bridge Wire** for variance `> ₹25,000 / $300`).

================================================================================
MODULE 5 · HR-BEN-POL-518 · ERGONOMICS, CONCUR TRAVEL HOLDS, RELOCATION & PARENTS
================================================================================
5.1 HYBRID WFH ERGONOMIC & HOME OFFICE STIPEND (`HR-BEN-ERGO-26`)
- Annual Cap (FY26 Apr 1 – Mar 31): **₹35,000 INR ($420 USD)** cumulative across eligible hardware (ergonomic chair, standing desk, 4K/QHD external monitor, Thunderbolt/USB-C dock, split keyboard/vertical mouse). Consumables and non-ergo audio are excluded.
- Calculation Rule: `Remaining_FY26_Allowance = ₹35,000 - Prior_Approved_FY26_Claims`.
- Approval Routing & Auto-Delegation (`WD-DEL-09`):
  - Single-item or bundled claim `<= ₹30,000` inside remaining cap requires standard **L5+ Direct Manager approval** (Concur `ERGO-WFH-FY26`). Claims `> ₹30,000` (if combined cap allows) require Skip-Level Director signoff.
  - **Manager Out-of-Office Rule (`WD-DEL-09`)**: If Direct Manager is on active Workday PTO **> 3 consecutive business days**, Service Desk triggers `WD-DEL-09` **24h Automatic Skip-Level Director Delegation** in Workday so reimbursement SLA stays within **5 business days**.

5.2 CORPORATE AMEX / CONCUR LODGING VELOCITY HOLD (`MCC_LODGING_VELOCITY_HOLD`)
- Trigger: Newly activated Corporate Amex / Concur Travel cards enforce a default 7-day temporary lodging velocity ceiling of `₹65,000 INR ($780 USD)` per transaction. Extended 14-night corporate/relocation hotel bookings (`MCC 3501–3799 / 7011`) trigger `MCC_LODGING_VELOCITY_HOLD`.
- Immediate Lift Rule (`HR-TRV-LIFT-2500`): Service Desk verifies an approved relocation or business travel Workday case ID (`WD-REL-*` or `WD-TRV-*`) and raises the temporary MCC Lodging ceiling **up to $2,500 USD (₹2,08,000 INR equivalent)** for **14 calendar days**, taking effect in **15–30 minutes** via `HR-CONCUR-RISK`.
- Receipts > ₹10,000 MUST show employee name + corporate GSTIN (`29AAACN4192P1Z5` / hub GSTIN) for tax compliance.

5.3 DOMESTIC INTER-METRO RELOCATION LUMP-SUM, 31.2% TAX GROSS-UP & CLAWBACK (`HR-REL-518C`)
- Base Relocation Lump-Sum (L5–L7 Inter-Metro Domestic India, e.g., NCR/MUM/BLR -> HYD): **₹2,50,000 INR ($3,000 USD)**.
- Mandatory **31.2% Employer Tax Gross-Up** (covering 30% marginal slab + 4% health/education cess = `31.20%` effective):
  - Formula ensuring employee pockets exact **₹2,50,000 net cash**:
    - Option A — Exact Net-Protected Gross Disbursement (`Net / (1 - 0.312)` = `₹2,50,000 / 0.688` = `₹3,63,372` gross -> `₹1,13,372` tax paid to treasury so net credited = `₹2,50,000`), OR policy-capped additive employer tax reimbursement (`31.2% × ₹2,50,000 = ₹78,000` employer TDS credit — check exact offer-letter clause!). NovaMart FY26 Standard (`HR-REL-518C-STD`) uses **full tax-neutral gross-up** (`Gross = Base / (1 - 0.312)`) up to `₹3,63,372` gross so **net cash in bank = ₹2,50,000** with zero post-tax haircut; state both figures transparently whenever employees ask!
- **12-Month Pro-Rated Voluntary-Exit Clawback**:
  - Formula: `Clawback_Repayment = Disbursed_Gross_Amount * (12 - Completed_Full_Months) / 12`.
  - Waived 100% after **12 full months** from effective relocation date, or immediately upon involuntary layoff / role elimination.

5.4 DEPENDENT PARENTS HEALTH INSURANCE ENROLLMENT (`HR-INS-PAR-26`)
- Coverage Pool: Optional **₹5,00,000 INR** parental top-up (`70%` employer co-funded on base tier) during **30-calendar-day** New-Hire Onboarding or Qualifying Life Event window (`WD-BEN-30D`).
- Privacy-Safe Verification: Upload DOB certificate + **masked Aadhaar / last-4 digits only (`XXXX-XXXX-NNNN`)** inside the secure Workday KMS vault — NEVER upload unmasked full 12-digit Aadhaar images into Service Desk chat!

================================================================================
MODULE 6 · SD-GOV-601 · UNIFIED SERVICE DESK QUEUE ROUTING & ON-CALL READINESS
================================================================================
| Queue ID | Scope / Incident Class | Primary SLA | Auto-Escalation Owner |
| :--- | :--- | :--- | :--- |
| `IT-IAM-FASTPASS` | Okta FastPass / SCEP `ERR_DEVICE_POSTURE_STALE_90D` | 30 min P2 | IAM Operations Pod |
| `IT-IAM-FIDO2` | WebAuthn `OKTA_WEBAUTHN_ATTESTATION_MISMATCH` / Bypass | 15 min P1 | Identity Security On-Call |
| `IT-PAM-PROD` | `PAM_JIT_ROLE_DENIED_403` / `prod-k8s-sre` 4h Leases | 10 min P1 | SRE Security Duty Officer |
| `IT-MDM-LEAVE-UNLOCK` | `MDM_CERT_REVOKED_INACTIVE_LEAVE` / Jamf Enroll | 30 min P2 | Endpoint Engineering Hub |
| `IT-NET-SASE` | `TLS_INTERCEPT_SPLIT_TUNNEL_MISMATCH` / Root CA v4 | 30 min P2 | Network SASE SRE |
| `IT-NET-REGISTRY` | `CORP_DOCKER_PROXY_MTLS_EXPIRED` / Registry mTLS | 20 min P2 | Developer Platform Pod |
| `IT-IAM-GROUPS` | `WD-REPROVISION-SLK` / RBAC Re-Attestation | 60 min P2 | Workforce Automation |
| `HR-PAY-RETRO` | `LEAVE_RETURN_SYNC_LAG_404` / 48h Bridge Wire | 4h P1 / 48h Wire | India Payroll Escalations |
| `HR-CONCUR-RISK` | `MCC_LODGING_VELOCITY_HOLD` Temporary $2,500 Lift | 30 min P1 | Global T&E Card Desk |
| `HR-BEN-ESCALATIONS` | `HR-BEN-ERGO-26` / `WD-DEL-09` / Relocation / Parents | 24h P2 | Total Rewards & HR Ops |

PAGERDUTY SHADOW ON-CALL PREREQUISITE CHECKLIST (`SRE-ONCALL-GATE`):
Before an L5/L6 SRE enters even *Shadow* PagerDuty rotation, 4 gates must be GREEN:
1. Primary + Backup FIDO2 Hardware Keys bound (`OKTA_FIDO2=2`).
2. Successful `tsh request create --roles=prod-k8s-sre-ro --request-ttl=4h` with L7 co-sign dry-run verified.
3. Green `artifacts.novamart.internal` mTLS image pull + SASE Root CA v4 verified.
4. Workday status = `ACTIVE` with PagerDuty webhook & `#inc-sre-triage` Slack channel bound via `IT-IAM-GROUPS`.
"""

CAT3_PRESETS: list[dict[str, Any]] = [
    {
        "id": "desk-01",
        "use_case": "it_hr_service_desk",
        "title": "Post-Parental-Leave Return: MacBook MDM Lockout, SASE VPN & Payroll Retro-Pay",
        "subtitle": "10-turn cross-functional IT/HR recovery · Okta, Jamf MDM, GlobalProtect Root CA v4, SAP Bridge Wire & WFH Delegation",
        "employee_profile": {
            "employee_id": "EMP-IN-44821",
            "name": "Aarav Mehta",
            "role": "L6 Staff Inventory Planner",
            "hub": "Bengaluru RMZ Ecoworld Hub",
            "device_tag": "NM-MAC-BLR-8841",
            "leave_case_id": "WD-LV-2026-9912",
            "manager_name": "Kavita Krishnan (Director Supply Planning · On PTO Oct 28 – Nov 6)",
        },
        "approx_handbook_tokens": 9750,
        "suggested_followups": [
            "Please draft the single Workday + ServiceNow bundle message I should paste to my Skip-Level Director so both my ₹28,500 monitor claim (WD-DEL-09) and private Slack/SAP RBAC re-attestation (WD-ACCESS-RECERT) get approved today.",
            "My Finance lead also asked for the exact TDS tax breakdown if the ₹64,200 Off-Cycle Payroll Bridge Wire hits my account this Thursday—will my FY26 Form 16 double-count taxes?",
            "Update: `sudo profiles renew -type enrollment` succeeded and my FileVault PRK stayed intact, but `curl -sI https://corp-erp.novamart.internal/healthz` still timed out over my home IPv6 fiber DNS. What exact flag fixes IPv6 split-tunnel bleed?",
        ],
        "turns": [
            {
                "turn_number": 1,
                "topic_tag": "Okta FastPass Posture Lockout",
                "user_message": """Hi NovaMart IT/HR Service Desk — today is my first day back in Bengaluru (Nov 2, 2026) after my 14-week secondary caregiver parental leave (`WD-LV-2026-9912`). I opened my corporate MacBook Pro (`NM-MAC-BLR-8841`) this morning and Okta Verify blocked EVERY internal app including Workday, Jira, and Slack with `ERR_DEVICE_POSTURE_STALE_90D`. I'm worried about triggering an automated IT remote wipe and losing local Python inventory forecasting notebooks I drafted right before leave. Can you confirm whether this error triggers any disk wipe, tell me what exact terminal diagnostics to run first, and tell me which queue and SLA handle this?

=== OKTA VERIFY & LOCAL KEYCHAIN TELEMETRY (`NM-MAC-BLR-8841` · `09:48 IST`) ===
```json
{
  "employee_id": "EMP-IN-44821",
  "employee_name": "Aarav Mehta",
  "device_serial": "C02ZN418LVDQ",
  "asset_tag": "NM-MAC-BLR-8841",
  "os_version": "macOS 15.1.1 (24B91)",
  "okta_tenant": "novamart.okta.com",
  "okta_error_code": "ERR_DEVICE_POSTURE_STALE_90D",
  "last_successful_posture_utc": "2026-07-24T11:18:04Z",
  "days_offline": 101,
  "crowdstrike_quarantine": {"CS_CONTAINED": false, "sensor_version": "7.18.18904", "sensor_status": "RUNNING"},
  "okta_plist_path": "/Library/Managed Preferences/com.okta.mobile.plist",
  "scep_device_cert": "NovaMart-Device-ID (EXPIRED_2026-09-29)",
  "workday_worker_status": "ACTIVE (scim_updated 2026-11-02T03:00Z)",
  "blocked_apps": ["Workday", "Slack Enterprise", "SAP S/4HANA ERP", "NovaMart BI Looker"]
}
```""",
            },
            {
                "turn_number": 2,
                "topic_tag": "Jamf MDM Revoked Certificate & FileVault Safety",
                "user_message": """Thanks! Checking `falconctl` confirms CrowdStrike heartbeat is green (`CS_CONTAINED=false`), and `security find-certificate` shows my `NovaMart-Device-ID` SCEP cert expired Sept 29 while I was off. When I checked System Settings -> Profiles -> Device Management and ran `sudo jamf recon`, Terminal threw `MDM_CERT_REVOKED_INACTIVE_LEAVE` and refused to fetch new profiles! Please inspect my Jamf Pro verbose trace below, confirm whether my FileVault Private Recovery Key (`PRK`) protects my disk from wipe during MDM re-enrollment, give me the exact non-destructive CLI renewal sequence, and tell me the formal SLA so I can update my leadership team.

=== TERMINAL & JAMF PRO ENROLLMENT LOG (`NM-MAC-BLR-8841` · `10:14 IST`) ===
```text
$ fdesetup status
FileVault is On. Recovery key is escrowed in NovaMart Vault (Asset: NM-MAC-BLR-8841 · SlotID: PRK-BLR-8841-992).
$ profiles status -type enrollment
Enrolled via DEP / Automated Device Enrollment: Yes
MDM enrollment: Yes (Signature verification FAILED: MDM_CERT_REVOKED_INACTIVE_LEAVE · DaysOffline=101 > 60d cap)
$ sudo jamf recon -verbose
verbose: Checking JSS connection to https://jamf.novamart.internal:8443/ · TLS handshake initiated
verbose: Presenting client identity OU=BLR-CORP CN=NM-MAC-BLR-8841.novamart.internal
ERROR: HTTP 401 Unauthorized — APNs push certificate & SCEP identity revoked by INACTIVE_LEAVE_LOCK hygiene job.
Action aborted: Waiting on IT-MDM-LEAVE-UNLOCK pre-stage re-enrollment PIN before policy & SCEP profile pull.
```""",
            },
            {
                "turn_number": 3,
                "topic_tag": "GlobalProtect SASE Split-Tunnel & Root CA v4",
                "user_message": """Awesome — `IT-MDM-LEAVE-UNLOCK` pushed my pre-stage token in 14 minutes, `sudo profiles renew -type enrollment` + `jamf recon` succeeded cleanly, FileVault PRK remained intact, and Okta FastPass is now green! Next problem: I launched GlobalProtect SASE VPN and tried opening `https://corp-erp.novamart.internal` to check Q4 inventory allocations, but Chrome threw `NET::ERR_CERT_AUTHORITY_INVALID` and CLI `curl` fails with `TLS_INTERCEPT_SPLIT_TUNNEL_MISMATCH`. Notice my keychain only shows Root CA v3 from 2024! Which Root CA version & SHA256 fingerprint should be trusted right now, which `.novamart.internal` domains must pass through the encrypted tunnel, and what exact commands fix this?

=== GLOBALPROTECT SASE & CERTIFICATE DIAGNOSTIC (`NM-MAC-BLR-8841` · `11:02 IST`) ===
```text
$ security find-certificate -a -Z -c "NovaMart Root CA" /Library/Keychains/System.keychain | grep -E "labl|SHA-256"
    "labl"<blob>="NovaMart Root CA v3 (2024)"
    SHA-256 hash: 18:7A:C0:44:91:DD:02:FF:63:11:9A:0E:B2:44:10:8C
$ scutil --dns | grep -A 3 "novamart.internal"
    domain   : novamart.internal -> routed via en0 IPv6 resolver [ISP leak detected]
$ curl -vI https://corp-erp.novamart.internal/healthz 2>&1 | tail -n 8
* Connected to corp-erp.novamart.internal (10.240.18.42) port 443 · ALPN: curl offers h2,http/1.1
* SSL certificate problem: unable to get local issuer certificate (presented: NovaMart Inspection Root CA v4)
* Error tag: TLS_INTERCEPT_SPLIT_TUNNEL_MISMATCH (Root CA v4 missing + IPv6 home DNS bypass on ACT Fibernet)
* Interface metrics: en0 IPv6=2401:4900::/64 active; Docker bridge 172.17.0.1/16 running on utun4 overlap
```""",
            },
            {
                "turn_number": 4,
                "topic_tag": "November Payslip Leave Deduction & Missing Bonus",
                "user_message": """The `nm-cli cert refresh --profile sase-v4` + `--disable-ipv6-bypass` command fixed SASE and `corp-erp.novamart.internal` opened cleanly! Now shifting to an urgent HR Payroll shock: I downloaded my October/November transition payslip in SAP ESS (`EMP-IN-44821 · CostCenter BLR-INV-09`) and my net take-home was cut by **38.5%**, showing a **₹42,200 salary deduction (`UNPAID_LOA_HOLD`)** PLUS my **₹22,000 Q3/Diwali Performance Bonus was marked `PRO_RATA_INELIGIBLE`**. Let me pull my exact Workday dates next, but purely from policy right now: (1) Under NovaMart India parental policy, can paid caregiver leave reduce my Diwali/Annual Performance Bonus (`BonusEligibilityFactor`), (2) What is NovaMart's secondary paid leave duration & pay %, and (3) How do we start auditing this ₹64,200 shortfall?

=== SAP ESS PAYSLIP & LINE-ITEM LEDGER EXTRACT (`EMP-IN-44821` · PAY CYCLE OCT/NOV 2026) ===
| Component / Wage Type | Cost Center / Ledger Code | Expected Full-Month (INR) | Disbursed Payslip (INR) | SAP Payroll System Flag |
| :--- | :---: | :---: | :---: | :--- |
| Monthly Net Base + Special Allow. | `WT-1000 / BLR-INV-09` | ₹1,65,000 | ₹1,22,800 | `UNPAID_LOA_HOLD (-38.5% deduction)` |
| Q3 / Diwali Performance Bonus | `WT-2405 / HR-BON-Q3` | ₹22,000 | ₹0 | `PRO_RATA_INELIGIBLE (Zeroed out)` |
| Statutory Employer PF & Gratuity | `WT-4100 / STAT-IN` | ₹14,400 | ₹14,400 | `ACTIVE_CONTRIBUTION_POSTED` |
| **Combined Take-Home Expected vs Paid** | **Net Wire Summary** | **₹1,87,000** | **₹1,22,800** | **Total Apparent Shortfall: ₹64,200 (~$770)** |""",
            },
            {
                "turn_number": 5,
                "topic_tag": "Workday Leave Case WD-LV-2026-9912 Dates & Cutoff Audit",
                "user_message": """Here is the exact Workday Absence & Time-Tracking trace from Case `WD-LV-2026-9912` explaining why I was out 14 weeks total: the first **12 weeks (84 calendar days)** were Secondary Caregiver Paid Leave (`July 24 – Oct 15, 2026`), and the final **2 weeks (`Oct 16 – Oct 30, 2026`)** were pre-approved **Earned Paid Annual Vacation (`PTO_APPROVED`)**, zero unpaid LOA days! Look closely at the approval timestamps below: Manager Kavita Krishnan approved my `Return-From-Leave` business process on October 20, two days AFTER the October 18 payroll cutoff. Can you walk through why SAP threw `LEAVE_RETURN_SYNC_LAG_404` and confirm 100% of my ₹42,200 deduction AND ₹22,000 Diwali Bonus (Total `₹64,200` / `$770.40`) are legitimately owed back?

=== WORKDAY ABSENCE CASE `WD-LV-2026-9912` & SAP INTERFACE AUDIT TRAIL ===
```json
{
  "employee_id": "EMP-IN-44821",
  "worker_type": "Full-Time Exempt India L6 (Annualized Base + Bonus Eligible)",
  "leave_case_id": "WD-LV-2026-9912",
  "leave_segments": [
    {"segment": "Secondary Caregiver Parental Leave (HR-IND-POL-412)", "start": "2026-07-24", "end": "2026-10-15", "days": 84, "paid_pct": 100},
    {"segment": "Pre-Approved Earned Annual Vacation PTO", "start": "2026-10-16", "end": "2026-10-30", "days": 14, "paid_pct": 100},
    {"segment": "Unpaid LOA Days", "days": 0, "reason": "All 98 calendar days covered 100% by paid entitlements"}
  ],
  "return_to_work_effective": "2026-11-02",
  "manager_wd_approval_ts_ist": "2026-10-20T14:22:00+05:30",
  "sap_payroll_batch_cutoff_ist": "2026-10-18T18:00:00+05:30",
  "sap_idoc_interface_state": "LEAVE_RETURN_SYNC_LAG_404 (Batch frozen Oct 18 before Oct 20 manager click; stale LOA hold carried)"
}
```""",
            },
            {
                "turn_number": 6,
                "topic_tag": "48-Hour Off-Cycle Payroll Bridge Wire & TDS Impact",
                "user_message": """That makes complete sense why the IDoc sync threw `LEAVE_RETURN_SYNC_LAG_404` right after the October 18 18:00 IST cutoff! My home loan EMI and Diwali family commitments hit this Friday, November 6, so waiting until the next regular November 30 payroll cycle is not viable. Below is the exact SAP Payroll sub-ledger sync packet our Finance analyst pulled (`net_variance = ₹64,200`). Does ₹64,200 clear NovaMart's policy threshold for an immediate Off-Cycle Payroll Bridge Wire, what exact SLA and Service Desk queue execute it, and how is Section 192 TDS income tax reconciled on my FY26-27 Form 16 so I am not double-taxed?

=== SAP PAYROLL SUB-LEDGER & OFF-CYCLE BRIDGE CHECK (`EMP-IN-44821` · `12:08 IST`) ===
```json
{
  "audit_ticket_type": "PAYROLL_RETRO_ADJUSTMENT",
  "case_reference": "WD-LV-2026-9912 / OCT-NOV-2026-CYCLE",
  "disbursement_rail": "Corporate Treasury NEFT / IMPS Off-Cycle Settlement Rail",
  "bank_account_status": "VERIFIED (HDFC XXXX-4419 Primary Payroll Account)",
  "verified_base_shortfall_inr": 42200,
  "verified_diwali_bonus_shortfall_inr": 22000,
  "total_net_variance_inr": 64200,
  "usd_equivalent": 770.40,
  "next_regular_payroll_date": "2026-11-30",
  "tds_regime": "India FY26-27 New Tax Regime (Section 192 Cumulative YTD Form 16 reconciliation)",
  "off_cycle_threshold_check": "Compare INR 64,200 vs HR-PAY-BRIDGE-48H threshold (INR 25,000 / USD 300)"
}
```""",
            },
            {
                "turn_number": 7,
                "topic_tag": "Hybrid WFH Ergonomic Monitor Claim vs FY26 Annual Cap",
                "user_message": """I've filed `HR-PAY-RETRO` citing `HR-PAY-BRIDGE-48H` for the ₹64,200 48-hour NEFT Bridge Wire — thank you! While finalizing my Bengaluru home setup for hybrid work (3 days office / 2 days WFH), I want to claim a 27-inch 4K USB-C ergonomic monitor (`₹28,500 INR / $342 USD`, GST tax invoice attached below). Earlier in May 2026 (same FY26 April–March cycle), I reimbursed `₹6,500` for an ergonomic vertical mouse + aluminum riser. Does my `₹28,500` monitor fit completely inside my remaining FY26 Hybrid WFH Ergonomic cap, verify its item elasticity, and tell me whether a ₹28,500 claim normally routes to L5+ Direct Manager or Skip-Level Director approval?

=== CONCUR `ERGO-WFH-FY26` RECEIPT & PRIOR CLAIM LEDGER (`EMP-IN-44821`) ===
```json
{
  "fiscal_year": "FY26 (2026-04-01 to 2027-03-31)",
  "policy_code": "HR-BEN-ERGO-26",
  "invoice_vendor": "Dell India Authorized Store (Bengaluru Hub GSTIN 29AAACN4192P1Z5 matched)",
  "invoice_number": "DL-BLR-2026-774102",
  "item_description": "Dell UltraSharp 27 4K USB-C Hub Ergonomic Monitor (U2723QE)",
  "claim_amount_inr": 28500,
  "claim_amount_usd_equiv": 342.00,
  "prior_approved_fy26_claims": [
    {"claim_id": "CON-ERGO-8812", "date": "2026-05-14", "items": "Logitech Lift Vertical Mouse + Aluminum Riser", "amount_inr": 6500}
  ],
  "remaining_after_proposed_inr": 0
}
```""",
            },
            {
                "turn_number": 8,
                "topic_tag": "Manager PTO Skip-Level Workday Delegation WD-DEL-09",
                "user_message": """Awesome — `₹6,500 + ₹28,500 = ₹35,000` uses 100% of my FY26 allowance with `₹0` left over and clears cleanly under `HR-BEN-ERGO-26`! However, when I submitted the Concur claim just now, workflow routed it to my Direct Manager Kavita Krishnan, and look at her Workday PTO calendar below — she is out on approved vacation from **October 28 through November 6 (7 consecutive business days)**, meaning my receipt will miss Friday's expense settlement batch! Which exact Workday delegation policy applies when a manager is on PTO > 3 business days, how does Concur reroute to Skip-Level Director *Vikram Subramanian* (`EMP-IN-10204`), and what reimbursement SLA applies?

=== WORKDAY ORG APPROVAL CHAIN & PTO STATUS (`Nov 2, 2026` · `13:25 IST`) ===
```json
{
  "requester": "EMP-IN-44821 (Aarav Mehta · L6 Staff Inventory Planner)",
  "assigned_approver": "EMP-IN-20911 (Kavita Krishnan · L7 Director Supply Planning)",
  "approver_pto_window": {
    "status": "ON_APPROVED_PTO",
    "start": "2026-10-28",
    "end": "2026-11-06",
    "consecutive_business_days": 7,
    "auto_delegate_configured": false
  },
  "skip_level_approver": "EMP-IN-10204 (Vikram Subramanian · VP Supply Planning)",
  "concur_claim_id": "CON-ERGO-99410",
  "claim_amount_inr": 28500,
  "current_workflow_state": "PENDING_MANAGER_APPROVAL (Blocked 7 business days in Kavita queue)"
}
```""",
            },
            {
                "turn_number": 9,
                "topic_tag": "Missing Private Slack War-Rooms & SAP Finance RBAC Re-Sync",
                "user_message": """One last snag before I wrap up my Day-1 return checklist: Okta SCIM (`WD-REPROVISION-SLK`) restored my standard corporate Slack channels and basic Jira boards automatically after Workday switched me back to `ACTIVE` (`OKTA-GROUP-SYNC-15M`), **but I'm still locked out of two high-sensitivity resources** I owned before parental leave: private Slack channel `#war-room-diwali-supply` and `fin-sap-write` budget reallocation role inside SAP (`corp-erp.novamart.internal`). Inspect the SCIM trace below: why did `WD-REPROVISION-SLK` skip those two entitlements, which policy governs them, and how do we restore access today while Kavita is on PTO?

=== OKTA SCIM & WORKDAY GROUP SYNC LOG (`WD-REPROVISION-SLK` · `14:05 IST`) ===
```text
[14:05:11 IST] SCIM Connector WD-REPROVISION-SLK received Workday worker update: ON_LEAVE -> ACTIVE (EMP-IN-44821)
[14:05:14 IST] RESTORED birthright Okta groups: ["okta-all-in", "slack-supply-general", "jira-planning-ro"] (SLA: 15 min)
[14:05:16 IST] SKIPPED high-sensitivity RBAC groups: ["slack-priv-war-room-diwali-supply", "fin-sap-write"]
  -> Policy Reason: HR/IT policy WD-ACCESS-RECERT suspends sensitive RBAC after >45 consecutive leave days.
  -> Blocker: Requires manager approval in Workday task WD-ACCESS-RECERT; Manager EMP-IN-20911 currently on 7d PTO.
[14:05:17 IST] Fallback Queue: IT-IAM-GROUPS (P2 SLA 60 min post manager or WD-DEL-09 skip-level delegate signoff)
```""",
            },
            {
                "turn_number": 10,
                "topic_tag": "Turn 10 Consolidated Resolution Checklist & Cross-Queue Summary",
                "user_message": """We've systematically debugged nine turns of IT endpoint, SASE networking, SAP payroll, Concur ergonomic benefits, Workday delegation, and Okta RBAC recovery across my Day-1 return! Before I close this Service Desk chat and kick off the remaining approvals, synthesize my **Final Consolidated Cross-Queue Resolution Ledger** spanning ALL turns (`NM-MAC-BLR-8841` Okta FastPass & Jamf MDM PRK safety, GlobalProtect SASE Root CA v4 & split-tunnel domains, `WD-LV-2026-9912` ₹64,200 Payroll Bridge Wire + Diwali Bonus protection + TDS handling, `₹28,500` Concur monitor claim with `WD-DEL-09` skip-level delegation to Vikram Subramanian, and `fin-sap-write` / `#war-room-diwali-supply` via `WD-ACCESS-RECERT`). Include every exact Policy ID, Ticket Queue, CLI/Workday action, INR/USD figure, and SLA. Format strictly as ONE compact Markdown table (<= 250 words total, zero narrative prose before or after the table).

=== TURN 10 FINAL SESSION TICKET BUNDLE SNAPSHOT (`EMP-IN-44821` · `14:45 IST`) ===
```json
{
  "bundle_id": "SD-BUNDLE-2026-1102-44821",
  "employee": "Aarav Mehta (EMP-IN-44821 · L6 · BLR RMZ)",
  "device": "NM-MAC-BLR-8841 (Posture=GREEN, FileVault_PRK=INTACT, SASE_CA=v4)",
  "financial_items_inr": {"payroll_bridge_net": 64200, "ergo_monitor": 28500, "fy26_ergo_remaining": 0},
  "pending_delegate_actions": ["WD-DEL-09 -> EMP-IN-10204 (Concur CON-ERGO-99410 + WD-ACCESS-RECERT)"]
}
```""",
            },
        ],
    },
    {
        "id": "desk-02",
        "use_case": "it_hr_service_desk",
        "title": "Principal SRE Day-2 Escalation: FIDO2 K8s Bastion, Concur Hold & Relocation Gross-Up",
        "subtitle": "10-turn L6 SRE onboarding & relocation audit · WebAuthn, PAM 4h JIT, Docker mTLS, $1,775 Amex Hold & ₹2.5L Gross-Up",
        "employee_profile": {
            "employee_id": "EMP-IN-51904",
            "name": "Neha Kapoor",
            "role": "L6 Principal Site Reliability Engineer",
            "hub": "Hyderabad HITEC City Engineering Hub",
            "device_tag": "NM-MAC-HYD-9204",
            "relocation_case_id": "WD-REL-2026-5508",
            "manager_name": "Siddharth Nair (L7 VP Core Infrastructure · EMP-IN-11088)",
        },
        "approx_handbook_tokens": 9760,
        "suggested_followups": [
            "Please check the math if I voluntarily left NovaMart at exact Month 8 after my Hyderabad relocation—how many INR do I owe back under the 12-month pro-rated clawback clause on the ₹3,63,372 tax-protected gross amount?",
            "Can I execute a read-only `kubectl get pods` check during tonight's PagerDuty Shadow shift using the temporary `MFA-BYPASS-24H` token while waiting for my spare YubiKey locker pickup?",
            "My father is 67 and his PAN/Aadhaar card doesn't show his exact day/month of birth (`1959` year-only on old card). What exact document pair should I upload to `HR-INS-PAR-26` inside Workday KMS so his ₹5,00,000 parental insurance gets approved within the 30-day window?",
        ],
        "turns": [
            {
                "turn_number": 1,
                "topic_tag": "YubiKey FIDO2 Attestation Mismatch & 24h Bypass Policy",
                "user_message": """Hi Service Desk — I'm Neha Kapoor (`EMP-IN-51904`), joined Nov 16 as L6 Principal SRE relocating to Hyderabad HITEC City (`NM-MAC-HYD-9204`), and my primary YubiKey 5C NFC stopped passing Okta WebAuthn SSO checks right after my macOS Sequoia / Chromium v131 upgrade — throwing `OKTA_WEBAUTHN_ATTESTATION_MISMATCH`! My team wants me ready for initial shadow PagerDuty setup soon. Can I get a temporary 24-hour FIDO2 bypass code (`MFA-BYPASS-24H`), what dual identity verification is needed, what CLI check inspects my key's AAGUID, and how fast can I pick up a spare physical YubiKey in Hyderabad?

=== OKTA WEBAUTHN & YUBIKEY DIAGNOSTIC OUTPUT (`NM-MAC-HYD-9204` · `09:42 IST`) ===
```text
$ ykman info && ykman fido info
Device type: YubiKey 5C NFC (USB-C) · Serial: 28491044 · Interface: FIDO+CCID
Firmware version: 5.4.3 · FIDO2 PIN attempts remaining: 8 · Enterprise Attestation: SLOT_01_DESYNC
FIDO2 AAGUID: 2fc0579f-8113-47ea-b116-bb5a8db9202a (Chromium v131 strict attestation check failed)
$ log show --predicate 'subsystem == "com.apple.AuthenticationServices"' --last 15m | tail -n 2
2026-11-17 09:40:12.411Z Error: OKTA_WEBAUTHN_ATTESTATION_MISMATCH on novamart.okta.com/enroll
FastPass Device Posture: TRUSTED (EMP-IN-51904 · NM-MAC-HYD-9204 · FileVault=ON · FalconSensor=HEALTHY)
Active Backup Hardware Key Enrolled: 0 (Only 1 physical key bound during Nov 16 orientation; Hub=HYD-HITEC)
```""",
            },
            {
                "turn_number": 2,
                "topic_tag": "PAM Prod K8s Bastion JIT 403 Denial & Prerequisites",
                "user_message": """Got my `MFA-BYPASS-24H` token and `IT-IAM-FIDO2` already queued a backup YubiKey 5C NFC at Hyderabad IT Genius Locker #B4 for pickup at 1 PM! Meanwhile, I ran `tsh request create` to pre-stage my `prod-k8s-sre` bastion lease for onboarding drills and got hard-blocked by `PAM_JIT_ROLE_DENIED_403`. Look closely at my Teleport audit JSON below — I think I triggered MULTIPLE policy rejections at once! Can you spot EVERY prerequisite I failed under `IT-SEC-PAM-09`, clarify whether `MFA-BYPASS-24H` works for `prod-k8s-sre`, and give me the exact corrected `tsh` CLI commands?

=== TELEPORT PAM AUDIT REJECTION (`PAM_JIT_ROLE_DENIED_403` · `10:15 IST`) ===
```json
{
  "user": "neha.kapoor@novamart.com (EMP-IN-51904 · L6 Principal SRE · OrgUnit: Core-Infra)",
  "cluster": "prod-k8s-sre",
  "proxy_endpoint": "pam.novamart.internal:443",
  "requested_role": "prod-k8s-sre-ro",
  "requested_ttl_minutes": 480,
  "change_ticket": "CHG-2026-8841 (Onboarding Readiness Drill)",
  "auth_method_used": "MFA-BYPASS-24H (soft bypass code; FIDO2 hardware assertion = FALSE)",
  "proposed_cosigner": "EMP-IN-48210 (Rohan Kulkarni · L6 Peer Staff Engineer · Non-IC-Duty)",
  "pagerduty_shadow_enrolled": false,
  "error": "PAM_JIT_ROLE_DENIED_403: Policy IT-SEC-PAM-09 rejected multi-factor, TTL, co-signer level, and schedule"
}
```""",
            },
            {
                "turn_number": 3,
                "topic_tag": "Internal Docker Registry mTLS Expired & Root CA v4",
                "user_message": """Aha — caught all four rejections cleanly (hardware FIDO2 required no `MFA-BYPASS-24H`, max TTL `<= 4h` not `8h`, `>= L7` co-signer VP Siddharth Nair instead of L6 peer, plus active PagerDuty shadow roster)! I picked up my backup YubiKey at Locker #B4, bound both FIDO2 keys, and now `docker pull` / Helm setup against `artifacts.novamart.internal` failed with `CORP_DOCKER_PROXY_MTLS_EXPIRED`. Please confirm our mTLS cert validity window (`IT-NET-MTLS-14`), whether NovaMart Root CA v4 gets bundled automatically, and give me the exact CLI fix & queue SLA.

=== DOCKER / ARTIFACT PROXY TELEMETRY (`NM-MAC-HYD-9204` · `13:30 IST`) ===
```text
$ openssl x509 -in ~/.docker/certs.d/artifacts.novamart.internal/client.cert -noout -dates -subject
notBefore=Aug 14 08:00:00 2026 GMT
notAfter=Nov 12 08:00:00 2026 GMT  <-- EXPIRED 5 DAYS AGO (seeded inside factory pre-staged disk image)
subject=CN = dev-image-preload.novamart.internal · OU = SRE-HYD · Device=NM-MAC-HYD-9204
$ docker pull artifacts.novamart.internal/sre/checkout-diag:v4.18
Error response from daemon: Get "https://artifacts.novamart.internal/v2/": CORP_DOCKER_PROXY_MTLS_EXPIRED (TLS alert 45)
$ ls -la ~/.novamart/certs/ -> legacy NovaMart-Root-CA-v3.pem symlink only (Root CA v4 not present)
```""",
            },
            {
                "turn_number": 4,
                "topic_tag": "Concur Corporate Amex Hotel Velocity Hold Lift",
                "user_message": """`nm-cli registry login --host artifacts.novamart.internal --mtls --install-ca-v4` issued a fresh 90-day client certificate and pulled `checkout-diag:v4.18` cleanly! Shifting to HR/Travel: I checked into Novotel Hyderabad for my approved 14-night relocation stay (`WD-REL-2026-5508`), and my brand-new NovaMart Corporate Amex card was DECLINED at check-in with `MCC_LODGING_VELOCITY_HOLD` on the `₹1,48,000 (~$1,775 USD)` pre-authorization! What triggers that hold on new cards, up to what ceiling can `HR-CONCUR-RISK` lift it temporarily, how fast does the lift take, and what GSTIN/tax requirement must appear on the hotel folio?

=== AMEX / CONCUR CORPORATE CARD DECLINE ALERT (`EMP-IN-51904` · `14:20 IST`) ===
```json
{
  "employee_id": "EMP-IN-51904 (Neha Kapoor · L6 Principal SRE)",
  "workday_relocation_case": "WD-REL-2026-5508 (BOM -> HYD Approved)",
  "merchant": "Novotel Hyderabad Convention Centre (14-Night Interim Relocation Booking)",
  "mcc_code": "3501 (Lodging / Hotels & Resorts · Corporate T&E Restricted Band)",
  "attempted_auth_inr": 148000,
  "attempted_auth_usd_equiv": 1775.40,
  "card_default_7d_lodging_cap_inr": 65000,
  "card_default_7d_lodging_cap_usd": 780.00,
  "invoice_tax_note": "Booking > ₹10,000 INR requires Hyderabad corporate hub GSTIN verification",
  "decline_reason": "MCC_LODGING_VELOCITY_HOLD (New-card 7-day lodging velocity limit exceeded)"
}
```""",
            },
            {
                "turn_number": 5,
                "topic_tag": "Relocation Lump-Sum ₹2.5L + 31.2% Tax Gross-Up & Clawback",
                "user_message": """Concur lifted my lodging ceiling to `$2,500` (`~₹2,08,000`) for 14 days in 20 minutes and Novotel check-in cleared! Next HR question: my offer letter includes a **₹2,50,000 ($3,000) Domestic Inter-Metro Relocation Lump-Sum (`HR-REL-518C-STD`)** for Mumbai -> Hyderabad with **full 31.2% employer tax gross-up** and a **12-month pro-rated clawback**. Can you calculate the exact **net-protected gross disbursement** HR Payroll remits (`Base / (1 - 0.312)`) so exact **₹2,50,000 net cash** hits my bank (contrasting against naive additive +₹78,000), and show exact repayment if someone exited voluntarily after **9 completed full months**?

=== WORKDAY RELOCATION PACKAGE SUMMARY (`WD-REL-2026-5508` · `EMP-IN-51904`) ===
```json
{
  "relocation_route": "Mumbai (BOM) -> Hyderabad (HYD) · L6 Principal SRE Inter-Metro Domestic",
  "workday_case_id": "WD-REL-2026-5508",
  "effective_relocation_date": "2026-11-16",
  "base_net_lump_sum_inr": 250000,
  "base_net_lump_sum_usd_equiv": 3000,
  "effective_tds_tax_plus_cess_pct": 31.2,
  "gross_up_policy": "HR-REL-518C-STD (Full tax-neutral gross-up protecting exact ₹2,50,000 net cash in bank)",
  "clawback_window_months": 12,
  "example_exit_check_months_completed": 9,
  "clawback_trigger": "Voluntary resignation only (waived 100% after 12 full months or involuntary layoff)"
}
```""",
            },
            {
                "turn_number": 6,
                "topic_tag": "Dependent Parents Health Insurance & Aadhaar Masking Rules",
                "user_message": """Super clear math (`₹3,63,372` gross -> `₹1,13,372` TDS = exact `₹2,50,000` net cash, and 3/12 remaining clawback = `₹90,843` at month 9)! Next HR question: I want to enroll my mother (age 62) and father (age 66) into the **₹5,00,000 Dependent Parents Top-Up Insurance (`HR-INS-PAR-26`)**. Workday shows a **30-calendar-day onboarding enrollment window (`WD-BEN-30D`)**, and I have my father's **full unmasked 12-digit Aadhaar PDF** on my desktop right now. Should I attach or paste his unmasked Aadhaar number here in Service Desk chat for verification, what % does NovaMart co-fund, and what exact cutoff date applies since I joined **Nov 16, 2026**?

=== WORKDAY BENEFITS ENROLLMENT PROMPT (`WD-BEN-30D` · `EMP-IN-51904`) ===
```json
{
  "employee_id": "EMP-IN-51904 (Neha Kapoor · L6 Principal SRE)",
  "join_date": "2026-11-16",
  "enrollment_window_policy": "WD-BEN-30D (30 calendar days from onboarding effective date)",
  "dependents_to_enroll": [
    {"relation": "Mother", "age": 62, "doc_ready": "Masked Aadhaar (XXXX-XXXX-NNNN last-4) + Birth Certificate"},
    {"relation": "Father", "age": 66, "doc_ready": "Unmasked 12-digit Aadhaar PDF ready on laptop desktop"}
  ],
  "plan_code": "HR-INS-PAR-26 (INR 5,00,000 Top-Up Parental Medical Cover)",
  "portal_state": "AWAITING_MASKED_ID_AND_DOB_KMS_VAULT_UPLOAD"
}
```""",
            },
            {
                "turn_number": 7,
                "topic_tag": "Hybrid WFH Ergonomic Chair + Dock Claim (₹29,800 vs ₹35k)",
                "user_message": """Glad I checked before uploading an unmasked Aadhaar — I will mask the first 8 digits (`XXXX-XXXX-NNNN`) and upload solely inside the encrypted Workday KMS Vault before the December 16 cutoff! Next question: once my Hyderabad apartment lease starts Dec 1, I want to claim a high-back ergonomic chair (`₹18,900`) and a CalDigit TS4 dock (`₹10,900`) for **₹29,800 INR total** under `HR-BEN-ERGO-26`. Since my prior FY26 claims = `₹0` and my manager *Siddharth Nair* is active (not on PTO), does `₹29,800` clear in a single Concur claim with just L7 manager signoff, what remaining FY26 allowance stays available, and does a Thunderbolt dock qualify?

=== CONCUR DRAFT CART (`HR-BEN-ERGO-26` · FY26 BALANCE CHECK · `EMP-IN-51904`) ===
```json
{
  "employee_id": "EMP-IN-51904",
  "fiscal_year": "FY26 (2026-04-01 to 2027-03-31)",
  "concur_expense_category": "ERGO-WFH-FY26",
  "prior_fy26_ergo_spend_inr": 0,
  "draft_items": [
    {"item": "Featherlite Helix High-Back Ergonomic Mesh Chair", "category": "ergonomic_chair", "amount_inr": 18900},
    {"item": "CalDigit TS4 Thunderbolt 4 Dock (0.8m)", "category": "thunderbolt_usb_c_dock", "amount_inr": 10900}
  ],
  "combined_claim_inr": 29800,
  "gst_invoice_verified": true,
  "manager_emp_id": "EMP-IN-11088 (Siddharth Nair · L7 VP Core Infrastructure · Active · 0 PTO)"
}
```""",
            },
            {
                "turn_number": 8,
                "topic_tag": "First-Month Payroll Cutoff Check (Joined Nov 16 vs Nov 18 Cutoff)",
                "user_message": """`₹29,800` clears inside both the `₹35,000` annual cap and the `₹30,000` single-claim rule via Siddharth Nair directly, leaving `₹5,200` for any split keyboard or vertical mouse later in FY26! One urgent Payroll timing question before November ends: I joined **Monday, November 16, 2026**, and Section 4.2 of the handbook mentions our monthly SAP cutoff on the **18th (`Nov 18 at 18:00 IST`)**. Because I joined on the **16th** (16th–30th window) AND just submitted my relocation/bank packet Nov 17, will I receive a 15-day pro-rated paycheck on **Nov 30**, or does `HR-PAY-NH-18` combine Nov 16–30 into **Dec 31** payroll — and what advance option exists?

=== NEW HIRE PAYROLL INTAKE SNAPSHOT (`EMP-IN-51904` · JOIN DATE NOV 16, 2026) ===
```json
{
  "employee_id": "EMP-IN-51904 (Neha Kapoor · L6 Principal SRE · HYD-HITEC)",
  "joining_date": "2026-11-16",
  "november_sap_cutoff_ist": "2026-11-18T18:00:00+05:30",
  "tax_declaration_and_bank_status": "Submitted 2026-11-17 (Treasury micro-deposit verification queued)",
  "expected_nov_calendar_days_worked": 15,
  "first_paycheck_question": "Nov 30 pro-rata check vs Dec 31 combined Cycle-1+Cycle-2 disbursement",
  "available_advance_policy": "HR-PAY-ADV-14 (14-day Onboarding Advance against relocation/salary)",
  "policy_rule_check": "HR-PAY-NH-18 & HR-PAY-ADV-14"
}
```""",
            },
            {
                "turn_number": 9,
                "topic_tag": "PagerDuty Shadow Rotation 4-Gate Readiness Audit",
                "user_message": """Good thing I asked — under `HR-PAY-NH-18`, Nov 16–30 pro-rata days combine cleanly with December salary on Dec 31 unless I opt into the 14-day `HR-PAY-ADV-14` Onboarding Advance! Finally, before Siddharth adds me to this Thursday's **PagerDuty Shadow On-Call rotation**, let's audit my live state below against the mandatory 4-gate `SRE-ONCALL-GATE` checklist. Look carefully at every JSON field: which 3 gates are already GREEN, what ONE gate still blocks tonight's on-call dry-run, and what exact final command + co-signer unblocks it?

=== `SRE-ONCALL-GATE` READINESS SNAPSHOT (`16:40 IST` · `EMP-IN-51904`) ===
```json
{
  "audit_framework": "SRE-ONCALL-GATE (All 4 prerequisites required prior to Shadow PagerDuty shift)",
  "gate_1_fido2_hardware_keys": {"enrolled_count": 2, "primary": "YubiKey 5C NFC", "backup": "YubiKey 5C NFC #B4", "okta_fido2": "GREEN"},
  "gate_2_pam_jit_dry_run": {
    "cluster": "prod-k8s-sre",
    "role": "prod-k8s-sre-ro",
    "max_ttl_hours": 4,
    "change_ticket": "CHG-2026-8841",
    "tsh_dry_run_status": "PENDING — still need L7 VP co-sign dry-run approval from Siddharth Nair (EMP-IN-11088)"
  },
  "gate_3_registry_mtls_and_sase_ca_v4": {"client_cert_days_remaining": 90, "root_ca": "v4", "pull_test": "PASSED"},
  "gate_4_workday_scim_pagerduty": {"workday_status": "ACTIVE", "pagerduty_webhook": "BOUND", "slack_inc_triage": "JOINED"}
}
```""",
            },
            {
                "turn_number": 10,
                "topic_tag": "Turn 10 Consolidated Day-2 SRE & Relocation Execution Ledger",
                "user_message": """That's 9 turns of continuous troubleshooting and HR/Finance policy verification across my entire Hyderabad Principal SRE Day-2 onboarding! Before I send my final status message to VP Siddharth Nair (`EMP-IN-11088`), generate my **Final Consolidated Day-2 Execution & Compliance Ledger** covering ALL systems across Turns 1–9: FIDO2 dual keys, `SRE-ONCALL-GATE` Gate 2 remaining `prod-k8s-sre-ro` 4h PAM JIT dry-run, Docker mTLS 90-day + Root CA v4 status, Concur `₹1,48,000` Amex hold lift, `₹2,50,000` net / `₹3,63,372` tax-protected relocation gross-up + 12m clawback terms, `HR-INS-PAR-26` masked-Aadhaar parental cover by Dec 16, `₹29,800` Concur Ergo claim (`₹5,200` remaining), and `HR-PAY-NH-18` Dec 31 combined payroll schedule. Format strictly as ONE compact Markdown table (<= 250 words total, zero narrative prose before or after the table).

=== TURN 10 FINAL ONBOARDING LEDGER SNAPSHOT (`EMP-IN-51904` · `17:05 IST`) ===
```json
{
  "bundle_id": "SD-BUNDLE-2026-1117-51904",
  "employee": "Neha Kapoor (EMP-IN-51904 · L6 Principal SRE · HYD-HITEC)",
  "device": "NM-MAC-HYD-9204 (OKTA_FIDO2=2, Docker_mTLS=90d, SASE_CA=v4)",
  "open_gate": "SRE-ONCALL-GATE Gate 2 (prod-k8s-sre-ro 4h L7 co-sign by EMP-IN-11088)",
  "hr_finance_totals_inr": {"relocation_gross": 363372, "relocation_net": 250000, "ergo_claim": 29800, "ergo_left": 5200}
}
```""",
            },
        ],
    },
]
