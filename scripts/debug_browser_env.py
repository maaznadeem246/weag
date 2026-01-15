"""
Debug script to verify BROWSER_HEADLESS environment variable flow.
This shows what value is set at each stage without running a full assessment.
"""
import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

print("="*60)
print("BROWSER_HEADLESS ENVIRONMENT VARIABLE DEBUG")
print("="*60)
print()

# Check current environment
browser_headless = os.environ.get("BROWSER_HEADLESS")
print(f"Current environment: BROWSER_HEADLESS = {repr(browser_headless)}")
print()

# Simulate what session_manager does
if browser_headless is None:
    headless = True
    print("❌ BROWSER_HEADLESS not set -> headless = True (HEADLESS)")
else:
    headless = str(browser_headless).lower() not in ("0", "false", "no", "off")
    print(f"✅ BROWSER_HEADLESS = {repr(browser_headless)}")
    print(f"   str(browser_headless).lower() = {repr(str(browser_headless).lower())}")
    print(f"   Is it in ('0', 'false', 'no', 'off')? {str(browser_headless).lower() in ('0', 'false', 'no', 'off')}")
    print(f"   NOT in list? {str(browser_headless).lower() not in ('0', 'false', 'no', 'off')}")
    print(f"   -> headless = {headless}")
    
    if headless:
        print("   🚫 Browser will be HEADLESS (invisible)")
    else:
        print("   👁️  Browser will be VISIBLE")

print()
print("="*60)
print()

# Show examples
print("EXAMPLES:")
print("-" * 60)

test_values = [
    (None, "Not set"),
    ("false", "Visible (recommended)"),
    ("False", "Visible"),
    ("no", "Visible"),
    ("0", "Visible"),
    ("off", "Visible"),
    ("true", "Headless"),
    ("True", "Headless"),
    ("yes", "Headless"),
    ("1", "Headless"),
    ("anything_else", "Headless"),
]

for value, expected in test_values:
    if value is None:
        headless = True
    else:
        headless = str(value).lower() not in ("0", "false", "no", "off")
    
    result = "HEADLESS (invisible)" if headless else "VISIBLE"
    print(f"BROWSER_HEADLESS={repr(value):20s} -> {result:20s} ({expected})")

print()
print("="*60)
