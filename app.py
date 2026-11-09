"""
Sahaayak Pro - Main Flask Application
Offline-first health symptom-triage and referral decision support for ASHA workers.
"""

from flask import Flask, render_template, request, redirect, url_for, session, jsonify, Response, send_file
import json
import os
import io
from datetime import datetime

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'sahaayak-pro-offline-key-2024')

# Database & Engine imports
from db import (
    init_db,
    save_case,
    get_case,
    get_all_cases,
    get_stats,
    get_setting,
    set_setting,
    get_cases_for_export
)
from triage.engine import evaluate, extract_symptoms, load_rules
from sync import sync_worker, export_cases_csv, export_cases_json


def load_i18n():
    """Load all JSON translation catalogs from i18n/ directory."""
    catalogs = {}
    i18n_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'i18n')
    if os.path.exists(i18n_dir):
        for fname in os.listdir(i18n_dir):
            if fname.endswith('.json'):
                lang = fname[:-5]
                filepath = os.path.join(i18n_dir, fname)
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        catalogs[lang] = json.load(f)
                except Exception as e:
                    print(f"Error loading {filepath}: {e}")
    return catalogs


I18N = load_i18n()


def get_current_lang():
    """Retrieve language preference from session with 'en' default."""
    return session.get('language', 'en')


def get_translations():
    """Retrieve translations dict for current language."""
    lang = get_current_lang()
    return I18N.get(lang, I18N.get('en', {}))


@app.context_processor
def inject_template_globals():
    """Inject translation strings, current lang, and sync status into all Jinja templates."""
    lang = get_current_lang()
    return {
        't': get_translations(),
        'lang': lang,
        'languages': {'en': 'English', 'hi': 'हिन्दी', 'pa': 'ਪੰਜਾਬੀ'},
        'sync_status': sync_worker.get_status()
    }


# ------------------- Routes -------------------

@app.route('/')
def index():
    stats = get_stats()
    all_cases = get_all_cases(limit=5)
    return render_template('index.html', stats=stats, recent_cases=all_cases)


@app.route('/new-case')
def new_case():
    return render_template('new_case.html')


@app.route('/symptoms', methods=['POST'])
def symptoms():
    patient_group = request.form.get('patient_group', 'child')
    age = request.form.get('age', 12, type=int)
    age_unit = request.form.get('age_unit', 'months')
    gender = request.form.get('gender', '')

    if age_unit == 'years':
        age_months = age * 12
    else:
        age_months = age

    # Filter symptoms relevant to this patient group from rules.json
    rules_data = load_rules()
    relevant_symptoms = set()
    for rule in rules_data.get('rules', []):
        if patient_group in rule.get('patient_groups', []):
            for s in rule.get('symptoms', []):
                relevant_symptoms.add(s)
            for s in rule.get('match_required', []):
                relevant_symptoms.add(s)
            for s in rule.get('match_additional_any', []):
                relevant_symptoms.add(s)

    return render_template(
        'symptoms.html',
        patient_group=patient_group,
        age_months=age_months,
        gender=gender,
        available_symptoms=sorted(list(relevant_symptoms))
    )


@app.route('/check-risk', methods=['POST'])
def check_risk():
    patient_group = request.form.get('patient_group', 'child')
    age_months = request.form.get('age_months', 0, type=int)
    gender = request.form.get('gender', '')
    symptom_text = request.form.get('symptom_text', '')
    selected_symptoms = request.form.getlist('symptoms')

    # Extract symptoms from text/voice notes using keyword dictionary
    current_lang = get_current_lang()
    text_symptoms = extract_symptoms(symptom_text, current_lang) if symptom_text.strip() else []

    # Merge and deduplicate symptoms
    combined_symptoms = list(set(selected_symptoms + text_symptoms))

    # Evaluate deterministic triage rules
    result = evaluate(
        patient_group=patient_group,
        age_months=age_months,
        symptoms=combined_symptoms,
        gender=gender,
        lang=current_lang
    )

    # Persist case to offline SQLite database immediately
    case_data = {
        'patient_group': patient_group,
        'age_months': age_months,
        'gender': gender,
        'symptoms': combined_symptoms,
        'symptom_text': symptom_text,
        'risk': result['risk'],
        'risk_level': result['risk_level'],
        'reasons': result['reasons'],
        'protocol_refs': result['protocol_refs'],
        'explanation': result['explanation'],
        'rules_fired': result['rules_fired'],
        'language': current_lang
    }
    case_id = save_case(case_data)

    return render_template(
        'result.html',
        result=result,
        case_id=case_id,
        patient_group=patient_group,
        age_months=age_months,
        gender=gender
    )


@app.route('/case/<case_id>')
def view_case(case_id):
    case = get_case(case_id)
    if not case:
        return render_template('404.html'), 404
    return render_template('case_detail.html', case=case)


@app.route('/cases')
def cases():
    all_cases = get_all_cases(limit=200)
    return render_template('cases.html', cases=all_cases)


@app.route('/about')
def about():
    rules_data = load_rules()
    return render_template(
        'about.html',
        rules_version=rules_data.get('version', '1.0.0'),
        rules_updated=rules_data.get('last_updated', '2024-01-15')
    )


@app.route('/status')
def status():
    stats = get_stats()
    sync_status = sync_worker.get_status()
    return render_template('status.html', stats=stats, sync_status=sync_status)


@app.route('/set-language', methods=['POST'])
def set_language():
    lang = request.form.get('language', 'en')
    if lang in I18N:
        session['language'] = lang
    return redirect(request.referrer or url_for('index'))


@app.route('/api/sync-status')
def api_sync_status():
    stats = get_stats()
    status_info = sync_worker.get_status()
    return jsonify({**status_info, **stats})


