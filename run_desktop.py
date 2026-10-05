"""
run_desktop.py — Desktop launcher for the AI PowerPoint Generator.

This is the main entry point compiled by PyInstaller into AI-Presentation-Engine.exe.
It handles:
1. Dynamic port assignment (finds an open port starting at 8501)
2. Headless Streamlit engine launch
3. Background polling and automatic browser opening
4. Clean, user-friendly console status messages for non-technical users
"""

import os
import socket
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

# Safe encoding for Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def get_base_dirs():
    """Return (app_dir, bundle_dir) depending on whether running frozen or as script."""
    if getattr(sys, "frozen", False):
        app_dir = Path(sys.executable).resolve().parent
        bundle_dir = Path(getattr(sys, "_MEIPASS", sys.executable)).resolve()
        if not bundle_dir.is_dir():
            bundle_dir = bundle_dir.parent
    else:
        app_dir = Path(__file__).resolve().parent
        bundle_dir = app_dir
    return app_dir, bundle_dir


def find_free_port(start_port: int = 8501, max_attempts: int = 25) -> int:
    """Find the first available localhost port starting from start_port."""
    for port in range(start_port, start_port + max_attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    return start_port


def wait_and_open_browser(url: str, timeout: int = 30) -> None:
    """Poll Streamlit's health endpoint and open the browser as soon as ready."""
    health_url = f"{url}/_stcore/health"
    start_time = time.time()
    opened = False

    while time.time() - start_time < timeout:
        try:
            req = urllib.request.Request(health_url, headers={"User-Agent": "AIPPTLauncher/1.0"})
            with urllib.request.urlopen(req, timeout=1) as resp:
                if resp.status == 200:
                    print(f"  [OK] Server is ready! Opening your web browser: {url}")
                    webbrowser.open(url)
                    opened = True
                    break
        except Exception:
            pass
        time.sleep(0.5)

    if not opened:
        # Fallback: open anyway after timeout
        print(f"  [INFO] Opening browser at: {url}")
        webbrowser.open(url)


def main():
    app_dir, bundle_dir = get_base_dirs()

    # Ensure project root is in sys.path
    for d in [str(bundle_dir), str(app_dir)]:
        if d not in sys.path:
            sys.path.insert(0, d)

    # Set working directory to app_dir so outputs and local files are placed next to the .exe
    os.chdir(app_dir)

    # Locate app.py
    candidate_paths = [
        bundle_dir / "app.py",
        app_dir / "app.py",
        bundle_dir / "_internal" / "app.py",
    ]
    app_path = None
    for p in candidate_paths:
        if p.exists():
            app_path = p
            break

    if not app_path:
        print("\n[ERROR] Could not locate application entry point (app.py).")
        print(f"Checked paths:\n  " + "\n  ".join(str(p) for p in candidate_paths))
        input("\nPress Enter to exit...")
        sys.exit(1)

    port = find_free_port(8501)
    app_url = f"http://localhost:{port}"

    print("=" * 72)
    print("  [*] AI PowerPoint Presentation Engine")
    print("  Corporate Edition -- Standalone Desktop App")
    print("=" * 72)
    print(f"  Status:  Starting application server...")
    print(f"  Port:    {port}")
    print(f"  Address: {app_url}")
    print("  Browser: Launching automatically...")
    print("-" * 72)
    print("  [!] IMPORTANT:")
    print("     - Keep this console window open while using the application.")
    print("     - If your browser doesn't open automatically, open:")
    print(f"       {app_url}")
    print("     - To close the application, simply close this console window.")
    print("=" * 72 + "\n")

    # Start browser launcher thread
    browser_thread = threading.Thread(
        target=wait_and_open_browser,
        args=(app_url,),
        daemon=True,
    )
    browser_thread.start()

    # Configure Streamlit
    try:
        from streamlit.web import bootstrap

        flag_options = {
            "server.port": port,
            "server.address": "127.0.0.1",
            "server.headless": True,
            "global.developmentMode": False,
            "browser.gatherUsageStats": False,
            "server.enableCORS": False,
            "server.enableXsrfProtection": False,
        }

        # Apply flags and run
        bootstrap.load_config_options(flag_options=flag_options)
        bootstrap.run(str(app_path), False, [], flag_options=flag_options)

    except KeyboardInterrupt:
        print("\n[INFO] Application closed by user.")
        sys.exit(0)
    except Exception as e:
        print(f"\n[FATAL ERROR] An unexpected error occurred: {e}")
        import traceback
        traceback.print_exc()
        input("\nPress Enter to exit...")
        sys.exit(1)


if __name__ == "__main__":
    main()
