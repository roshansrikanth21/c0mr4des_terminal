#!/usr/bin/env python3
"""
Simple setup script for AI Trading System.
Migrates existing API keys to secure encrypted storage.
"""

import os
import sys
from pathlib import Path

# Add backend to path
backend_path = Path(__file__).parent / "backend"
sys.path.insert(0, str(backend_path))

def setup_secure_configuration():
    """Migrate existing API keys to secure storage"""
    print("Setting up secure configuration for AI Trading System...")
    
    try:
        from config.secure_config import config_manager
        print("Secure config manager imported successfully")
    except ImportError as e:
        print(f"Failed to import secure config: {e}")
        return False
    
    # Check existing .env file
    env_path = backend_path / ".env"
    if not env_path.exists():
        print("No .env file found. Please create one with your API keys.")
        return False
    
    print(f"Found .env file: {env_path}")
    
    # Load existing environment variables
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=env_path)
    
    # Get Gemini API key (the one you already have)
    gemini_key = os.getenv("GEMINI_API_KEY")
    
    if gemini_key:
        print("Migrating GEMINI API key...")
        try:
            config_manager.store_api_key("gemini", gemini_key)
            print("Gemini key stored securely")
            return True
        except Exception as e:
            print(f"Failed to store Gemini key: {e}")
            return False
    else:
        print("No GEMINI_API_KEY found in .env file")
        return False

def test_configuration():
    """Test the secure configuration"""
    print("Testing secure configuration...")
    
    try:
        from config.secure_config import config_manager
        
        # Test API key retrieval
        gemini_key = config_manager.get_api_key("gemini")
        if gemini_key:
            print("Gemini API key retrieved successfully")
            print(f"Key starts with: {gemini_key[:10]}...")
            return True
        else:
            print("Gemini API key not found")
            return False
        
    except Exception as e:
        print(f"Configuration test failed: {e}")
        return False

def main():
    """Main setup process"""
    print("AI Trading System - Secure Setup")
    print("=" * 50)
    
    # Step 1: Setup secure configuration
    if not setup_secure_configuration():
        print("Secure configuration setup failed")
        return False
    
    # Step 2: Test configuration
    if not test_configuration():
        print("Configuration test failed")
        return False
    
    print("\nSetup completed successfully!")
    print("\nNext steps:")
    print("1. Start Redis server (optional): docker run -d -p 6379:6379 redis:alpine")
    print("2. Run tests: python backend/tests/test_trading_system.py")
    print("3. Start the system: python backend/main_refactored.py")
    
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)