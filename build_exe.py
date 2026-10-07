"""
build_exe.py — Automated build & packaging script for AI Presentation Engine.

Usage:
    python build_exe.py
"""

import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

# Safe encoding for Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def main():
    root_dir = Path(__file__).resolve().parent
    spec_file = root_dir / "ai_ppt_engine.spec"
    dist_dir = root_dir / "dist"
    build_dir = root_dir / "build"
    app_dist_dir = dist_dir / "AI-Presentation-Engine"

    print("=" * 72)
    print("  [*] Building Standalone Windows Executable (.exe)")
    print("=" * 72)
    print(f"  Project Root: {root_dir}")
    print(f"  Python:       {sys.executable}")
    print(f"  Spec File:    {spec_file}")
    print("-" * 72)

    # 1. Run PyInstaller
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        str(spec_file),
        "--clean",
        "--noconfirm",
    ]
    print(f"\n[1/4] Running PyInstaller...")
    result = subprocess.run(cmd, cwd=root_dir)
    if result.returncode != 0:
        print(f"\n[ERROR] PyInstaller build failed with exit code {result.returncode}")
        sys.exit(result.returncode)

    if not app_dist_dir.is_dir():
        print(f"\n[ERROR] Expected output directory not found: {app_dist_dir}")
        sys.exit(1)

    print("\n[2/4] Setting up client distribution folders...")

    # 2. Ensure user directories exist in the distribution folder
    output_dir = app_dist_dir / "output"
    logs_dir = app_dist_dir / "logs" / "llm"
    output_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    # 3. Copy .env or .env.example (ensuring latest active .env is bundled)
    env_target = app_dist_dir / ".env"
    if (root_dir / ".env").exists():
        shutil.copy2(root_dir / ".env", env_target)
        print("  - Copied active .env to distribution folder")
    elif (root_dir / ".env.example").exists() and not env_target.exists():
        shutil.copy2(root_dir / ".env.example", env_target)
        print("  - Copied .env.example to distribution folder as .env")

    # 4. Copy templates folder to user level if not fully bundled
    user_templates_dir = app_dist_dir / "templates"
    if not user_templates_dir.exists() and (root_dir / "templates").exists():
        shutil.copytree(root_dir / "templates", user_templates_dir)
        print("  - Copied templates/ folder to distribution root for user access")

    # 5. Create HOW_TO_RUN.txt for business users
    instructions_file = app_dist_dir / "HOW_TO_RUN.txt"
    instructions_text = """========================================================================
  AI PowerPoint Presentation Engine — Quick Start Guide
========================================================================

1. HOW TO START:
   - Double-click "AI-Presentation-Engine.exe" in this folder.
   - A status window will open, and your web browser will automatically 
     launch with the AI Presentation Engine.
   - Keep the status window open while using the application.

2. GENERATE POWERPOINTS:
   - Upload a document (.pdf, .docx, .txt, .xlsx) or enter a prompt.
   - Choose your template, audience, and slide count.
   - Click "Generate Presentation".
   - When finished, click "Download Presentation (.pptx)".
   - All generated presentations are also saved in the "output" folder.

3. HOW TO CLOSE:
   - Simply close the status window or close your browser tab.
========================================================================
"""
    instructions_file.write_text(instructions_text, encoding="utf-8")
    print("  - Generated HOW_TO_RUN.txt user guide")

    # 6. Compress into portable ZIP
    print("\n[3/4] Creating client portable ZIP archive...")
    zip_path = dist_dir / "AI-Presentation-Engine-v1.0.zip"
    if zip_path.exists():
        zip_path.unlink()

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in app_dist_dir.rglob("*"):
            arcname = file_path.relative_to(dist_dir)
            zf.write(file_path, arcname)

    zip_size_mb = zip_path.stat().st_size / (1024 * 1024)
    print(f"  - Created {zip_path.name} ({zip_size_mb:.1f} MB)")

    print("\n[4/4] Build Completed Successfully!")
    print("=" * 72)
    print(f"  Distribution Folder: {app_dist_dir}")
    print(f"  Executable File:     {app_dist_dir / 'AI-Presentation-Engine.exe'}")
    print(f"  Portable ZIP File:   {zip_path} ({zip_size_mb:.1f} MB)")
    print("=" * 72)


if __name__ == "__main__":
    main()
