"""
Redis-based caching service for expensive calculations.
Provides high-performance caching with automatic expiration and serialization.
"""

import redis
import pickle
import hashlib
import json
import time
import logging
from functools import wraps
from typing import Optional, Any, Dict

from backend.exceptions import TradingSystemError

logger = logging.getLogger(__name__)

class CacheManager:
    """Redis-based caching manager with automatic serialization"""
    
    def __init__(self, host: str = 'localhost', port: int = 6379, db: int = 0, 
                 password: Optional[str] = None, default_ttl: int = 300):
        """
        Initialize Redis cache manager
        
        Args:
            host: Redis server host
            port: Redis server port
            db: Redis database number
            password: Redis password (optional)
            default_ttl: Default time-to-live in seconds (5 minutes)
        """
        self.default_ttl = default_ttl
        self._redis_client = None
        
        try:
            self._redis_client = redis.Redis(
                host=host, 
                port=port, 
                db=db, 
                password=password,
                decode_responses=False,  # Handle binary data
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=True
            )
            
            # Test connection
            self._redis_client.ping()
            logger.info(f"Redis cache connected successfully at {host}:{port}")
            
        except Exception as e:
            logger.warning(f"Redis connection failed: {e}. Using in-memory cache fallback.")
            self._redis_client = None
            self._memory_cache = {}
    
    def _get_redis_client(self):
        """Get Redis client or fallback to memory cache"""
        if self._redis_client is not None:
            return self._redis_client
        return None
    
    def _serialize_value(self, value: Any) -> bytes:
        """Serialize value for storage"""
        try:
            return pickle.dumps(value)
        except Exception as e:
            # Fallback to JSON serialization for simpler objects
            try:
                return json.dumps(value).encode('utf-8')
            except (TypeError, ValueError):
                logger.error(f"Failed to serialize value: {e}")
                raise TradingSystemError(f"Cannot cache value: {e}")
    
    def _deserialize_value(self, value: bytes) -> Any:
        """Deserialize value from storage"""
        try:
            return pickle.loads(value)
        except (pickle.PickleError, UnicodeDecodeError):
            # Fallback to JSON deserialization
            try:
                return json.loads(value.decode('utf-8'))
            except (json.JSONDecodeError, UnicodeDecodeError):
                logger.error("Failed to deserialize cached value")
                return None
    
    def _generate_key(self, prefix: str, **kwargs) -> str:
        """Generate consistent cache key from parameters"""
        # Sort kwargs to ensure consistent key generation
        key_data = {k: v for k, v in sorted(kwargs.items())}
        key_string = f"{prefix}:{hashlib.md5(str(key_data).encode()).hexdigest()}"
        return key_string
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """
        Store value in cache
        
        Args:
            key: Cache key
            value: Value to store
            ttl: Time-to-live in seconds (uses default if None)
            
        Returns:
            True if successful, False otherwise
        """
        if ttl is None:
            ttl = self.default_ttl
        
        redis_client = self._get_redis_client()
        
        if redis_client:
            try:
                serialized = self._serialize_value(value)
                return redis_client.setex(key, ttl, serialized)
            except Exception as e:
                logger.error(f"Redis set error: {e}")
                return False
        else:
            # Fallback to memory cache
            self._memory_cache[key] = {
                'value': value,
                'expires': time.time() + ttl
            }
            return True
    
    def get(self, key: str) -> Optional[Any]:
        """
        Retrieve value from cache
        
        Args:
            key: Cache key
            
        Returns:
            Cached value or None if not found/expired
        """
        redis_client = self._get_redis_client()
        
        if redis_client:
            try:
                value = redis_client.get(key)
                if value:
                    return self._deserialize_value(value)
                return None
            except Exception as e:
                logger.error(f"Redis get error: {e}")
                return None
        else:
            # Fallback to memory cache
            if key in self._memory_cache:
                cache_item = self._memory_cache[key]
                if time.time() < cache_item['expires']:
                    return cache_item['value']
                else:
                    # Expired item
                    del self._memory_cache[key]
            return None
    
    def delete(self, key: str) -> bool:
        """
        Delete value from cache
        
        Args:
            key: Cache key
            
        Returns:
            True if successful, False otherwise
        """
        redis_client = self._get_redis_client()
        
        if redis_client:
            try:
                return bool(redis_client.delete(key))
            except Exception as e:
                logger.error(f"Redis delete error: {e}")
                return False
        else:
            # Fallback to memory cache
            if key in self._memory_cache:
                del self._memory_cache[key]
                return True
            return False
    
    def exists(self, key: str) -> bool:
        """
        Check if key exists in cache
        
        Args:
            key: Cache key
            
        Returns:
            True if key exists and is not expired
        """
        redis_client = self._get_redis_client()
        
        if redis_client:
            try:
                return bool(redis_client.exists(key))
            except Exception as e:
                logger.error(f"Redis exists error: {e}")
                return False
        else:
            # Fallback to memory cache
            if key in self._memory_cache:
                cache_item = self._memory_cache[key]
                if time.time() < cache_item['expires']:
                    return True
                else:
                    # Expired item
                    del self._memory_cache[key]
            return False
    
    def clear_pattern(self, pattern: str) -> int:
        """
        Clear all keys matching a pattern
        
        Args:
            pattern: Redis pattern (e.g., "ticker:*")
            
        Returns:
            Number of keys deleted
        """
        redis_client = self._get_redis_client()
        
        if redis_client:
            try:
                keys = redis_client.keys(pattern)
                if keys:
                    return redis_client.delete(*keys)
                return 0
            except Exception as e:
                logger.error(f"Redis clear pattern error: {e}")
                return 0
        else:
            # Fallback to memory cache
            count = 0
            keys_to_delete = []
            for key in self._memory_cache:
                if pattern.replace('*', '') in key:
                    keys_to_delete.append(key)
            
            for key in keys_to_delete:
                del self._memory_cache[key]
                count += 1
            
            return count
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics
        
        Returns:
            Dictionary with cache statistics
        """
        redis_client = self._get_redis_client()
        
        if redis_client:
            try:
                info = redis_client.info()
                return {
                    'type': 'redis',
                    'connected_clients': info.get('connected_clients', 0),
                    'used_memory': info.get('used_memory_human', '0B'),
                    'keyspace_hits': info.get('keyspace_hits', 0),
                    'keyspace_misses': info.get('keyspace_misses', 0),
                    'total_commands_processed': info.get('total_commands_processed', 0)
                }
            except Exception as e:
                logger.error(f"Redis stats error: {e}")
                return {'type': 'redis', 'error': str(e)}
        else:
            # Memory cache stats
            current_time = time.time()
            valid_keys = sum(
                1 for item in self._memory_cache.values()
                if current_time < item['expires']
            )
            
            return {
                'type': 'memory',
                'total_keys': len(self._memory_cache),
                'valid_keys': valid_keys,
                'expired_keys': len(self._memory_cache) - valid_keys
            }

# Decorator for caching function results
def cached(prefix: str, ttl: Optional[int] = None, cache_manager: Optional[CacheManager] = None):
    """
    Decorator to cache function results
    
    Args:
        prefix: Cache key prefix
        ttl: Time-to-live in seconds
        cache_manager: CacheManager instance (uses global if None)
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Use global cache manager if none provided
            cm = cache_manager or global_cache_manager
            
            if cm is None:
                # No caching available, run function normally
                return func(*args, **kwargs)
            
            # Generate cache key
            cache_key = cm._generate_key(
                prefix,
                func_name=func.__name__,
                args=args,
                kwargs=kwargs
            )
            
            # Try to get from cache
            cached_result = cm.get(cache_key)
            if cached_result is not None:
                logger.debug(f"Cache hit for {func.__name__}")
                return cached_result
            
            # Cache miss, run function
            logger.debug(f"Cache miss for {func.__name__}, computing result")
            result = func(*args, **kwargs)
            
            # Store in cache
            cm.set(cache_key, result, ttl)
            
            return result
        
        return wrapper
    return decorator

