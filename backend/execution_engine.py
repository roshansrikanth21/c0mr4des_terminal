"""
Execution Engine
Bridges Signal Generation with Broker Execution
"""
import logging
from datetime import datetime
from backend.broker.base_broker import BaseBroker
from backend.broker.paper_broker import PaperBroker
from backend.broker.angel_one_broker import AngelOneBroker
from backend.database import SessionLocal
from backend.models import Trade
from backend.services.execution_quality_service import execution_quality_service
from backend.services.ops_control_service import ops_control_service
from backend.services.routing_service import routing_service

class ExecutionEngine:
    def __init__(self, broker: BaseBroker = None):
        self.broker = broker or PaperBroker()
        self.active_trades = {}
        self.trade_history = []
        self._recover_active_trades_from_db()
        logging.info(f"Execution Engine initialized with {type(self.broker).__name__}")
        
    def _recover_active_trades_from_db(self):
        """Restore active filled trades from SQLite DB on server restart"""
        try:
            db = SessionLocal()
            trades = db.query(Trade).filter(Trade.status == "FILLED").all()
            for trade in trades:
                if trade.ticker not in self.active_trades:
                    self.active_trades[trade.ticker] = {
                        'id': str(trade.id),
                        'ticker': trade.ticker,
                        'action': trade.action,
                        'entry_price': trade.price,
                        'quantity': trade.quantity,
                        'timestamp': trade.timestamp.isoformat() if hasattr(trade, 'timestamp') and trade.timestamp else datetime.now().isoformat()
                    }
            db.close()
            if self.active_trades:
                logging.info(f"Recovered {len(self.active_trades)} active trades from DB.")
        except Exception as e:
            logging.error(f"Failed to recover active trades: {e}")
        
    def _log_trade_to_db(self, symbol: str, action: str, quantity: float, price: float, trade_id: str = None):
        """Persist trade execution to SQLite DB"""
        try:
            db = SessionLocal()
            trade = Trade(
                ticker=symbol,
                action=action,
                quantity=quantity,
                price=price,
                status="FILLED"
            )
            db.add(trade)
            db.commit()
            db.close()
        except Exception as e:
            logging.error(f"Failed to log trade to DB: {e}")

    def _current_mode(self) -> str:
        """Return normalized broker mode for API consumers."""
        if isinstance(self.broker, PaperBroker):
            return "PAPER"
        if isinstance(self.broker, AngelOneBroker):
            return "ANGEL_ONE"
        return "NONE"

    def get_status(self):
        """Returns connection status and P&L summarize"""
        try:
            pnl = float(self.broker.get_pnl() or 0.0)
            balance = float(getattr(self.broker, "balance", 0.0) or 0.0)
            return {
                "connected": True,
                "mode": self._current_mode(),
                "last_updated": datetime.now().isoformat(),
                "status": "CONNECTED",
                "broker": type(self.broker).__name__,
                "pnl": pnl,
                "balance": balance
            }
        except Exception as e:
            return {
                "connected": False,
                "mode": self._current_mode(),
                "last_updated": datetime.now().isoformat(),
                "status": "ERROR",
                "message": str(e),
                "pnl": 0.0,
                "balance": 0.0
            }

    def get_portfolio(self):
        """Returns active positions and orders"""
        try:
            raw_positions = self.broker.get_positions() or []
            raw_orders = self.broker.get_orders() or []
            balance = float(getattr(self.broker, "balance", 0.0) or 0.0)

            normalized_positions = []
            total_position_value = 0.0
            total_unrealized = 0.0

            for pos in raw_positions:
                symbol = pos.get("symbol", "")
                quantity = float(pos.get("quantity", 0) or 0)

                avg_price = float(
                    pos.get("avg_price")
                    or pos.get("averageprice")
                    or pos.get("avgprice")
                    or 0.0
                )
                ltp = float(
                    pos.get("ltp")
                    or pos.get("last_price")
                    or pos.get("ltp_value")
                    or 0.0
                )
                if ltp == 0 and symbol:
                    try:
                        ltp = float(self.broker.get_quote(symbol) or 0.0)
                    except Exception:
                        ltp = 0.0

                pnl = pos.get("pnl")
                if pnl is None:
                    pnl = (ltp - avg_price) * quantity
                pnl = float(pnl or 0.0)

                basis = avg_price * quantity
                pnl_percent = (pnl / basis * 100.0) if basis > 0 else 0.0
                value = ltp * quantity

                total_position_value += value
                total_unrealized += pnl

                normalized_positions.append({
                    "symbol": symbol,
                    "quantity": int(quantity),
                    "avg_price": avg_price,
                    "ltp": ltp,
                    "pnl": pnl,
                    "pnl_percent": pnl_percent,
                    "value": value
                })

            return {
                "balance": balance,
                "used_margin": 0.0,
                "total_value": balance + total_position_value,
                "pnl": total_unrealized,
                "positions": normalized_positions,
                "orders": raw_orders
            }
        except Exception as e:
            return {"status": "ERROR", "message": str(e)}

    def execute_order(self, order_params: dict):
        """Executes a manual order via the current broker"""
        started_at = datetime.now()
        try:
            # Standardize symbol for yfinance vs internal
            symbol = order_params.get('symbol')
            # If symbol is just SBIN, and we are in India, yf might need SBIN.NS
            # Paper broker handles this, but let's be careful
            
            quantity = order_params.get('quantity', 1)
            action = order_params.get('action', 'BUY')
            price = order_params.get('price', 0.0)
            order_type = str(order_params.get('type', 'MARKET')).upper()
            expected_price = price
            if order_type == "MARKET":
                is_option = any(x in str(symbol).upper() for x in ['CE', 'PE', 'OPT'])
                if is_option and expected_price > 0:
                    order_type = 'LIMIT'
                    if action == 'BUY':
                        price = round(expected_price * 1.05, 2)
                    else:
                        price = round(expected_price * 0.95, 2)
                else:
                    try:
                        expected_price = float(self.broker.get_quote(symbol) or 0.0)
                        if is_option and expected_price > 0:
                            order_type = 'LIMIT'
                            price = round(expected_price * 1.05, 2) if action == 'BUY' else round(expected_price * 0.95, 2)
                    except Exception:
                        expected_price = 0.0
            routing = routing_service.get_execution_directive(ticker=str(symbol or "UNKNOWN"))
            auto_switch = None
            if routing.get("directive") == "prefer_alternate" and ops_control_service.can_auto_switch():
                auto_switch = routing_service.apply_auto_switch(ticker=str(symbol or "UNKNOWN"))
                routing = routing_service.get_execution_directive(ticker=str(symbol or "UNKNOWN"))
            forecast = execution_quality_service.forecast_execution(
                symbol=str(symbol or "UNKNOWN"),
                side=str(action or "BUY"),
                broker=type(self.broker).__name__,
                order_type=order_type,
            ).get("forecast", {})
            if routing.get("directive") == "halt" and bool(order_params.get("auto_route")):
                return {
                    "status": "REJECTED",
                    "reason": routing.get("reason", "Current broker route is degraded."),
                    "execution_forecast": forecast,
                    "routing": routing,
                    "auto_switch": auto_switch,
                }
            
            result = self.broker.place_order(
                symbol=symbol,
                quantity=quantity,
                side=action,
                order_type=order_type,
                price=price
            )
            
            if result.get('status') not in ['REJECTED', 'FAILED']:
                exec_price = result.get('price', price)
                self._log_trade_to_db(symbol, action, quantity, exec_price, result.get('id', ''))

            latency_ms = (datetime.now() - started_at).total_seconds() * 1000.0
            tracking = execution_quality_service.record_execution(
                symbol=str(symbol or "UNKNOWN"),
                side=str(action or "BUY"),
                quantity=quantity,
                status=str(result.get('status', 'UNKNOWN')),
                source="manual_order",
                broker=type(self.broker).__name__,
                order_type=order_type,
                expected_price=expected_price,
                executed_price=result.get('price', price),
                latency_ms=latency_ms,
                filled_quantity=quantity if str(result.get('status', '')).upper() in {'FILLED', 'EXECUTED', 'SUCCESS'} else 0,
                filled_at=datetime.now().isoformat() if str(result.get('status', '')).upper() in {'FILLED', 'EXECUTED', 'SUCCESS'} else None,
                signal_id=order_params.get("signal_id"),
                broker_order_id=result.get('id'),
                reason=result.get('reason') or result.get('message'),
                metadata={"result": result, "request": order_params, "forecast": forecast},
            )
            result["execution_tracking"] = tracking.get("event")
            result["execution_forecast"] = forecast
            result["routing"] = routing
            if auto_switch is not None:
                result["auto_switch"] = auto_switch
                
            return result
        except Exception as e:
            latency_ms = (datetime.now() - started_at).total_seconds() * 1000.0
            fallback = execution_quality_service.record_execution(
                symbol=str(order_params.get('symbol') or "UNKNOWN"),
                side=str(order_params.get('action') or "BUY"),
                quantity=order_params.get('quantity', 0),
                status="REJECTED",
                source="manual_order",
                broker=type(self.broker).__name__,
                order_type=str(order_params.get('type', 'MARKET')).upper(),
                expected_price=order_params.get('price'),
                executed_price=None,
                latency_ms=latency_ms,
                signal_id=order_params.get("signal_id"),
                reason=str(e),
                metadata={"request": order_params},
            )
            return {"status": "REJECTED", "reason": str(e), "execution_tracking": fallback.get("event")}

    def switch_mode(self, mode: str):
        """Switches between PAPER and ANGEL_ONE"""
        if mode == "ANGEL_ONE":
            self.broker = AngelOneBroker()
            if not self.broker.connect():
                return {"status": "error", "message": "Failed to connect to Angel One. Staying on Paper."}
        else:
            self.broker = PaperBroker()
            
        logging.info(f"Switched to {type(self.broker).__name__}")
        return {"status": "success", "mode": mode}

    def execute_decision(self, decision: dict, plan: dict):
        """
        Processes a decision from the IntegratedTradingDecisionEngine
        """
        started_at = datetime.now()
        action = decision.get('action')
        ticker = decision.get('ticker')
        
        if action == 'HOLD':
            return {"status": "SKIPPED", "reason": "Signal is HOLD"}

        # Basic Risk Check
        if ticker in self.active_trades:
            return {"status": "SKIPPED", "reason": f"Active trade already exists for {ticker}"}

        # Symbol Translation for Broker (NIFTY -> Nifty 50 for Angel One)
        broker_symbol = ticker
        if "^NSEI" in ticker: broker_symbol = "NIFTY"
        
        routing = routing_service.get_execution_directive(ticker=str(ticker or "UNKNOWN"))
        auto_switch = None
        if routing.get("directive") == "prefer_alternate" and ops_control_service.can_auto_switch():
            auto_switch = routing_service.apply_auto_switch(ticker=str(ticker or "UNKNOWN"))
            routing = routing_service.get_execution_directive(ticker=str(ticker or "UNKNOWN"))
        if routing.get("directive") == "halt":
            return {
                "status": "SKIPPED",
                "reason": routing.get("reason", "Execution route is degraded."),
                "routing": routing,
                "auto_switch": auto_switch,
            }

        base_quantity = int(plan.get('size', {}).get('quantity', 1) or 1)
        forecast = execution_quality_service.forecast_execution(
            symbol=str(ticker or broker_symbol or "UNKNOWN"),
            side='BUY' if action == 'BUY' else 'SELL',
            broker=type(self.broker).__name__,
            order_type='MARKET',
        ).get("forecast", {})
        forecast_samples = int(forecast.get("sample_count", 0) or 0)
        risk_multiplier = float(forecast.get("risk_multiplier", 1.0) or 1.0)
        quantity = max(1, int(round(base_quantity * max(0.25, min(risk_multiplier, 1.0))))) if base_quantity > 0 else 1
        if forecast.get("recommendation") == "avoid" and forecast_samples >= 8:
            return {
                "status": "SKIPPED",
                "reason": "Execution forecast vetoed trade due to poor expected fill quality.",
                "execution_forecast": forecast,
                "routing": routing,
                "auto_switch": auto_switch,
            }
        if routing.get("directive") == "reduce_size":
            quantity = max(1, int(round(quantity * 0.75)))
        
        logging.info(f"Executing {action} for {ticker} | Qty: {quantity}")
        
        order_type = 'MARKET'
        price = plan.get('entry', 0.0)
        
        # Slippage bounds / price protection for option trades
        is_option = any(x in broker_symbol.upper() for x in ['CE', 'PE', 'OPT'])
        if is_option and price > 0:
            order_type = 'LIMIT'
            # 5% slippage bound
            if action == 'BUY':
                price = round(price * 1.05, 2)
            else:
                price = round(price * 0.95, 2)

        order_result = self.broker.place_order(
            symbol=broker_symbol,
            quantity=quantity,
            side='BUY' if action == 'BUY' else 'SELL',
            order_type=order_type,
            price=price
        )
        
        status = order_result.get('status')
        latency_ms = (datetime.now() - started_at).total_seconds() * 1000.0
        tracking = execution_quality_service.record_execution(
            symbol=str(ticker or broker_symbol or "UNKNOWN"),
            side='BUY' if action == 'BUY' else 'SELL',
            quantity=quantity,
            status=str(status or "UNKNOWN"),
            source="strategy_execution",
            broker=type(self.broker).__name__,
            order_type='MARKET',
            expected_price=plan.get('entry'),
            executed_price=order_result.get('price', plan.get('entry', 0.0)),
            latency_ms=latency_ms,
            filled_quantity=quantity if str(status or '').upper() in {'FILLED', 'EXECUTED', 'SUCCESS'} else 0,
            filled_at=datetime.now().isoformat() if str(status or '').upper() in {'FILLED', 'EXECUTED', 'SUCCESS'} else None,
            signal_id=decision.get("signal_id") or plan.get("signal_id"),
            broker_order_id=order_result.get('id'),
            reason=order_result.get('reason'),
            metadata={"decision": decision, "plan": plan, "result": order_result, "forecast": forecast},
        )
        order_result["execution_tracking"] = tracking.get("event")
        order_result["execution_forecast"] = forecast
        if status == 'SUBMITTED' or status == 'FILLED':
            trade_id = order_result.get('id')
            exec_price = order_result.get('price', plan.get('entry', 0.0))
            self._log_trade_to_db(broker_symbol, action, quantity, exec_price, trade_id)
            
            self.active_trades[ticker] = {
                'id': trade_id,
                'ticker': ticker,
                'action': action,
                'entry_price': plan.get('entry'),
                'sl': plan.get('sl'),
                'tp': plan.get('tp'),
                'timestamp': datetime.now().isoformat()
            }
            return {
                "status": "EXECUTED",
                "trade_id": trade_id,
                "execution_tracking": tracking.get("event"),
                "execution_forecast": forecast,
                "routing": routing,
                "auto_switch": auto_switch,
                "requested_quantity": base_quantity,
                "executed_quantity": quantity,
            }
        else:
            return {
                "status": "FAILED",
                "reason": order_result.get('reason'),
                "execution_tracking": tracking.get("event"),
                "execution_forecast": forecast,
                "routing": routing,
                "auto_switch": auto_switch,
                "requested_quantity": base_quantity,
                "executed_quantity": quantity,
            }

    def switch_broker(self, live: bool = False):
        """Switch between Paper and Live (Angel One)"""
        if live:
            self.broker = AngelOneBroker()
            if not self.broker.connect():
                logging.error("Failed to connect to Live Broker. Staying on Paper.")
                self.broker = PaperBroker()
        else:
            self.broker = PaperBroker()
        logging.info(f"Switched to {type(self.broker).__name__}")
