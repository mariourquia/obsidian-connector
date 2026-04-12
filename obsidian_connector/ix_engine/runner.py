import os
import sys
import subprocess
from pathlib import Path

IX_ENGINE_DIR = Path(__file__).parent.resolve()
IX_CLI_DIR = IX_ENGINE_DIR / "ix-cli"
CORE_INGESTION_DIR = IX_ENGINE_DIR / "core-ingestion"


def _check_node_installed():
    try:
        subprocess.run(["node", "--version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        subprocess.run(["npm", "--version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("Error: Ix requires Node.js (>=20.0.0) and npm to be installed.", file=sys.stderr)
        print("Please install them from https://nodejs.org/ and try again.", file=sys.stderr)
        sys.exit(1)


def _setup_ix_if_needed():
    """Ensure Ix dependencies are installed and compiled."""
    _check_node_installed()

    # We check if `dist/cli/main.js` exists to determine if it's built
    main_js_path = IX_CLI_DIR / "dist" / "cli" / "main.js"
    if main_js_path.exists():
        return

    print("First run of `ix` detected. Initializing and building Ix engine (this may take a minute)...", file=sys.stderr)

    # Note: ix-cli's build script automatically runs `npm ci` and `npm run build` in core-ingestion
    # So we just need to run npm ci and npm run build in ix-cli.
    try:
        npm_cmd = "npm.cmd" if sys.platform == "win32" else "npm"
        subprocess.run([npm_cmd, "ci", "--silent"], cwd=str(IX_CLI_DIR), check=True)
        subprocess.run([npm_cmd, "run", "build"], cwd=str(IX_CLI_DIR), check=True)
        print("Ix engine built successfully.", file=sys.stderr)
    except subprocess.CalledProcessError as e:
        print(f"Failed to build Ix engine: {e}", file=sys.stderr)
        sys.exit(1)


def run_ix(args: list[str]) -> int:
    """Run the embedded Ix CLI with the given arguments."""
    _setup_ix_if_needed()
    
    main_js_path = IX_CLI_DIR / "dist" / "cli" / "main.js"
    
    cmd = ["node", str(main_js_path)] + args
    
    try:
        result = subprocess.run(cmd)
        return result.returncode
    except KeyboardInterrupt:
        return 130
    except Exception as e:
        print(f"Error running Ix: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    # If executed directly
    sys.exit(run_ix(sys.argv[1:]))
