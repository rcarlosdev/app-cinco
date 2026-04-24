from __future__ import annotations

import os
from unittest.mock import patch

from django.test import SimpleTestCase

from apps.ia_dev.services.intent_service import IntentClassifierService


class IntentServiceEmployeeLookupTests(SimpleTestCase):
    def test_classify_generic_employee_lookup_by_movil_identifier(self):
        with patch.dict(os.environ, {"IA_DEV_USE_OPENAI_CLASSIFIER": "0"}, clear=False):
            service = IntentClassifierService()
            classification = service.classify("informacion de TIRAN462")
        self.assertEqual(str(classification.get("domain") or ""), "empleados")
        self.assertTrue(bool(classification.get("needs_database")))

    def test_classify_generic_employee_lookup_by_movil_identifier_without_preposition(self):
        with patch.dict(os.environ, {"IA_DEV_USE_OPENAI_CLASSIFIER": "0"}, clear=False):
            service = IntentClassifierService()
            classification = service.classify("informacion TIRAN462")
        self.assertEqual(str(classification.get("domain") or ""), "empleados")
        self.assertTrue(bool(classification.get("needs_database")))

    def test_classify_generic_employee_lookup_by_movil_identifier_with_space(self):
        with patch.dict(os.environ, {"IA_DEV_USE_OPENAI_CLASSIFIER": "0"}, clear=False):
            service = IntentClassifierService()
            classification = service.classify("informacion tiran 462")
        self.assertEqual(str(classification.get("domain") or ""), "empleados")
        self.assertTrue(bool(classification.get("needs_database")))

    def test_classify_generic_employee_lookup_by_movil_numeric_suffix(self):
        with patch.dict(os.environ, {"IA_DEV_USE_OPENAI_CLASSIFIER": "0"}, clear=False):
            service = IntentClassifierService()
            classification = service.classify("462")
        self.assertEqual(str(classification.get("domain") or ""), "empleados")
        self.assertTrue(bool(classification.get("needs_database")))
