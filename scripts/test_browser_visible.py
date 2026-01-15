"""
Test script to verify browser visibility (no LLM calls).
This directly tests BrowserGym environment creation with visible browser.
"""
import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import gymnasium as gym
import browsergym.miniwob  # Register browsergym environments

# Set environment variables
os.environ["MINIWOB_URL"] = f"file:///{project_root}/benchmarks/miniwob/html/miniwob/"
os.environ["BROWSER_HEADLESS"] = "false"  # VISIBLE

print("="*60)
print("BROWSER VISIBILITY TEST")
print("="*60)
print(f"MINIWOB_URL: {os.environ['MINIWOB_URL']}")
print(f"BROWSER_HEADLESS: {os.environ['BROWSER_HEADLESS']}")
print("")

try:
    print("Creating BrowserGym environment (VISIBLE MODE)...")
    env = gym.make(
        "browsergym/miniwob.click-test",
        headless=False  # Explicitly set to False
    )
    
    print("✓ Environment created!")
    print("Resetting environment...")
    
    obs, info = env.reset()
    
    print("✓ Environment reset successful!")
    print(f"Goal: {obs.get('goal', 'N/A')}")
    print("")
    print("Browser should be VISIBLE now!")
    print("Press Ctrl+C to close...")
    
    # Keep it open for 30 seconds so you can see the browser
    import time
    time.sleep(30)
    
    print("\nClosing environment...")
    env.close()
    print("✓ Test complete!")
    
except Exception as e:
    print(f"✗ Error: {e}")
    import traceback
    traceback.print_exc()