# Specialized caching functions for trading data
class TradingCache:
    """Specialized cache for trading-related data"""
    
    def __init__(self, cache_manager: CacheManager):
        self.cache = cache_manager
    
    def cache_market_data(self, ticker: str, period: str, interval: str, data: Any) -> bool:
        """Cache market data"""
        key = f"market_data:{ticker}:{period}:{interval}"
        # Market data cached for 2 minutes
        return self.cache.set(key, data, ttl=120)
    
    def get_market_data(self, ticker: str, period: str, interval: str) -> Optional[Any]:
        """Get cached market data"""
        key = f"market_data:{ticker}:{period}:{interval}"
        return self.cache.get(key)
    
    def cache_indicators(self, ticker: str, indicator_type: str, params: dict, result: Any) -> bool:
        """Cache technical indicator results"""
        param_str = hashlib.md5(str(sorted(params.items())).encode()).hexdigest()
        key = f"indicators:{ticker}:{indicator_type}:{param_str}"
        # Indicators cached for 5 minutes
        return self.cache.set(key, result, ttl=300)
    
    def get_indicators(self, ticker: str, indicator_type: str, params: dict) -> Optional[Any]:
        """Get cached technical indicators"""
        param_str = hashlib.md5(str(sorted(params.items())).encode()).hexdigest()
        key = f"indicators:{ticker}:{indicator_type}:{param_str}"
        return self.cache.get(key)
    
    def cache_signals(self, ticker: str, strategy: str, result: Any) -> bool:
        """Cache trading signals"""
        key = f"signals:{ticker}:{strategy}"
        # Signals cached for 1 minute
        return self.cache.set(key, result, ttl=60)
    
    def get_signals(self, ticker: str, strategy: str) -> Optional[Any]:
        """Get cached trading signals"""
        key = f"signals:{ticker}:{strategy}"
        return self.cache.get(key)
    
    def cache_analysis(self, ticker: str, analysis_type: str, result: Any) -> bool:
        """Cache analysis results"""
        key = f"analysis:{ticker}:{analysis_type}"
        # Analysis cached for 10 minutes
        return self.cache.set(key, result, ttl=600)
    
    def get_analysis(self, ticker: str, analysis_type: str) -> Optional[Any]:
        """Get cached analysis"""
        key = f"analysis:{ticker}:{analysis_type}"
        return self.cache.get(key)
    
    def clear_ticker_cache(self, ticker: str) -> int:
        """Clear all cached data for a ticker"""
        patterns = [
            f"market_data:{ticker}:*",
            f"indicators:{ticker}:*",
            f"signals:{ticker}:*",
            f"analysis:{ticker}:*"
        ]
        
        total_deleted = 0
        for pattern in patterns:
            total_deleted += self.cache.clear_pattern(pattern)
        
        return total_deleted

# Global cache manager instance
global_cache_manager = CacheManager()

# Trading cache instance
trading_cache = TradingCache(global_cache_manager)
