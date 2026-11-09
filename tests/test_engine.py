"""
Unit tests for Sahaayak Pro Triage Engine.
Tests multiple scenarios for each risk level (URGENT_REFERRAL, CLINIC_VISIT, HOME_CARE),
symptom extraction from text (English & transliterated Hindi), and risk priority escalation.
Compatible with standard unittest and pytest.
"""

import unittest
import os
import sys

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from triage.engine import evaluate, extract_symptoms, load_rules, load_keywords


class TestTriageUrgentReferral(unittest.TestCase):
    """Tests for cases triggering URGENT_REFERRAL (Risk Level 3)"""

    def test_child_general_danger_signs_convulsions(self):
        result = evaluate(
            patient_group='child',
            age_months=24,
            symptoms=['convulsions', 'fever']
        )
        self.assertEqual(result['risk'], 'URGENT_REFERRAL')
        self.assertEqual(result['risk_level'], 3)
        self.assertTrue(any('General Danger Signs' in r for r in result['reasons']))
        self.assertTrue(any('GDS-001' in r for r in result['rules_fired']))

    def test_pregnant_vaginal_bleeding(self):
        result = evaluate(
            patient_group='pregnant',
            age_months=300,
            symptoms=['vaginal_bleeding']
        )
        self.assertEqual(result['risk'], 'URGENT_REFERRAL')
        self.assertEqual(result['risk_level'], 3)
        self.assertTrue(any('Pregnancy Danger Signs' in r for r in result['reasons']))

    def test_newborn_not_feeding(self):
        result = evaluate(
            patient_group='newborn',
            age_months=1,
            symptoms=['not_feeding']
        )
        self.assertEqual(result['risk'], 'URGENT_REFERRAL')
        self.assertEqual(result['risk_level'], 3)
        self.assertTrue(any('Very Severe Disease' in r for r in result['reasons']))

    def test_severe_pneumonia_chest_indrawing(self):
        result = evaluate(
            patient_group='child',
            age_months=18,
            symptoms=['chest_indrawing', 'fast_breathing']
        )
        self.assertEqual(result['risk'], 'URGENT_REFERRAL')
        self.assertEqual(result['risk_level'], 3)


class TestTriageClinicVisit(unittest.TestCase):
    """Tests for cases triggering CLINIC_VISIT (Risk Level 2)"""

    def test_child_fever_alone(self):
        result = evaluate(
            patient_group='child',
            age_months=36,
            symptoms=['fever']
        )
        self.assertEqual(result['risk'], 'CLINIC_VISIT')
        self.assertEqual(result['risk_level'], 2)
        self.assertTrue(any('Fever' in r for r in result['reasons']))

    def test_child_fast_breathing_pneumonia(self):
        result = evaluate(
            patient_group='child',
            age_months=15,
            symptoms=['fast_breathing']
        )
        self.assertEqual(result['risk'], 'CLINIC_VISIT')
        self.assertEqual(result['risk_level'], 2)
        self.assertTrue(any('Pneumonia' in r for r in result['reasons']))

    def test_pregnant_warning_signs_mild_headache(self):
        result = evaluate(
            patient_group='pregnant',
            age_months=280,
            symptoms=['mild_headache', 'swelling_feet']
        )
        self.assertEqual(result['risk'], 'CLINIC_VISIT')
        self.assertEqual(result['risk_level'], 2)
        self.assertTrue(any('Pregnancy Warning Signs' in r for r in result['reasons']))

    def test_newborn_local_infection(self):
        result = evaluate(
            patient_group='newborn',
            age_months=1,
            symptoms=['umbilicus_redness']
        )
        self.assertEqual(result['risk'], 'CLINIC_VISIT')
        self.assertEqual(result['risk_level'], 2)


class TestTriageHomeCare(unittest.TestCase):
    """Tests for cases resulting in HOME_CARE (Risk Level 1)"""

    def test_no_symptoms_child(self):
        result = evaluate(
            patient_group='child',
            age_months=12,
            symptoms=[]
        )
        self.assertEqual(result['risk'], 'HOME_CARE')
        self.assertEqual(result['risk_level'], 1)

    def test_normal_pregnant_woman(self):
        result = evaluate(
            patient_group='pregnant',
            age_months=300,
            symptoms=[]
        )
        self.assertEqual(result['risk'], 'HOME_CARE')
        self.assertEqual(result['risk_level'], 1)
        self.assertTrue(any('Normal Pregnancy' in r for r in result['reasons']))

    def test_unrelated_or_empty_adult(self):
        result = evaluate(
            patient_group='adult',
            age_months=400,
            symptoms=[]
        )
        self.assertEqual(result['risk'], 'HOME_CARE')
        self.assertEqual(result['risk_level'], 1)


class TestRiskEscalation(unittest.TestCase):
    """Test that higher risk always supersedes lower risk"""

    def test_highest_risk_wins_child(self):
        result = evaluate(
            patient_group='child',
            age_months=14,
            symptoms=['fever', 'chest_indrawing']
        )
        self.assertEqual(result['risk'], 'URGENT_REFERRAL')
        self.assertEqual(result['risk_level'], 3)


class TestSymptomKeywordExtraction(unittest.TestCase):
    """Test text matching and multilingual synonym recognition"""

    def test_english_symptom_extraction(self):
        text = "Child is very hot with high fever and shaking with fits"
        extracted = extract_symptoms(text, language='en')
        self.assertIn('fever', extracted)
        self.assertIn('convulsions', extracted)

    def test_hindi_transliterated_extraction(self):
        text = "Bacche ko tez bukhar hai aur saans me taklif hai"
        extracted = extract_symptoms(text, language='hi')
        self.assertIn('fever', extracted)
        self.assertIn('fast_breathing', extracted)

    def test_empty_string_extraction(self):
        self.assertEqual(extract_symptoms("", language='en'), [])
        self.assertEqual(extract_symptoms("   ", language='hi'), [])


class TestEngineIntegrity(unittest.TestCase):
    """Check rule set integrity and schema"""

    def test_rules_file_valid(self):
        rules_data = load_rules()
        self.assertIn('rules', rules_data)
        self.assertGreater(len(rules_data['rules']), 0)

    def test_all_rules_have_protocol_references(self):
        rules_data = load_rules()
        for rule in rules_data['rules']:
            self.assertIn('protocol_ref', rule)
            self.assertGreater(len(rule['protocol_ref']), 0)


if __name__ == '__main__':
    unittest.main()
