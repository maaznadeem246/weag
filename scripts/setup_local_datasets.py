"""
Setup script for local development - downloads benchmark datasets.

Run this script once before running tests locally:
    python scripts/setup_local_datasets.py

For Docker, benchmarks are automatically downloaded during build.

Downloads:
- MiniWoB++: HTML task files from GitHub (sparse checkout)
- WebLINX: metadata.json from HuggingFace (~106MB)
"""

import json
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
    datasets_dir = project_root / "green-agent" / "datasets"
    miniwob_dir = datasets_dir / "miniwob"
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
    datasets_dir.mkdir(parents=True, exist_ok=True)
    
    # Clone with sparse checkout for efficiency
    temp_dir = datasets_dir / "temp_miniwob"
    
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


def setup_weblinx():
    """Download WebLINX metadata for local development.

    Downloads the metadata.json (~106MB) from HuggingFace which contains
    task definitions for all WebLINX splits. The actual demo data (screenshots,
    HTML snapshots) is downloaded on-demand when tasks are run.
    """
    print("\n" + "="*60)
    print("Setting up WebLINX dataset for local development")
    print("="*60 + "\n")

    project_root = Path(__file__).parent.parent
    datasets_dir = project_root / "green-agent" / "datasets" / "weblinx"
    metadata_path = datasets_dir / "metadata.json"

    # Check if already exists
    if metadata_path.exists():
        size_mb = metadata_path.stat().st_size / (1024 * 1024)
        print(f"✓ WebLINX metadata already exists at: {metadata_path}")
        print(f"  Size: {size_mb:.1f} MB")

        # Quick validation
        try:
            with open(metadata_path, "r") as f:
                meta = json.load(f)
            splits = list(meta.keys())
            print(f"  Splits: {', '.join(splits)}")
        except Exception:
            pass

        print(f"\n✓ Set BROWSERGYM_WEBLINX_CACHE_DIR environment variable:")
        if sys.platform == "win32":
            print(f'  PowerShell: $env:BROWSERGYM_WEBLINX_CACHE_DIR="{datasets_dir}"')
        else:
            print(f'  Bash: export BROWSERGYM_WEBLINX_CACHE_DIR="{datasets_dir}"')
        return True

    print(f"Downloading WebLINX metadata to: {datasets_dir}")
    datasets_dir.mkdir(parents=True, exist_ok=True)

    try:
        from huggingface_hub import hf_hub_download

        print("[1/1] Downloading metadata.json from HuggingFace (~106MB)...")
        hf_hub_download(
            repo_id="McGill-NLP/weblinx-browsergym",
            repo_type="dataset",
            filename="metadata.json",
            local_dir=str(datasets_dir),
        )

        if metadata_path.exists():
            size_mb = metadata_path.stat().st_size / (1024 * 1024)
            print(f"\n✓ Successfully downloaded WebLINX metadata ({size_mb:.1f} MB)")
            print(f"✓ Dataset location: {datasets_dir}")
        else:
            print("\n✗ Download completed but metadata.json not found")
            return False

        print(f"\n✓ Set BROWSERGYM_WEBLINX_CACHE_DIR environment variable:")
        if sys.platform == "win32":
            print(f'  PowerShell: $env:BROWSERGYM_WEBLINX_CACHE_DIR="{datasets_dir}"')
        else:
            print(f'  Bash: export BROWSERGYM_WEBLINX_CACHE_DIR="{datasets_dir}"')

        return True

    except ImportError:
        print("\n✗ huggingface_hub not installed.")
        print("  Install with: pip install huggingface_hub")
        return False
    except Exception as e:
        print(f"\n✗ Error downloading WebLINX metadata: {e}")
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

    results = {}

    # Setup MiniWoB
    results["miniwob"] = setup_miniwob()

    # Setup WebLINX
    results["weblinx"] = setup_weblinx()

    # Summary
    all_ok = all(results.values())
    print("\n" + "="*60)
    print("SETUP SUMMARY")
    print("="*60)
    for name, ok in results.items():
        status = "✓" if ok else "✗"
        print(f"  {status} {name}")

    if all_ok:
        print("\n✓ All datasets setup complete!")
        print("\nYou can now run assessments:")
        print("  python kickstart_assessment.py --task miniwob.click-test")
        print("  python kickstart_assessment.py --task weblinx.scicrdo.1")
        sys.exit(0)
    else:
        failed = [n for n, ok in results.items() if not ok]
        print(f"\n✗ Some datasets failed to setup: {', '.join(failed)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
