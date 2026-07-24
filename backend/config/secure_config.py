"""
Secure configuration management with encrypted API keys.
Uses system keyring for secure storage and Fernet encryption.
"""

import os
try:
    import keyring
except ImportError:
    keyring = None

from cryptography.fernet import Fernet
from typing import Optional, Dict, Any
from dataclasses import dataclass, field
from pathlib import Path
import json
from backend.exceptions import APIKeyMissingError

@dataclass
class TradingConfig:
    """Configuration with validation for trading parameters"""
    # Entry/Exit thresholds
    ou_entry_z: float = field(default=1.5, metadata={"min": 0.5, "max": 3.0})
    ou_exit_z: float = field(default=0.5, metadata={"min": 0.1, "max": 1.5})
    min_confidence: float = field(default=0.6, metadata={"min": 0.1, "max": 1.0})
    
    # Risk management
    max_daily_loss_percent: float = field(default=2.0, metadata={"min": 0.5, "max": 10.0})
    max_position_size_percent: float = field(default=5.0, metadata={"min": 1.0, "max": 20.0})
    stop_loss_atr_multiplier: float = field(default=1.5, metadata={"min": 1.0, "max": 3.0})
    
    # Technical indicators
    sma_fast: int = field(default=9, metadata={"min": 5, "max": 20})
    sma_slow: int = field(default=21, metadata={"min": 15, "max": 50})
    rsi_period: int = field(default=14, metadata={"min": 7, "max": 30})
    atr_period: int = field(default=14, metadata={"min": 7, "max": 30})
    
    def validate(self) -> None:
        """Validate configuration parameters"""
        for field_name, field_def in self.__dataclass_fields__.items():
            value = getattr(self, field_name)
            if "min" in field_def.metadata and value < field_def.metadata["min"]:
                raise ValueError(f"{field_name} ({value}) below minimum ({field_def.metadata['min']})")
            if "max" in field_def.metadata and value > field_def.metadata["max"]:
                raise ValueError(f"{field_name} ({value}) above maximum ({field_def.metadata['max']})")

class SecureConfigManager:
    """Manages secure configuration and API key storage"""
    
    def __init__(self, service_name: str = "trading_system"):
        self.service_name = service_name
        self._cipher_suite = None
        self._config = TradingConfig()
        self._key_file = Path(__file__).resolve().with_name(".encryption_key")
        
    def _get_or_create_key(self) -> bytes:
        """Get or create encryption key"""
        try:
            key = keyring.get_password(self.service_name, "encryption_key")
            if key:
                return key.encode()
        except Exception as e:
            pass

        env_key = os.getenv("ENCRYPTION_KEY")
        if env_key:
            return env_key.encode()

        try:
            if self._key_file.exists():
                file_key = self._key_file.read_text(encoding="utf-8").strip()
                if file_key:
                    return file_key.encode()
        except Exception:
            pass

        key = Fernet.generate_key()
        try:
            self._key_file.write_text(key.decode(), encoding="utf-8")
        except Exception:
            pass
        os.environ.setdefault("ENCRYPTION_KEY", key.decode())
        return key
    
    @property
    def cipher_suite(self) -> Fernet:
        """Lazy initialization of cipher suite"""
        if self._cipher_suite is None:
            self._cipher_suite = Fernet(self._get_or_create_key())
        return self._cipher_suite
    
    def store_api_key(self, service: str, api_key: str) -> None:
        """Securely store API key"""
        try:
            encrypted = self.cipher_suite.encrypt(api_key.encode())
            keyring.set_password(self.service_name, service, encrypted.decode())
        except Exception as e:
            # Fallback to environment variable
            env_var = f"{service.upper()}_API_KEY"
            os.environ[env_var] = api_key
    
    def get_api_key(self, service: str) -> Optional[str]:
        """Retrieve and decrypt API key"""
        try:
            # Try keyring first
            encrypted_key = keyring.get_password(self.service_name, service)
            if encrypted_key:
                return self.cipher_suite.decrypt(encrypted_key.encode()).decode()
        except Exception:
            pass
        
        # Fallback to environment variable
        env_var = f"{service.upper()}_API_KEY"
        return os.getenv(env_var)
    
    def get_required_api_key(self, service: str) -> str:
        """Get required API key or raise exception"""
        api_key = self.get_api_key(service)
        if not api_key:
            raise APIKeyMissingError(service)
        return api_key

    def store_secret(self, secret_name: str, secret_value: str) -> None:
        """
        Store a generic secret (non-API-key credential) in keyring with encryption.
        Falls back to process env var if keyring is unavailable.
        """
        try:
            encrypted = self.cipher_suite.encrypt(secret_value.encode())
            keyring.set_password(self.service_name, secret_name, encrypted.decode())
        except Exception:
            pass
        os.environ[secret_name] = secret_value

    def get_secret(self, secret_name: str) -> Optional[str]:
        """
        Retrieve a generic secret from keyring (encrypted) with environment fallback.
        Supports backwards compatibility if plaintext was saved in keyring.
        """
        try:
            stored = keyring.get_password(self.service_name, secret_name)
            if stored:
                try:
                    return self.cipher_suite.decrypt(stored.encode()).decode()
                except Exception:
                    return stored
        except Exception:
            pass
        return os.getenv(secret_name)
    
    def get_config(self) -> TradingConfig:
        """Get trading configuration"""
        return self._config
    
    def update_config(self, **kwargs) -> None:
        """Update configuration parameters"""
        for key, value in kwargs.items():
            if hasattr(self._config, key):
                setattr(self._config, key, value)
        self._config.validate()
    
    def save_config_to_file(self, filepath: str) -> None:
        """Save configuration to file (without API keys)"""
        config_dict = {
            field.name: getattr(self._config, field.name)
            for field in self._config.__dataclass_fields__.values()
        }
        
        with open(filepath, 'w') as f:
            json.dump(config_dict, f, indent=2)
    
    def load_config_from_file(self, filepath: str) -> None:
        """Load configuration from file"""
        try:
            with open(filepath, 'r') as f:
                config_dict = json.load(f)
            
            for key, value in config_dict.items():
                if hasattr(self._config, key):
                    setattr(self._config, key, value)
            
            self._config.validate()
        except FileNotFoundError:
            # Config file doesn't exist, use defaults
            pass
        except Exception as e:
            raise ValueError(f"Invalid configuration file: {e}")

# Global configuration manager instance
config_manager = SecureConfigManager()
