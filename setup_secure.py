#!/usr/bin/env python3
"""
Secure setup script for AI Trading System.
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
    print("🔒 Setting up secure configuration for AI Trading System...")
    
    try:
        from config.secure_config import config_manager
        print("✅ Secure config manager imported successfully")
    except ImportError as e:
        print(f"❌ Failed to import secure config: {e}")
        return False
    
    # Check existing .env file
    env_path = backend_path / ".env"
    if not env_path.exists():
        print("⚠️  No .env file found. Creating secure configuration...")
        return create_new_secure_config()
    
    print(f"📄 Found .env file: {env_path}")
    
    # Load existing environment variables
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=env_path)
    
    # Migrate API keys
    api_keys = {
        'gemini': os.getenv("GEMINI_API_KEY"),
        'alpha_vantage': os.getenv("ALPHA_VANTAGE_API_KEY"),
        'angel_one': os.getenv("ANGEL_ONE_API_KEY"),
        'zerodha': os.getenv("ZERODHA_API_KEY"),
        'upstox': os.getenv("UPSTOX_API_KEY")
    }
    
    migrated_keys = []
    for service, key in api_keys.items():
        if key:
            print(f"🔐 Migrating {service.upper()} API key...")
            try:
                config_manager.store_api_key(service, key)
                migrated_keys.append(service)
                print(f"✅ {service.upper()} key stored securely")
            except Exception as e:
                print(f"❌ Failed to store {service} key: {e}")
        else:
            print(f"⚠️  No {service.upper()} API key found")
    
    if migrated_keys:
        print(f"\n🎉 Successfully migrated {len(migrated_keys)} API keys to secure storage!")
        print("📝 Keys are now encrypted and stored in system keyring")
        
        # Ask if user wants to remove from .env
        response = input("\n❓ Remove API keys from .env file for security? (y/N): ").strip().lower()
        if response in ['y', 'yes']:
            backup_env_file(env_path, migrated_keys)
            clean_env_file(env_path, api_keys)
            print("🗑️  API keys removed from .env file (backup created)")
        
        return True
    else:
        print("❌ No API keys found to migrate")
        return False

def create_new_secure_config():
    """Create new secure configuration from user input"""
    print("\n🔧 Creating new secure configuration...")
    
    api_keys = {}
    
    # Collect API keys from user
    gemini_key = input("Enter Gemini API key (or press Enter to skip): ").strip()
    if gemini_key:
        api_keys['gemini'] = gemini_key
    
    alpha_vantage_key = input("Enter Alpha Vantage API key (optional): ").strip()
    if alpha_vantage_key:
        api_keys['alpha_vantage'] = alpha_vantage_key
    
    # Store keys securely
    from config.secure_config import config_manager
    
    for service, key in api_keys.items():
        try:
            config_manager.store_api_key(service, key)
            print(f"✅ {service.upper()} key stored securely")
        except Exception as e:
            print(f"❌ Failed to store {service} key: {e}")
            return False
    
    if api_keys:
        print("\n🎉 Secure configuration created successfully!")
        print("📝 Keys are encrypted and stored in system keyring")
        return True
    
    return False

def backup_env_file(env_path, migrated_keys):
    """Create backup of .env file before cleaning"""
    backup_path = env_path.with_suffix('.env.backup')
    
    try:
        with open(env_path, 'r') as original, open(backup_path, 'w') as backup:
            backup.write(original.read())
        print(f"📋 Backup created: {backup_path}")
    except Exception as e:
        print(f"⚠️  Could not create backup: {e}")

def clean_env_file(env_path, api_keys):
    """Remove API keys from .env file"""
    try:
        with open(env_path, 'r') as f:
            lines = f.readlines()
        
        # Filter out API key lines
        cleaned_lines = []
        for line in lines:
            should_remove = False
            for service in api_keys.keys():
                if line.startswith(f"{service.upper()}_API_KEY="):
                    should_remove = True
                    break
            
            if not should_remove:
                cleaned_lines.append(line)
        
        with open(env_path, 'w') as f:
            f.writelines(cleaned_lines)
            
    except Exception as e:
        print(f"⚠️  Could not clean .env file: {e}")

def test_configuration():
    """Test the secure configuration"""
    print("\n🧪 Testing secure configuration...")
    
    try:
        from config.secure_config import config_manager
        from services.image_analysis_service import image_analysis_service
        
        # Test configuration
        config = config_manager.get_config()
        print("✅ Configuration loaded successfully")
        
        # Test API key retrieval
        gemini_key = config_manager.get_api_key("gemini")
        if gemini_key:
            print("✅ Gemini API key retrieved successfully")
        else:
            print("⚠️  Gemini API key not found")
        
        # Test image analysis service initialization
        if image_analysis_service.client:
            print("✅ Image analysis service initialized successfully")
        else:
            print("⚠️  Image analysis service could not initialize")
        
        print("\n🎯 Configuration test completed!")
        return True
        
    except Exception as e:
        print(f"❌ Configuration test failed: {e}")
        return False

def main():
    """Main setup process"""
    print("🚀 AI Trading System - Secure Setup")
    print("=" * 50)
    
    # Step 1: Setup secure configuration
    if not setup_secure_configuration():
        print("❌ Secure configuration setup failed")
        return False
    
    # Step 2: Test configuration
    if not test_configuration():
        print("❌ Configuration test failed")
        return False
    
    print("\n🎉 Setup completed successfully!")
    print("\n📋 Next steps:")
    print("1. Start Redis server (optional but recommended): docker run -d -p 6379:6379 redis:alpine")
    print("2. Run tests: python backend/tests/test_trading_system.py")
    print("3. Start the system: python backend/main_refactored.py")
    
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)