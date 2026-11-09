# Sahaayak Pro (सहायक प्रो / ਸਹਾਇਕ ਪ੍ਰੋ)

> **Offline Symptom-Triage & Referral Tool for ASHA Workers in Rural India**  
> *Zero internet required. Fully deterministic, rule-based clinical decision support encoded directly from WHO IMNCI and maternal risk protocols.*

---

## 🏥 Overview

In rural health settings across India, Accredited Social Health Activist (ASHA) workers frequently conduct home visits and triage in regions with poor, intermittent, or completely absent cellular connectivity. Traditional cloud-based or LLM-dependent health applications fail under these circumstances.

**Sahaayak Pro** is built ground-up for zero-connectivity environments:
- **Zero Cloud / Zero LLM**: 100% deterministic, transparent rule engine. Every triage classification cites the exact clinical guideline and module number.
- **Runs anywhere Python runs**: Laptops, low-cost tablets, and Android smartphones via Termux.
- **Multi-lingual**: Full UI and symptom vocabulary in **English**, **हिन्दी (Hindi)**, and **ਪੰਜਾਬੀ (Punjabi)**.
- **Offline-First Storage & Auto-Sync**: Cases are recorded in local SQLite with unique IDs (`C-XXXXXXXX`). A background sync worker transparently queues and pushes records whenever network connectivity is restored.
- **Printable / Downloadable Referral Slips**: Auto-generates formal referral slips (PDF or print-optimized HTML view) for families to take to primary health centers or hospitals.

---

## ⚡ Core Triage Flow (3 Steps)

1. **Step 1: Patient Details**
   - Select Patient Group: `Child (2 months - 5 years)`, `Newborn (0 - 2 months)`, `Pregnant Woman`, or `Adult`.
   - Specify age (months/years) and gender.
2. **Step 2: Symptom Assessment**
   - Tap large touch-target icon checkboxes (min 56px touch target) or describe symptoms via voice/text in English, Hindi, or Punjabi.
3. **Step 3: Immediate Risk Classification**
   - 🔴 **URGENT REFERRAL** (Red) — Life-threatening general danger signs or emergency maternal complications. Immediate hospital referral needed.
   - 🟡 **CLINIC VISIT** (Amber) — Warning signs requiring clinical assessment at a Primary Health Centre (PHC) within 24 hours.
   - 🟢 **HOME CARE** (Green) — Safe home management protocol with warning indicators on when to return.

---

## 🛠️ Architecture & Tech Stack

- **Backend**: Python 3.10+ with Flask (served locally on `http://localhost:8080`, configurable via `--port`).
- **Database**: SQLite via Python's built-in `sqlite3` in WAL mode (`sahaayak_pro.db`).
- **Rules Engine**: `triage/engine.py` evaluating `triage/rules.json` and matching multilingual phonetic/transliterated synonyms from `triage/keywords.json`.
- **Frontend**: Jinja2 templates, vanilla CSS (`static/css/style.css`), and minimal vanilla JS (`static/js/app.js`). **Zero external CDNs or external font dependencies.**
- **Speech-to-Text**: Offline-capable Web Speech API in browser with seamless fallback to text if speech recognition is unavailable on device.
- **PDF Generation**: ReportLab for offline referral cards (with HTML print view fallback).

---

## 📁 Project Structure

```
sahaayak_pro/
│
├── app.py                   # Main Flask routes and application server
├── db.py                    # SQLite helper module (WAL mode, indexing, schema)
├── sync.py                  # Background sync daemon and connectivity monitor
├── requirements.txt         # Dependencies (flask, reportlab, pytest)
├── README.md                # Documentation and demo guides
│
├── triage/
│   ├── __init__.py
│   ├── engine.py            # Pure Python deterministic triage engine
│   ├── rules.json           # Editable WHO IMNCI & maternal risk rules
│   └── keywords.json        # Symptom synonyms in English, Hindi, Punjabi
│
├── i18n/
│   ├── en.json              # English language catalog
│   ├── hi.json              # Hindi (Devanagari) catalog
│   └── pa.json              # Punjabi (Gurmukhi) catalog
│
├── static/
│   ├── css/
│   │   └── style.css        # Responsive, high-contrast, mobile-first CSS
│   └── js/
│       └── app.js           # Offline speech recognition, sync badges, interactions
│
├── templates/
│   ├── base.html            # Base layout with language toggle & sync badge
│   ├── index.html           # Dashboard & quick statistics
│   ├── new_case.html        # Step 1: Patient group & age
│   ├── symptoms.html        # Step 2: Symptom selection & voice input
│   ├── result.html          # Step 3: Triage output, reasons, and actions
│   ├── case_detail.html     # Detailed case inspection
│   ├── cases.html           # Case history & data export (CSV/JSON)
│   ├── about.html           # Protocol sources & medical disclaimers
│   ├── status.html          # Device offline status & sync metrics
│   ├── print_card.html      # Print-optimized A5 referral slip
│   └── 404.html             # Error page
│
└── tests/
    ├── __init__.py
    └── test_engine.py       # Pytest suite verifying triage classifications
```

