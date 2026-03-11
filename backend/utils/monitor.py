import time
from collections import deque
from typing import List, Dict, Any
import datetime

class RequestMonitor:
    def __init__(self, max_items: int = 100):
        self.history = deque(maxlen=max_items)
        self.stats = {
            "total_requests": 0,
            "success_count": 0,
            "error_count": 0,
            "avg_latency": 0.0
        }

    def log_request(self, method: str, path: str, status_code: int, duration_ms: float):
        timestamp = datetime.datetime.now().isoformat()
        entry = {
            "id": f"{int(time.time() * 1000)}",
            "timestamp": timestamp,
            "method": method,
            "path": path,
            "status": status_code,
            "duration": round(duration_ms, 2)
        }
        self.history.appendleft(entry)
        
        # Update Stats
        self.stats["total_requests"] += 1
        if 200 <= status_code < 400:
            self.stats["success_count"] += 1
        else:
            self.stats["error_count"] += 1
            
        # Moving average for latency
        prev_avg = self.stats["avg_latency"]
        count = self.stats["total_requests"]
        self.stats["avg_latency"] = ((prev_avg * (count - 1)) + duration_ms) / count

    def get_history(self) -> List[Dict[str, Any]]:
        return list(self.history)

    def get_stats(self) -> Dict[str, Any]:
        return {
            **self.stats,
            "avg_latency": round(self.stats["avg_latency"], 2),
            "uptime": "LIVE" # Could calculate actual uptime if needed
        }

# Global instance
monitor = RequestMonitor()
