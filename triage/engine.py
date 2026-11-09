"""
Triage Engine for Sahaayak Pro.
Rule-based symptom triage using WHO IMNCI and maternal risk screening guidelines.
All decisions are transparent and traceable to specific protocol references.
"""

import json
import os
import re
import logging

logger = logging.getLogger(__name__)

_rules_cache = None
_keywords_cache = None

RULES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'rules.json')
KEYWORDS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'keywords.json')

RISK_LEVELS = {
    'URGENT_REFERRAL': 3,
    'CLINIC_VISIT': 2,
    'HOME_CARE': 1
}

# Default explanations (used if i18n lookup fails)
DEFAULT_EXPLANATIONS = {
    "general_danger_signs": "This patient has a serious danger sign. Please refer to the nearest hospital IMMEDIATELY.",
    "severe_pneumonia": "This patient has signs of severe breathing difficulty and needs urgent hospital care.",
    "pneumonia": "This patient has signs of a chest infection and should see a doctor within one day.",
    "severe_dehydration": "This patient has lost too much water and needs urgent hospital treatment with fluids.",
    "some_dehydration": "This patient has some water loss. Give ORS and take to a clinic for further check.",
    "severe_malnutrition": "This patient is severely malnourished and needs hospital treatment with special nutrition support.",
    "severe_fever": "This patient has fever with dangerous signs that may indicate brain infection. Refer immediately.",
    "fever_only": "This patient has fever. Give paracetamol, plenty of fluids, and visit a clinic if fever persists over 2 days.",
    "measles_complications": "This patient has a rash with complications. Please take to a clinic for treatment.",
    "very_severe_disease_newborn": "This newborn has a very serious sign. Newborns can become very sick very quickly. Refer to hospital immediately.",
    "local_infection_newborn": "This newborn has signs of a local infection. Take to a clinic for treatment.",
    "jaundice_newborn": "This newborn has yellow skin. Please have it checked by a doctor.",
    "low_weight_newborn": "This newborn has low birth weight and needs extra care. Please visit a clinic.",
    "pregnancy_danger": "This pregnant woman has a DANGER sign. She must be taken to a hospital IMMEDIATELY.",
    "pregnancy_warning": "This pregnant woman has warning symptoms. Please visit a health clinic within one day.",
    "pregnancy_normal": "This pregnancy appears normal. Continue regular check-ups and take iron-folic acid tablets.",
    "adult_danger": "This person has a serious sign that needs urgent medical care. Go to the nearest hospital immediately.",
    "adult_warning": "This person has symptoms that should be checked by a doctor. Visit a health clinic soon.",
    "home_care_default": "Based on the symptoms, home care should be sufficient. Rest, drink fluids, eat well. Visit a clinic if symptoms worsen."
}


def load_rules(rules_path=None):
    """Load the triage rules from rules.json."""
    global _rules_cache
    path = rules_path or RULES_PATH
    if _rules_cache is None or rules_path:
        try:
            with open(path, 'r', encoding='utf-8') as f:
                _rules_cache = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.error(f"Failed to load rules: {e}")
            _rules_cache = {"version": "0.0.0", "rules": []}
    return _rules_cache


def load_keywords(keywords_path=None):
    """Load the symptom keyword/synonym dictionary from keywords.json."""
    global _keywords_cache
    path = keywords_path or KEYWORDS_PATH
    if _keywords_cache is None or keywords_path:
        try:
            with open(path, 'r', encoding='utf-8') as f:
                _keywords_cache = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.error(f"Failed to load keywords: {e}")
            _keywords_cache = {}
    return _keywords_cache


def normalize_text(text):
    """
    Normalize input text: lowercase, strip extra whitespace and basic punctuation.
    Returns the cleaned string.
    """
    if not text:
        return ""
    text = text.lower().strip()
    # Replace common punctuation with spaces (keep hyphens within words)
    text = re.sub(r'[,;.!?()"\'\[\]{}]', ' ', text)
    # Collapse multiple spaces
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def extract_symptoms(text, language='en'):
    """
    Map free text to canonical symptom IDs using keyword matching.
    Checks multi-word phrases first, then single words.
    Returns a list of matched symptom IDs (deduplicated).
    """
    if not text or not text.strip():
        return []

    normalized = normalize_text(text)
    keywords = load_keywords()
    matched = set()

    # Build a sorted list of (phrase, symptom_id) pairs, longest first
    phrase_map = []
    for symptom_id, lang_synonyms in keywords.items():
        synonyms = lang_synonyms.get(language, []) + lang_synonyms.get('en', [])
        for synonym in synonyms:
            phrase_map.append((normalize_text(synonym), symptom_id))

    # Sort by length descending so multi-word phrases match first
    phrase_map.sort(key=lambda x: len(x[0]), reverse=True)

    for phrase, symptom_id in phrase_map:
        if phrase and phrase in normalized:
            matched.add(symptom_id)

    return list(matched)


def _check_age_condition(age_months, age_condition):
    """Check if the patient's age satisfies the rule's age condition."""
    if not age_condition:
        return True
    min_m = age_condition.get('min_months')
    max_m = age_condition.get('max_months')
    if min_m is not None and age_months < min_m:
        return False
    if max_m is not None and age_months > max_m:
        return False
    return True


