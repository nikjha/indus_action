#!/usr/bin/env python
"""
Service manager for local Windows development
Helps to start, stop, and manage multiple services
"""

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

# Set environment to local development
os.environ["ENVIRONMENT"] = "local"
os.environ["DEBUG"] = "true"

# Load .env.local
from dotenv import load_dotenv

env_path = Path(__file__).parent / ".env.local"
fallback_env_path = Path(__file__).parent / "env_local_work.txt"

if not env_path.exists():
    if fallback_env_path.exists():
        print("Creating .env.local from env_local_work.txt...", file=sys.stderr)
        env_path.write_text(fallback_env_path.read_text())
    else:
        print("env_local_work.txt not found. No environment file loaded.", file=sys.stderr)


if env_path.exists():
    load_dotenv(env_path, override=True)

class ServiceManager:
    """Manages local development services"""
    
    SERVICES: dict[str, dict] = {
        "api-gateway": {
            "port": 8000,
            "module": "services.api_gateway.app.main",
            "startup": "api_gateway.app.main:app",
            "description": "API Gateway - Main entry point"
        },
        "auth-service": {
            "port": 8001,
            "module": "services.auth_service.app.main",
            "startup": "auth_service.app.main:app",
            "description": "Authentication Service"
        },
        "user-service": {
            "port": 8002,
            "module": "services.user_service.app.main",
            "startup": "user_service.app.main:app",
            "description": "User Management Service"
        },
        "task-service": {
            "port": 8003,
            "module": "services.task_service.app.main",
            "startup": "task_service.app.main:app",
            "description": "Task Service"
        },
        "eligibility-engine": {
            "port": 8004,
            "module": "services.eligibility_engine.app.main",
            "startup": "eligibility_engine.app.main:app",
            "description": "Eligibility Engine"
        },
        "worker": {
            "port": 5000,
            "module": "services.worker.app.worker",
            "startup": "worker.app.worker",
            "description": "Background Task Worker"
        }
    }
    
    def __init__(self):
        self.processes: dict[str, subprocess.Popen] = {}
        self.project_root = Path(__file__).parent
        
    def get_service_config(self, service_name: str) -> dict | None:
        """Get configuration for a service"""
        return self.SERVICES.get(service_name)
    
    def validate_service(self, service_name: str) -> bool:
        """Validate that service exists"""
        if service_name not in self.SERVICES:
            print(f"ERROR: Unknown service '{service_name}'", file=sys.stderr)
            print(f"Available services: {', '.join(self.SERVICES.keys())}", file=sys.stderr)
            return False
        return True
    
    def start_service(self, service_name: str, verbose: bool = False) -> bool:
        """Start a specific service"""
        if not self.validate_service(service_name):
            return False
        
        config = self.get_service_config(service_name)
        port = config["port"]
        
        print(f"Starting {service_name} (port {port})...", file=sys.stderr)
        
        # Change to services directory
        service_path = self.project_root / "services"
        
        # Build uvicorn command for FastAPI apps or direct Python for worker
        if "worker" in service_name:
            cmd = [
                sys.executable,
                str(self.project_root / "services" / "worker" / "app" / "worker.py")
            ]
        else:
            service_dir = service_name.replace("-", "_")
            cmd = [
                sys.executable,
                "-m", "uvicorn",
                f"{service_dir}.app.main:app",
                "--host", "0.0.0.0",
                "--port", str(port),
                "--reload" if verbose else "",
            ]
            # Remove empty string from reload if not verbose
            cmd = [x for x in cmd if x]
        
        try:
            env = os.environ.copy()
            env["ENVIRONMENT"] = "local"
            env["DEBUG"] = "true"
            
            # Set service-specific port if needed
            if service_name == "api-gateway":
                env["API_GATEWAY_PORT"] = str(port)
            elif service_name == "auth-service":
                env["AUTH_SERVICE_PORT"] = str(port)
            elif service_name == "user-service":
                env["USER_SERVICE_PORT"] = str(port)
            elif service_name == "task-service":
                env["TASK_SERVICE_PORT"] = str(port)
            elif service_name == "eligibility-engine":
                env["ELIGIBILITY_ENGINE_PORT"] = str(port)
            
            process = subprocess.Popen(
                cmd,
                cwd=str(service_path),
                env=env,
                stdout=sys.stdout if verbose else subprocess.DEVNULL,
                stderr=sys.stderr if verbose else subprocess.DEVNULL
            )
            
            self.processes[service_name] = process
            print(f" {service_name} started (PID: {process.pid})", file=sys.stderr)
            return True
            
        except Exception as e:
            print(f"ERROR: Failed to start {service_name}: {e}", file=sys.stderr)
            return False
    
    def stop_service(self, service_name: str) -> bool:
        """Stop a specific service"""
        if service_name not in self.processes:
            print(f"ERROR: {service_name} is not running", file=sys.stderr)
            return False
        
        process = self.processes[service_name]
        print(f"Stopping {service_name}...", file=sys.stderr)
        
        try:
            process.terminate()
            process.wait(timeout=5)
            print(f" {service_name} stopped", file=sys.stderr)
            del self.processes[service_name]
            return True
        except subprocess.TimeoutExpired:
            print(f"Force killing {service_name}...", file=sys.stderr)
            process.kill()
            process.wait()
            del self.processes[service_name]
            return True
        except Exception as e:
            print(f"ERROR: Failed to stop {service_name}: {e}", file=sys.stderr)
            return False
    
    def start_all(self, verbose: bool = False) -> bool:
        """Start all services"""
        print("Starting all services...", file=sys.stderr)
        failed = []
        
        for service_name in self.SERVICES.keys():
            if not self.start_service(service_name, verbose):
                failed.append(service_name)
            time.sleep(2)  # Give each service time to start
        
        if failed:
            print(f"WARNING: Failed to start: {', '.join(failed)}", file=sys.stderr)
            return len(failed) < len(self.SERVICES)
        
        print(" All services started successfully!", file=sys.stderr)
        return True 
    
    def stop_all(self) -> bool:
        """Stop all running services"""
        print("Stopping all services...", file=sys.stderr)
        
        for service_name in list(self.processes.keys()):
            self.stop_service(service_name)
        
        print(" All services stopped", file=sys.stderr)
        return True
    
    def list_services(self) -> None:
        """List all available services"""
        print("Available Services:", file=sys.stderr)
        print("-" * 60, file=sys.stderr)
        
        for service_name, config in self.SERVICES.items():
            running = " RUNNING" if service_name in self.processes else "  stopped"
            print(f"{service_name:20} {config['description']:30} [Port: {config['port']}] {running}", file=sys.stderr)
    
    def show_help(self) -> None:
        """Show help message"""
        help_text = """
Local Development Service Manager
==================================

Usage: python run_services.py [command] [options]

Commands:
  start [SERVICE]      Start a service or all services
  stop [SERVICE]       Stop a service or all services
  restart [SERVICE]    Restart a service or all services
  list                 List all available services
  status               Show status of all services
  help                 Show this help message

Services:
  api-gateway          API Gateway (port 8000)
  auth-service         Authentication Service (port 8001)
  user-service         User Management Service (port 8002)
  task-service         Task Service (port 8003)
  eligibility-engine   Eligibility Engine (port 8004)
  worker               Background Worker (port 5000)

Options:
  -v, --verbose        Show service output
  -h, --help          Show this help message

Examples:
  python run_services.py start all
  python run_services.py start api-gateway --verbose
  python run_services.py stop user-service
  python run_services.py list
  python run_services.py status

Requirements:
  1. PostgreSQL must be running on localhost:5432
  2. Redis must be running on localhost:6379
  3. All Python dependencies must be installed

To setup the environment, run:
  python -m pip install -r requirements_spec.md
  python -m pip install -r dev-requirements.txt

"""
        print(help_text, file=sys.stderr)


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="Local Development Service Manager", add_help=False)
    parser.add_argument("command", nargs="?", default="help", help="Command to execute")
    parser.add_argument("service", nargs="?", default="all", help="Service name or 'all'")
    parser.add_argument("-v", "--verbose", action="store_true", help="Show service output")
    parser.add_argument("-h", "--help", action="store_true", help="Show help message")
    
    args = parser.parse_args()
    
    manager = ServiceManager()
    
    if args.help or args.command == "help":
        manager.show_help()
        return 0
    
    try:
        if args.command == "start":
            if args.service == "all":
                success = manager.start_all(args.verbose)
            else:
                success = manager.start_service(args.service, args.verbose)
            
            if success:
                try:
                    # Keep running until interrupted
                    while True:
                        time.sleep(1)
                except KeyboardInterrupt:
                    print("\nShutting down services...", file=sys.stderr)
                    manager.stop_all()
                    return 0
            else:
                return 1
        
        elif args.command == "stop":
            if args.service == "all":
                manager.stop_all()
            else:
                manager.stop_service(args.service)
            return 0
        
        elif args.command == "list":
            manager.list_services()
            return 0
        
        elif args.command == "status":
            manager.list_services()
            return 0
        
        else:
            print(f"Unknown command: {args.command}", file=sys.stderr)
            manager.show_help()
            return 1
    
    except KeyboardInterrupt:
        print("\nInterrupted by user", file=sys.stderr)
        manager.stop_all()
        return 0
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
