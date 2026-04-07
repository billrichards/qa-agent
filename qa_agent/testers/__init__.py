"""Test modules for different input methods and checks."""

from .accessibility import AccessibilityTester
from .custom import CustomTester
from .errors import ErrorDetector
from .forms import FormTester
from .keyboard import KeyboardTester
from .mouse import MouseTester
from .wcag_compliance import WCAGComplianceTester

__all__ = [
    "KeyboardTester",
    "MouseTester",
    "FormTester",
    "AccessibilityTester",
    "ErrorDetector",
    "CustomTester",
    "WCAGComplianceTester",
]
