#!/usr/bin/env python3
"""Display current access logs from database"""

import os

import psycopg2
from dotenv import load_dotenv

load_dotenv(".env.local")

db_host = os.getenv("DB_HOST", "localhost")
db_port = int(os.getenv("DB_PORT", "5433"))
db_user = os.getenv("DB_USER", "app")
db_password = os.getenv("DB_PASSWORD", "app")
db_name = os.getenv("DB_NAME", "appdb")

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
    
    # Check if table exists
    cur.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_name = 'access_logs'
        );
    """)
    
    if not cur.fetchone()[0]:
        print("✗ access_logs table does not exist")
        cur.close()
        conn.close()
        exit(1)
    
    # Get count
    cur.execute("SELECT COUNT(*) FROM access_logs;")
    count = cur.fetchone()[0]
    print(f"\n📊 Total Access Logs: {count}\n")
    
    if count == 0:
        print("No logs found. Start the services and make some requests.")
        cur.close()
        conn.close()
        exit(0)
    
    # Show recent logs
    print("📋 Last 10 Access Logs:")
    print("=" * 120)
    cur.execute("""
        SELECT id, service, method, path, status, time_ms, created_at
        FROM access_logs 
        ORDER BY created_at DESC 
        LIMIT 10
    """)
    
    for row in cur.fetchall():
        log_id, service, method, path, status, time_ms, created_at = row
        print(f"[{log_id:5}] {created_at.strftime('%Y-%m-%d %H:%M:%S')} | {service:18} | {method:6} | {status:3} | {time_ms:5}ms")
        print(f"        Path: {path}")
        print()
    
    print("\n📈 Logs by Service:")
    print("-" * 40)
    cur.execute("""
        SELECT service, COUNT(*) as count
        FROM access_logs
        GROUP BY service
        ORDER BY count DESC
    """)
    
    for service, count in cur.fetchall():
        print(f"  {service:20}: {count:5} logs")
    
    print("\n📊 Logs by Status Code:")
    print("-" * 40)
    cur.execute("""
        SELECT status, COUNT(*) as count
        FROM access_logs
        GROUP BY status
        ORDER BY status
    """)
    
    for status, count in cur.fetchall():
        status_text = {
            200: "✓ OK",
            201: "✓ Created",
            400: "✗ Bad Request",
            401: "✗ Unauthorized",
            403: "✗ Forbidden",
            404: "✗ Not Found",
            500: "✗ Server Error"
        }.get(status, "? Unknown")
        print(f"  {status:3} {status_text:20}: {count:5} logs")
    
    print("\n⏱️  Average Response Time:")
    print("-" * 40)
    cur.execute("""
        SELECT service, ROUND(AVG(time_ms)::numeric, 2) as avg_time
        FROM access_logs
        GROUP BY service
        ORDER BY avg_time DESC
    """)
    
    for service, avg_time in cur.fetchall():
        print(f"  {service:20}: {avg_time:6}ms")
    
    cur.close()
    conn.close()
    
except Exception as e:
    print(f"✗ Error: {e}")
    import traceback
    traceback.print_exc()
