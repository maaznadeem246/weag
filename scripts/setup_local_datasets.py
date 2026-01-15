"""
Setup script for local development - downloads MiniWoB benchmark.

Run this script once before running tests locally:
    python scripts/setup_local_datasets.py

For Docker, benchmarks are automatically downloaded during build.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path


def setup_miniwob():
    """Download and setup MiniWoB++ dataset for local development."""
    print("\n" + "="*60)
    print("Setting up MiniWoB++ dataset for local development")
    print("="*60 + "\n")
    
    # Determine project root and dataset directory
    project_root = Path(__file__).parent.parent
    benchmarks_dir = project_root / "benchmarks"
    miniwob_dir = benchmarks_dir / "miniwob"
    miniwob_html_dir = miniwob_dir / "html"
    miniwob_task_dir = miniwob_html_dir / "miniwob"
    
    # Check if already exists
    if miniwob_task_dir.exists() and any(miniwob_task_dir.iterdir()):
        print(f"✓ MiniWoB dataset already exists at: {miniwob_html_dir}")
        html_count = len(list(miniwob_task_dir.glob("*.html")))
        print(f"  Files found: {html_count}")
        
        # Set environment variable hint (must point to directory containing task HTML files)
        miniwob_url = f"file:///{miniwob_task_dir.as_posix().rstrip('/')}/"
        print(f"\n✓ Set MINIWOB_URL environment variable:")
        if sys.platform == "win32":
            print(f"  PowerShell: $env:MINIWOB_URL=\"{miniwob_url}\"")
        else:
            print(f"  Bash: export MINIWOB_URL=\"{miniwob_url}\"")
        return True
    
    print(f"Downloading MiniWoB++ dataset to: {miniwob_dir}")
    
    # Create benchmarks directory
    benchmarks_dir.mkdir(parents=True, exist_ok=True)
    
    # Clone with sparse checkout for efficiency
    temp_dir = benchmarks_dir / "temp_miniwob"
    
    try:
        print("\n[1/4] Cloning repository (sparse checkout)...")
        subprocess.run([
            "git", "clone",
            "--depth", "1",
            "--filter=blob:none",
            "--sparse",
            "https://github.com/Farama-Foundation/miniwob-plusplus.git",
            str(temp_dir)
        ], check=True, capture_output=True)
        
        print("[2/4] Checking out HTML files...")
        subprocess.run([
            "git", "-C", str(temp_dir),
            "sparse-checkout", "set", "miniwob/html"
        ], check=True, capture_output=True)
        
        print("[3/4] Copying files...")
        miniwob_dir.mkdir(parents=True, exist_ok=True)
        shutil.copytree(temp_dir / "miniwob" / "html", miniwob_html_dir, dirs_exist_ok=True)
        
        print("[4/4] Cleaning up temporary files...")
        shutil.rmtree(temp_dir, ignore_errors=True)
        
        # Count HTML files (in miniwob/ subdirectory)
        html_files = list(miniwob_task_dir.glob("*.html")) if miniwob_task_dir.exists() else []
        print(f"\n✓ Successfully downloaded {len(html_files)} MiniWoB HTML files")
        print(f"✓ Dataset location: {miniwob_html_dir}")
        
        # Set environment variable hint (must point to directory containing task HTML files)
        miniwob_url = f"file:///{miniwob_task_dir.as_posix().rstrip('/')}/"
        print(f"\n✓ Set MINIWOB_URL environment variable:")
        if sys.platform == "win32":
            print(f"  PowerShell: $env:MINIWOB_URL=\"{miniwob_url}\"")
        else:
            print(f"  Bash: export MINIWOB_URL=\"{miniwob_url}\"")
        
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"\n✗ Error downloading MiniWoB dataset: {e}")
        print(f"  Make sure git is installed and accessible")
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)
        return False
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)
        return False


def main():
    """Main setup entry point."""
    print("BrowserGym Green Agent - Local Dataset Setup")
    print("=" * 60)
    print("\nThis script downloads benchmark data for local development.")
    print("In Docker, benchmarks are automatically included during build.\n")
    
    # Check git availability
    try:
        subprocess.run(["git", "--version"], check=True, capture_output=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("✗ Error: git is not installed or not in PATH")
        print("  Please install git: https://git-scm.com/downloads")
        sys.exit(1)
    
    # Setup MiniWoB (only benchmark needed for local testing)
    success = setup_miniwob()
    
    if success:
        print("\n" + "="*60)
        print("✓ Local dataset setup complete!")
        print("="*60)
        print("\nYou can now run integration tests:")
        print("  pytest tests/unit/ -v")
        print("  python tests/integration/test_full_evaluation.py")
        print("\nNote: Other benchmarks (WebArena, WorkArena, etc.) require")
        print("      additional setup or use live websites.")
        sys.exit(0)
    else:
        print("\n" + "="*60)
        print("✗ Setup failed")
        print("="*60)
        sys.exit(1)


if __name__ == "__main__":
    main()
