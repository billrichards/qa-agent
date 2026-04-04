"""Test modules for different input methods and checks."""

from .keyboard import KeyboardTester
from .mouse import MouseTester
from .forms import FormTester
from .accessibility import AccessibilityTester
from .errors import ErrorDetector

__all__ = [
    "KeyboardTester",
    "MouseTester", 
    "FormTester",
    "AccessibilityTester",
    "ErrorDetector",
]