def _check_symptoms_match(patient_symptoms, rule):
    """
    Check if the patient's symptoms match the rule's symptom requirements.
    Returns True if the rule fires.
    """
    match_type = rule.get('match', 'any')
    rule_symptoms = rule.get('symptoms', [])

    if match_type == 'default':
        # Default rules fire only when no other rules have matched
        return False  # Handled separately in evaluate()

    if not rule_symptoms:
        return False

    patient_set = set(patient_symptoms)

    if match_type == 'any':
        # Any one of the rule's symptoms present
        return bool(patient_set & set(rule_symptoms))

    elif match_type == 'all':
        # All of the rule's symptoms must be present
        return set(rule_symptoms).issubset(patient_set)

    elif match_type == 'all_of':
        # Required symptoms must be present, plus at least one from additional
        required = rule.get('match_required', [])
        additional = rule.get('match_additional_any', [])
        required_met = set(required).issubset(patient_set)
        additional_met = bool(patient_set & set(additional)) if additional else True
        return required_met and additional_met

    return False


def get_explanation(explanation_key, lang='en'):
    """
    Get a patient-friendly explanation for a rule.
    Tries i18n files first, falls back to DEFAULT_EXPLANATIONS.
    """
    # Try loading i18n explanation
    try:
        i18n_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'i18n', f'{lang}.json')
        with open(i18n_path, 'r', encoding='utf-8') as f:
            i18n_data = json.load(f)
        explanations = i18n_data.get('explanations', {})
        if explanation_key in explanations:
            return explanations[explanation_key]
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        pass

    # Fall back to defaults
    return DEFAULT_EXPLANATIONS.get(explanation_key, DEFAULT_EXPLANATIONS['home_care_default'])


def evaluate(patient_group, age_months, symptoms, gender=None, lang='en'):
    """
    Main triage evaluation function.

    Args:
        patient_group: One of 'child', 'newborn', 'pregnant', 'adult'
        age_months: Age in months (integer)
        symptoms: List of canonical symptom ID strings
        gender: Optional gender string
        lang: Language code for explanations

    Returns:
        dict with keys:
            - risk: 'URGENT_REFERRAL', 'CLINIC_VISIT', or 'HOME_CARE'
            - risk_level: 3, 2, or 1
            - reasons: List of human-readable reason strings
            - protocol_refs: List of protocol reference strings
            - explanation: Patient-friendly explanation string
            - rules_fired: List of rule IDs that fired
    """
    rules_data = load_rules()
    all_rules = rules_data.get('rules', [])

    fired_rules = []
    default_rule = None

    for rule in all_rules:
        # Check patient group
        if patient_group not in rule.get('patient_groups', []):
            continue

        # Check age condition
        age_condition = rule.get('age_condition')
        if not _check_age_condition(age_months, age_condition):
            continue

        # Check if it's a default rule
        if rule.get('match') == 'default':
            if default_rule is None:
                default_rule = rule
            continue

        # Check symptom match
        if _check_symptoms_match(symptoms, rule):
            fired_rules.append(rule)

    # If no rules fired, use default
    if not fired_rules:
        if default_rule:
            explanation_key = default_rule.get('explanation_key', 'home_care_default')
            return {
                'risk': 'HOME_CARE',
                'risk_level': 1,
                'reasons': [default_rule.get('name', 'No risk factors identified')],
                'protocol_refs': [default_rule.get('protocol_ref', '')],
                'explanation': get_explanation(explanation_key, lang),
                'rules_fired': [default_rule.get('id', 'HC-DEFAULT')]
            }
        return {
            'risk': 'HOME_CARE',
            'risk_level': 1,
            'reasons': ['No risk factors identified based on reported symptoms'],
            'protocol_refs': [],
            'explanation': get_explanation('home_care_default', lang),
            'rules_fired': []
        }

    # Find highest risk level among fired rules
    highest_risk = 'HOME_CARE'
    highest_level = 1

    for rule in fired_rules:
        risk = rule.get('risk', 'HOME_CARE')
        level = RISK_LEVELS.get(risk, 1)
        if level > highest_level:
            highest_level = level
            highest_risk = risk

    # Collect reasons, protocol refs from all fired rules
    reasons = []
    protocol_refs = []
    rule_ids = []
    explanation_key = 'home_care_default'

    # Sort fired rules by risk level (highest first)
    fired_rules.sort(key=lambda r: RISK_LEVELS.get(r.get('risk', 'HOME_CARE'), 1), reverse=True)

    for rule in fired_rules:
        rule_name = rule.get('name', 'Unknown')
        rule_risk = rule.get('risk', 'HOME_CARE')
        reasons.append(f"{rule_name} ({rule_risk.replace('_', ' ').title()})")
        ref = rule.get('protocol_ref', '')
        if ref and ref not in protocol_refs:
            protocol_refs.append(ref)
        rule_ids.append(rule.get('id', ''))

    # Use explanation from the highest-risk rule
    explanation_key = fired_rules[0].get('explanation_key', 'home_care_default')

    return {
        'risk': highest_risk,
        'risk_level': highest_level,
        'reasons': reasons,
        'protocol_refs': protocol_refs,
        'explanation': get_explanation(explanation_key, lang),
        'rules_fired': rule_ids
    }
