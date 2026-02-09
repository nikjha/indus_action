"""
Configuration management for local and Docker environments
Handles environment-specific settings for development and production
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Load environment-specific .env files
# Priority: .env.local (local dev) > .env.{ENVIRONMENT} > .env (default)
env_path = Path(__file__).parent

def load_env_config():
    """Load environment configuration based on environment variable"""
    environment = os.getenv("ENVIRONMENT", "local")
    
    # Load .env.local first (local development)
    local_env = env_path / ".env.local"
    if local_env.exists():
        load_dotenv(local_env, override=True)
    
    # Load environment-specific .env
    env_file = env_path / f".env.{environment}"
    if env_file.exists():
        load_dotenv(env_file, override=True)
    
    # Load default .env
    default_env = env_path / ".env"
    if default_env.exists():
        load_dotenv(default_env, override=False)

class Config:
    """Base configuration"""
    ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
    DEBUG = os.getenv("DEBUG", "false").lower() == "true"
    
    # Database
    DB_HOST = os.getenv("DB_HOST", "db")
    DB_PORT = int(os.getenv("DB_PORT", "5433"))
    DB_USER = os.getenv("DB_USER", "app")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "app#123#")
    DB_NAME = os.getenv("DB_NAME", "taskdb")
    
    # Redis
    REDIS_URL = os.getenv("REDIS_URL", "redis://default:TKd5Nfb7390758iXfHTUo1qTZ0Pm4EeG@redis-15766.c330.asia-south1-1.gce.cloud.redislabs.com:15766")
    
    # Security
    AUTH_SECRET = os.getenv("AUTH_SECRET", "dev-secret-key")
    DOCS_USER = os.getenv("DOCS_USER", "docs")
    DOCS_PASS = os.getenv("DOCS_PASS", "docs123")
    
    # Logging
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    
    # Features
    USE_REDIS_CACHE = os.getenv("USE_REDIS_CACHE", "true").lower() == "true"
    ENABLE_ASYNC_TASKS = os.getenv("ENABLE_ASYNC_TASKS", "true").lower() == "true"
    
    @staticmethod
    def get_db_url():
        """Get database connection URL"""
        return f"postgresql://{Config.DB_USER}:{Config.DB_PASSWORD}@{Config.DB_HOST}:{Config.DB_PORT}/{Config.DB_NAME}"
    
    @staticmethod
    def get_redis_url():
        """Get Redis connection URL"""
        return Config.REDIS_URL
    
    @classmethod
    def from_env(cls):
        """Load configuration from environment"""
        load_env_config()
        return cls()

# Auto-load configuration on import
load_env_config()