@app.route('/api/sync-now', methods=['POST', 'GET'])
def api_sync_now():
    """Manual sync trigger endpoint."""
    status_info = sync_worker.trigger_sync()
    stats = get_stats()
    return jsonify({
        'success': True,
        'message': 'Sync triggered successfully',
        **status_info,
        **stats
    })


@app.route('/export/csv')
def export_csv():
    csv_data = export_cases_csv()
    return Response(
        csv_data,
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=sahaayak_cases.csv'}
    )


@app.route('/export/json')
def export_json_route():
    json_data = export_cases_json()
    return Response(
        json_data,
        mimetype='application/json',
        headers={'Content-Disposition': 'attachment; filename=sahaayak_cases.json'}
    )


@app.route('/print/<case_id>')
def print_card(case_id):
    case = get_case(case_id)
    if not case:
        return render_template('404.html'), 404
    return render_template('print_card.html', case=case)


@app.route('/pdf/<case_id>')
def pdf_card(case_id):
    case = get_case(case_id)
    if not case:
        return render_template('404.html'), 404

    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
        from reportlab.lib.colors import HexColor

        buffer = io.BytesIO()
        c = canvas.Canvas(buffer, pagesize=A4)
        width, height = A4

        # Risk Banner Color
        risk_colors = {
            'URGENT_REFERRAL': '#C62828',
            'CLINIC_VISIT': '#F57F17',
            'HOME_CARE': '#2E7D32'
        }
        risk_color = risk_colors.get(case.get('risk'), '#1B5E20')

        # Header background banner
        c.setFillColor(HexColor(risk_color))
        c.rect(0, height - 90, width, 90, fill=True, stroke=False)

        c.setFillColor(HexColor('#FFFFFF'))
        c.setFont("Helvetica-Bold", 20)
        c.drawString(30, height - 40, "Sahaayak Pro - Referral Card")

        c.setFont("Helvetica-Bold", 14)
        risk_text = case.get('risk', '').replace('_', ' ')
        c.drawString(30, height - 68, f"Classification: {risk_text}")

        # Meta section
        y = height - 120
        c.setFillColor(HexColor('#000000'))
        c.setFont("Helvetica-Bold", 11)

        meta_rows = [
            ("Case ID:", case.get('case_id', '')),
            ("Date / Time:", str(case.get('created_at', ''))[:19].replace('T', ' ')),
            ("Patient Group:", str(case.get('patient_group', '')).title()),
            ("Age:", f"{case.get('age_months', 0)} months"),
            ("Gender:", str(case.get('gender', 'N/A')).title())
        ]

        for label, val in meta_rows:
            c.setFont("Helvetica-Bold", 10)
            c.drawString(30, y, label)
            c.setFont("Helvetica", 10)
            c.drawString(140, y, str(val))
            y -= 20

        # Reasons section
        y -= 10
        c.setFont("Helvetica-Bold", 12)
        c.drawString(30, y, "Reasons for Classification:")
        y -= 18

        reasons = case.get('reasons', [])
        c.setFont("Helvetica", 10)
        for r in reasons:
            c.drawString(45, y, f"• {r}")
            y -= 16

        # Protocol Reference
        protocol_refs = case.get('protocol_refs', [])
        if protocol_refs:
            y -= 10
            c.setFont("Helvetica-Bold", 12)
            c.drawString(30, y, "Protocol Reference:")
            y -= 18
            c.setFont("Helvetica", 10)
            for ref in protocol_refs:
                c.drawString(45, y, f"• {ref}")
                y -= 16

        # Guidance / Explanation
        y -= 10
        c.setFont("Helvetica-Bold", 12)
        c.drawString(30, y, "Guidance for Family / Attendant:")
        y -= 18
        c.setFont("Helvetica", 9)
        explanation = case.get('explanation', '')
        words = explanation.split()
        line = ""
        for word in words:
            if c.stringWidth(line + " " + word, "Helvetica", 9) < (width - 70):
                line = (line + " " + word).strip()
            else:
                c.drawString(45, y, line)
                y -= 14
                line = word
        if line:
            c.drawString(45, y, line)
            y -= 14

        # Footer
        c.setFont("Helvetica-Oblique", 8)
        c.setFillColor(HexColor('#555555'))
        c.drawString(30, 45, "Generated fully offline by Sahaayak Pro decision support.")
        c.drawString(30, 32, "Notice: Prototype decision-support tool. Does not diagnose disease. Must be clinically validated.")

        c.save()
        buffer.seek(0)
        return send_file(
            buffer,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f"referral_{case_id}.pdf"
        )
    except ImportError:
        # Fallback to HTML print card if reportlab is absent
        return redirect(url_for('print_card', case_id=case_id))


@app.errorhandler(404)
def not_found(e):
    return render_template('404.html'), 404


import argparse

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Sahaayak Pro - Offline Health Triage Server')
    parser.add_argument('--port', type=int, default=int(os.environ.get('PORT', 8080)), help='Port to run the server on (default: 8080)')
    parser.add_argument('--host', type=str, default=os.environ.get('HOST', '0.0.0.0'), help='Host to bind the server to (default: 0.0.0.0)')
    args = parser.parse_args()

    init_db()
    sync_worker.start()
    print("\n" + "="*56)
    print("  Sahaayak Pro - Offline Health Triage Running")
    print(f"  Local URL:    http://localhost:{args.port}")
    print(f"  Network URL:  http://127.0.0.1:{args.port}")
    print(f"  Hotspot/LAN:  http://{args.host}:{args.port}")
    print("  Mode: Fully Offline (Zero-Cloud / Zero-LLM)")
    print("="*56 + "\n")
    app.run(host=args.host, port=args.port, debug=False)
