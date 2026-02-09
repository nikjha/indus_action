#!/usr/bin/env python3
"""Verify database and services status"""

import os

import psycopg2
from dotenv import load_dotenv

load_dotenv(".env.local")

def check_postgres():
    """Check PostgreSQL connectivity"""
    db_host = os.getenv("DB_HOST", "localhost")
    db_port = int(os.getenv("DB_PORT", "5433"))
    db_user = os.getenv("DB_USER", "app")
    db_password = os.getenv("DB_PASSWORD", "app#123#")
    db_name = os.getenv("DB_NAME", "taskdb")
    
    try:
        conn = psycopg2.connect(
            host=db_host,
            port=db_port,
            user=db_user,
            password=db_password,
            dbname=db_name,
            connect_timeout=5
        )
        
        cur = conn.cursor()
        cur.execute("SELECT VERSION();")
        version = cur.fetchone()[0]
        print(f"PostgreSQL Connected: {version.split(',')[0]}")
        
        # Check access_logs table
        cur.execute("""
            SELECT COUNT(*) FROM information_schema.tables 
            WHERE table_name = 'access_logs'
        """)
        if cur.fetchone()[0]:
            cur.execute("SELECT COUNT(*) FROM access_logs")
            count = cur.fetchone()[0]
            print(f"access_logs table exists with {count} records")
        else:
            print("access_logs table does not exist")
        
        cur.close()
        conn.close()
        return True
    except Exception as e:
        print(f"PostgreSQL Error: {e}")
        return False

def check_redis():
    """Check Redis connectivity"""
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
    try:
        import redis
        r = redis.from_url(redis_url)
        r.ping()
        print(f"Redis Connected: {redis_url.split('@')[-1]}")
        return True
    except Exception as e:
        print(f"Redis Error: {e}")
        return False

def check_services():
    """Check if services are running"""
    services = [
        ("API Gateway", "http://localhost:8000/health"),
        ("Auth Service", "http://localhost:8001/health"),
        ("User Service", "http://localhost:8002/health"),
        ("Task Service", "http://localhost:8003/health"),
        ("Eligibility Engine", "http://localhost:8004/health"),
    ]
    
    for name, url in services:
        try:
            import subprocess
            result = subprocess.run(
                ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", url],
                capture_output=True,
                timeout=2
            )
            if result.returncode == 0:
                print(f"✓ {name} (port {url.split(':')[-1].split('/')[0]})")
            else:
                print(f"✗ {name} - curl error {result.returncode}")
        except Exception as e:
            print(f"✗ {name} - Error: {e}")

if __name__ == "__main__":
    print("=== System Status Check ===\n")
    check_postgres()
    print()
    check_redis()
    print()
    print("Checking services...")
    check_services()
