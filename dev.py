#!/usr/bin/env python
"""
Common development tasks helper script
Usage: python dev.py [command]

Examples:
  python dev.py setup
  python dev.py start
  python dev.py test
  python dev.py format
"""

import os
import subprocess
import sys
from pathlib import Path


def run_command(cmd, description=None):
    """Run a shell command and report results"""
    if description:
        print(f"\n{'='*60}")
        print(f"► {description}")
        print(f"{'='*60}")
    
    print(f"$ {' '.join(cmd)}\n")
    result = subprocess.run(cmd, shell=isinstance(cmd, str))
    
    if result.returncode != 0:
        print("\n Failed!")
        return False
    print("\n Done!")
    return True

def activate_venv():
    """Return the path to python in venv"""
    if sys.platform == "win32":
        return str(Path(__file__).parent / "venv" / "Scripts" / "python.exe")
    else:
        return str(Path(__file__).parent / "venv" / "bin" / "python")

def main():
    """Main entry point"""
    commands = {
        "setup": "Initialize development environment",
        "install": "Install Python dependencies",
        "db-init": "Initialize database schema",
        "start": "Start all services",
        "start-api": "Start API Gateway only",
        "test": "Run tests",
        "test-coverage": "Run tests with coverage report",
        "format": "Format code with ruff",
        "lint": "Lint code with ruff",
        "clean": "Clean Python cache files",
        "help": "Show this help message",
    }
    
    if len(sys.argv) < 2 or sys.argv[1] == "help":
        print("Development Tasks Helper")
        print("=" * 60)
        print("\nAvailable commands:\n")
        for cmd, desc in commands.items():
            print(f"  python dev.py {cmd:<20} {desc}")
        print("\n" + "=" * 60)
        return 0
    
    command = sys.argv[1].lower()
    
    # Verify virtual environment
    venv_path = Path(__file__).parent / "venv"
    if not venv_path.exists() and command != "setup":
        print("ERROR: Virtual environment not found!")
        print("Run: python dev.py setup")
        return 1
    
    python_exe = activate_venv()
    
    # Execute commands
    try:
        if command == "setup":
            print("Setting up development environment...")
            if not run_command(f"{python_exe} -m venv venv", "Creating virtual environment"):
                return 1
            if not run_command(f"{python_exe} -m pip install --upgrade pip setuptools wheel", "Upgrading pip"):
                return 1
            if not run_command(f"{python_exe} -m pip install -r dev-requirements.txt", "Installing dev requirements"):
                return 1
            print("\n Setup complete! Run: python dev.py install")
            return 0
        
        elif command == "install":
            if not run_command(f"{python_exe} -m pip install -r dev-requirements.txt", "Installing dev requirements"):
                return 1
            # Install service requirements
            services = [
                "api_gateway", "auth_service", "user_service",
                "task_service", "eligibility_engine", "worker"
            ]
            for service in services:
                req_file = f"services/{service}/requirements.txt"
                if Path(req_file).exists():
                    if not run_command(
                        f"{python_exe} -m pip install -r {req_file}",
                        f"Installing {service} requirements"
                    ):
                        return 1
            return 0
        
        elif command == "db-init":
            db_user = os.getenv("DB_USER", "app")
            db_host = os.getenv("DB_HOST", "localhost")
            db_name = os.getenv("DB_NAME", "appdb")
            
            print("Initializing database...")
            cmd = f"psql -h {db_host} -U {db_user} -d {db_name} -f db/init.sql"
            return 0 if run_command(cmd, "Running database initialization") else 1
        
        elif command == "start":
            cmd = f"{python_exe} run_services.py start all --verbose"
            return 0 if run_command(cmd, "Starting all services") else 1
        
        elif command == "start-api":
            os.environ["ENVIRONMENT"] = "local"
            cmd = f"{python_exe} -m uvicorn services.api_gateway.app.main:app --reload --port 8000"
            return 0 if run_command(cmd, "Starting API Gateway") else 1
        
        elif command == "test":
            cmd = f"{python_exe} -m pytest tests/ -v"
            return 0 if run_command(cmd, "Running tests") else 1
        
        elif command == "test-coverage":
            cmd = f"{python_exe} -m pytest tests/ -v --cov=services --cov-report=html"
            result = run_command(cmd, "Running tests with coverage")
            if result:
                print("\n Coverage report generated: htmlcov/index.html")
            return 0 if result else 1
        
        elif command == "format":
            cmd = f"{python_exe} -m ruff format ."
            return 0 if run_command(cmd, "Formatting code") else 1
        
        elif command == "lint":
            cmd = f"{python_exe} -m ruff check . --line-length=100"
            return 0 if run_command(cmd, "Linting code") else 1
        
        elif command == "clean":
            print("Cleaning cache files...")
            for pattern in ["**/__pycache__", "**/*.pyc", ".pytest_cache", ".ruff_cache"]:
                import glob
                for path in glob.glob(pattern, recursive=True):
                    if os.path.isfile(path):
                        os.remove(path)
                        print(f"  Removed: {path}")
                    elif os.path.isdir(path):
                        import shutil
                        shutil.rmtree(path)
                        print(f"  Removed: {path}")
            print(" Clean complete!")
            return 0
        
        else:
            print(f"ERROR: Unknown command '{command}'")
            print("Run: python dev.py help")
            return 1
    
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        return 130
    except Exception as e:
        print(f"\nERROR: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
