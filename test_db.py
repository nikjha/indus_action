#!/usr/bin/env python3
"""Test database connectivity and access_logs table"""

import json
import os

import psycopg2
from dotenv import load_dotenv

# Load environment
load_dotenv(".env.local")

db_host = os.getenv("DB_HOST", "localhost")
db_port = int(os.getenv("DB_PORT", "5433"))
db_user = os.getenv("DB_USER", "app")
db_password = os.getenv("DB_PASSWORD", "app")
db_name = os.getenv("DB_NAME", "appdb")

print(f"Connecting to {db_user}@{db_host}:{db_port}/{db_name}")

try:
    conn = psycopg2.connect(
        host=db_host,
        port=db_port,
        user=db_user,
        password=db_password,
        dbname=db_name,
        connect_timeout=5
    )
    print(" Database connection successful")
    
    cur = conn.cursor()
    
    # Check if access_logs table exists
    cur.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_name = 'access_logs'
        );
    """)
    exists = cur.fetchone()[0]
    print(f" access_logs table exists: {exists}")
    
    if not exists:
        print("Creating access_logs table...")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS access_logs (
                id BIGSERIAL PRIMARY KEY,
                service TEXT NOT NULL,
                method TEXT NOT NULL,
                path TEXT NOT NULL,
                status INTEGER,
                time_ms INTEGER,
                req_headers JSONB,
                req_body TEXT,
                resp_headers JSONB,
                resp_body TEXT,
                created_at TIMESTAMP NOT NULL DEFAULT NOW()
            );
        """)
        conn.commit()
        print(" access_logs table created")
    
    # Try inserting a test record
    print("\nInserting test record...")
    headers = json.dumps({"content-type": "application/json"})
    cur.execute(
        "INSERT INTO access_logs (service, method, path, status, time_ms, req_headers, req_body, resp_headers, resp_body) VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s,%s::jsonb,%s);",
        ("test-service", "POST", "/test", 200, 100, headers, "test body", headers, "test response"),
    )
    conn.commit()
    print(" Test record inserted")
    
    # Query records
    cur.execute("SELECT COUNT(*) FROM access_logs;")
    count = cur.fetchone()[0]
    print(f" Total records in access_logs: {count}")
    
    cur.execute("SELECT id, service, method, path, status FROM access_logs ORDER BY created_at DESC LIMIT 3;")
    print("\nLast 3 records:")
    for row in cur.fetchall():
        print(f"  {row}")
    
    cur.close()
    conn.close()
    print("\n All tests passed!")
    
except Exception as e:
    print(f" Error: {e}")
    import traceback
    traceback.print_exc()