---

## 🚀 Setup & Installation

### 1. Prerequisites
Ensure Python 3.10 or later is installed.

### 2. Clone or Enter Directory
```bash
cd sahaayak_pro
```

### 3. Create Virtual Environment & Install Dependencies
```bash
python -m venv venv

# On Linux / macOS / Termux:
source venv/bin/activate

# On Windows:
venv\Scripts\activate

# Install dependencies:
pip install -r requirements.txt
```

### 4. Run the Application
```bash
# Run on default port 8080:
python app.py

# Or choose any custom port you like (e.g. 5050, 8000, 3000):
python app.py --port 8080
```
Open your browser at: **`http://localhost:8080`** (or access from a local Wi-Fi hotspot on Android).

---

## ✈️ Airplane-Mode Demonstration Guide

To demonstrate Sahaayak Pro's complete offline capabilities:

1. **Disconnect from Internet**:
   - Turn on Airplane Mode on your laptop or phone, or disconnect Wi-Fi and mobile data.
2. **Launch Sahaayak Pro**:
   - Run `python app.py`.
   - Open `http://localhost:8080`.
3. **Verify Header Status**:
   - Observe the **`OFFLINE`** red badge in the header navigation bar.
4. **Conduct a Triage Assessment**:
   - Click **New Case**.
   - Select **Child**, Age `18 months`.
   - In Step 2, select **Convulsions** and **Fever** (or type `bacche ko bukhar aur jhatkay aa rahe hain`).
   - Click **CHECK RISK ⚡**.
5. **Inspect the Result**:
   - Risk banner triggers **URGENT REFERRAL** (Red) with protocol citation: `WHO IMNCI - General Danger Signs, Module 1`.
   - Click **Explain this referral** to view clear, spoken-friendly guidance for the family.
   - Click **Print / Save Card** or **Download PDF Referral Card** to generate the offline referral slip.
6. **Check Case History & Local Sync Queue**:
   - Visit the **Case History** page — the record is saved with `Local` / `pending` status.
   - Visit **Device Status** page — inspect the database size, pending sync count, and export CSV/JSON directly.
7. **Demonstrate Auto-Sync**:
   - Turn Wi-Fi back on.
   - Within 30 seconds, the background thread detects network connectivity, updates the header badge to **`ONLINE`**, pushes queued cases, and marks them `Synced ✓`.

---

## 🧪 Running Unit Tests

Run the full pytest suite:

```bash
pytest -v tests/test_engine.py
```

The test suite validates:
- **URGENT_REFERRAL** triggers for childhood general danger signs, severe pneumonia (chest indrawing), maternal bleeding, and neonatal refusal to feed.
- **CLINIC_VISIT** triggers for isolated fever, fast breathing, mild neonatal infections, and pregnancy warning signs.
- **HOME_CARE** defaults for healthy or normal assessments.
- **Risk Escalation**: Highest risk always wins when multiple symptoms are reported.
- **Multilingual Symptom Extraction**: Natural language keyword mapping in English and Hindi.

---

## 📱 Running on Android via Termux

Sahaayak Pro runs natively on low-cost Android phones through Termux without root:

1. Install **Termux** from F-Droid.
2. In Termux, update packages and install Python & Git:
   ```bash
   pkg update && pkg upgrade -y
   pkg install python git -y
   ```
3. Copy or clone the `sahaayak_pro` repository into Termux:
   ```bash
   cd sahaayak_pro
   pip install -r requirements.txt
   ```
4. Start the server:
   ```bash
   python app.py
   ```
5. Open Chrome on the phone and navigate to `http://localhost:8080`.
6. Tap the Chrome menu → **Add to Home screen** for a full-screen, native app experience!

---

## 📜 Medical References & Protocols

- **WHO IMNCI (Integrated Management of Neonatal and Childhood Illness)**:
  - Module 1: General Danger Signs
  - Module 2: Cough or Difficult Breathing
  - Module 3: Diarrhoea & Dehydration Assessment
  - Module 4: Fever & Measles
  - Module 5: Malnutrition & Anaemia
  - Module 6: Young Infant (0-2 months) Very Severe Disease
  - Module 7: Counsel the Mother
- **Ministry of Health & Family Welfare (MoHFW), Govt of India**:
  - ASHA Training Modules 6 & 7 (Maternal, Newborn, and Child Care)
- **IDSP (Integrated Disease Surveillance Programme)** community health guidelines.

---

## ⚠️ Disclaimer

*Sahaayak Pro is a prototype clinical decision-support tool created to assist community healthcare workers in resource-constrained and offline environments. It does not provide medical diagnoses or replace licensed physicians. All rules and protocols must be clinically reviewed and validated by regional health authorities prior to real-world deployment.*
