import os
import logging
from typing import Dict, List
from .base_broker import BaseBroker
try:
    import pyotp
except ImportError:
    pyotp = None

try:
    from SmartApi import SmartConnect # type: ignore
    ANGEL_ONE_AVAILABLE = True
except ImportError:
    ANGEL_ONE_AVAILABLE = False

class AngelOneBroker(BaseBroker):
    """
    Angel One Broker Implementation using SmartAPI.
    Requires environment variables:
    - ANGEL_API_KEY
    - ANGEL_CLIENT_ID
    - ANGEL_PASSWORD
    - ANGEL_TOTP_KEY
    """
    
    def __init__(self):
        self.api_key = os.getenv("ANGEL_API_KEY") or os.getenv("ANGEL_ONE_API_KEY")
        self.client_id = os.getenv("ANGEL_CLIENT_ID") or os.getenv("ANGEL_ONE_CLIENT_ID")
        self.password = os.getenv("ANGEL_PASSWORD") or os.getenv("ANGEL_ONE_PASSWORD")
        self.totp_key = os.getenv("ANGEL_TOTP_KEY") or os.getenv("ANGEL_ONE_TOTP_KEY")
        self.smart_api = None
        self.session = None
        self.token_map = {}
        self._load_token_map()
        
    def _load_token_map(self):
        """Load instrument token map for symbol resolution with segment tuple mapping"""
        import requests
        import json
        token_path = os.path.join(os.path.dirname(__file__), 'angel_tokens.json')
        
        try:
            needs_download = True
            if os.path.exists(token_path):
                from datetime import datetime, timedelta
                mtime = datetime.fromtimestamp(os.path.getmtime(token_path))
                if datetime.now() - mtime < timedelta(hours=24):
                    needs_download = False
            
            if needs_download:
                url = "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"
                logging.info(f"Downloading Scrip Master from {url}...")
                response = requests.get(url, timeout=30, stream=True)
                if response.status_code == 200:
                    with open(token_path, 'wb') as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            f.write(chunk)
                    logging.info("Scrip Master downloaded successfully.")
            
            if os.path.exists(token_path):
                with open(token_path, 'r') as f:
                    raw_tokens = json.load(f)
                    # Map (symbol, exchange) to token for fast lookup to avoid collisions
                    self.token_map = {(str(t['symbol']).upper(), str(t['exch_seg']).upper()): t for t in raw_tokens}
                    logging.info(f"Loaded {len(raw_tokens)} Angel One tokens into map")
            else:
                logging.warning("Angel token map file not found. Symbol resolution will fail.")
        except Exception as e:
            import traceback
            logging.error(f"Failed to load Angel token map: {e}")
            traceback.print_exc()

    def _get_token_info(self, symbol: str, exchange: str = "NSE") -> Dict:
        """Find token and exchange for a given symbol"""
        # Common translations: NIFTY -> Nifty 50, etc.
        lookup = symbol.upper()
        if lookup in ("NIFTY", "^NSEI"):
            lookup = "NIFTY 50"
        
        # Try direct or with -EQ for NSE
        for s in [lookup, f"{lookup}-EQ", f"{lookup}-NSE"]:
            # Try to match in specified exchange or common segments
            exchanges_to_try = [exchange.upper()] if exchange else ["NSE", "NFO", "BSE", "MCX", "NCDEX", "CDS"]
            for exch in exchanges_to_try:
                if (s, exch) in self.token_map:
                    return self.token_map[(s, exch)]
        return {}

    def connect(self) -> bool:
        """Authenticate with Angel One"""
        if not all([self.api_key, self.client_id, self.password, self.totp_key]):
            logging.error("Angel One credentials missing in .env")
            return False
            
        if not pyotp:
            logging.error("pyotp library not installed. Cannot generate TOTP for Angel One login.")
            return False

        try:
            self.smart_api = SmartConnect(api_key=self.api_key)
            totp = pyotp.TOTP(self.totp_key).now()
            self.session = self.smart_api.generateSession(self.client_id, self.password, totp)
            
            if self.session['status']:
                logging.info(f"Connected to Angel One. User: {self.client_id}")
                return True
            else:
                logging.error(f"Angel One Login Failed: {self.session['message']}")
                return False
                
        except Exception as e:
            logging.error(f"Angel One Connection Error: {e}")
            return False
            
    def get_quote(self, symbol: str) -> float:
        """Get the latest price (LTP) for a symbol."""
        if not self.smart_api: return 0.0
        
        token_info = self._get_token_info(symbol)
        if not token_info: return 0.0
        
        try:
            quote = self.smart_api.ltpData(
                token_info['exch_seg'], 
                token_info['symbol'], 
                token_info['token']
            )
            if quote['status']:
                return float(quote['data']['ltp'])
        except Exception as e:
            logging.error(f"Failed to fetch quote for {symbol}: {e}")
        return 0.0
        
    def place_order(self, symbol: str, quantity: int, side: str, 
                   order_type: str = "MARKET", price: float = 0.0,
                   stop_loss: float = 0.0, take_profit: float = 0.0) -> Dict:
        
        if not self.smart_api:
            return {"status": "FAILED", "reason": "Not connected"}
            
        token_info = self._get_token_info(symbol)
        if not token_info:
            return {"status": "FAILED", "reason": f"Symbol {symbol} not found in token map"}
            
        try:
            orderparams = {
                "variety": "NORMAL",
                "tradingsymbol": token_info['symbol'],
                "symboltoken": token_info['token'],
                "transactiontype": side.upper(), # BUY/SELL
                "exchange": token_info['exch_seg'],
                "ordertype": order_type.upper(),
                "producttype": "INTRADAY",
                "duration": "DAY",
                "price": str(price) if order_type != "MARKET" else "0",
                "quantity": str(quantity)
            }
            
            response = self.smart_api.placeOrder(orderparams)
            if response and response.get('status'):
                order_id = response['data']['orderid']
                logging.info(f"Angel Order Placed: {order_id}")
                return {"status": "SUBMITTED", "id": order_id}
            else:
                return {"status": "FAILED", "reason": response.get('message', 'Unknown error')}
            
        except Exception as e:
            logging.error(f"Order Placement Failed: {e}")
            return {"status": "FAILED", "reason": str(e)}

    def get_positions(self) -> List[Dict]:
        if not self.smart_api: return []
        try:
            positions = self.smart_api.position()
            return positions['data'] if positions['data'] else []
        except Exception as e:
            return []

    def get_orders(self) -> List[Dict]:
        if not self.smart_api: return []
        try:
            orders = self.smart_api.orderBook()
            return orders['data'] if orders['data'] else []
        except Exception as e:
            return []

    def get_pnl(self) -> float:
        """Calculate total Realized + Unrealized P&L from positions"""
        positions = self.get_positions()
        total_pnl = 0.0
        for pos in positions:
            try:
                total_pnl += float(pos.get('pnl', 0))
            except:
                continue
        return total_pnl
