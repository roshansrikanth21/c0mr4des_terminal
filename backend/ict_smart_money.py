import pandas as pd
import numpy as np
from typing import Dict, List, Any

class ICTSmartMoney:
    """
    Implements 'Inner Circle Trader' (ICT) concepts:
    - Fair Value Gaps (FVG)
    - Order Blocks (OB)
    - Market Structure Shifts (MSS)
    - Break of Structure (BOS)
    """

    def __init__(self, df: pd.DataFrame):
        self.df = df.copy()
        # Ensure lowercase columns for consistency
        self.df.columns = [c.lower() for c in self.df.columns]
        if 'timestamp' not in self.df.columns:
            # If standard yfinance index
            self.df['timestamp'] = self.df.index

    def detect_fair_value_gaps(self) -> List[Dict]:
        """
        Detects 3-candle Fair Value Gaps.
        Bullish FVG: Candle 1 High < Candle 3 Low (Gap in between)
        Bearish FVG: Candle 1 Low > Candle 3 High (Gap in between)
        """
        fvgs = []
        df = self.df
        
        if len(df) < 3:
            return fvgs

        # Vectorized approach or robust loop
        # Loop is easier for logic clarity on 3-candle pattern
        for i in range(2, len(df)):
            try:
                # Candles: i-2 (1), i-1 (2), i (3)
                c1 = df.iloc[i-2]
                c2 = df.iloc[i-1] # The "displacement" candle
                c3 = df.iloc[i]
                
                # --- BULLISH FVG ---
                # Key: The Low of the 3rd candle is HIGHER than the High of the 1st candle
                if c3['low'] > c1['high']:
                    gap_size = c3['low'] - c1['high']
                    # Filter: Gap must be significant (e.g., > 0.02% of price) to avoid noise
                    min_gap = c2['close'] * 0.0002 
                    
                    if gap_size > min_gap:
                        fvgs.append({
                            "type": "bullish",
                            "top": float(c3['low']),      # Gap Top
                            "bottom": float(c1['high']),  # Gap Bottom
                            "start_time": str(c2['timestamp']), # Center candle timestamp
                            "end_time": str(c3['timestamp']),
                            "mitigated": False
                        })

                # --- BEARISH FVG ---
                # Key: The High of the 3rd candle is LOWER than the Low of the 1st candle
                elif c3['high'] < c1['low']:
                    gap_size = c1['low'] - c3['high']
                    min_gap = c2['close'] * 0.0002
                    
                    if gap_size > min_gap:
                        fvgs.append({
                            "type": "bearish",
                            "top": float(c1['low']),      # Gap Top
                            "bottom": float(c3['high']),  # Gap Bottom
                            "start_time": str(c2['timestamp']),
                            "end_time": str(c3['timestamp']),
                            "mitigated": False
                        })
            except Exception as e:
                continue
        
        return fvgs

    def detect_inverse_fair_value_gaps(self) -> List[Dict]:
        """
        Detect inverse FVG (IFVG) transitions.
        Logic:
        - A bullish FVG invalidated to downside can flip to bearish IFVG.
        - A bearish FVG invalidated to upside can flip to bullish IFVG.
        """
        ifvgs: List[Dict] = []
        fvgs = self.detect_fair_value_gaps()
        if not fvgs:
            return ifvgs

        df = self.df
        if len(df) < 10:
            return ifvgs

        # Pre-normalize timestamp for robust comparisons.
        local = df.copy()
        local["timestamp"] = pd.to_datetime(local["timestamp"], errors="coerce", utc=True)
        local = local.dropna(subset=["timestamp"])
        if local.empty:
            return ifvgs

        for fvg in fvgs:
            try:
                end_ts = pd.to_datetime(fvg.get("end_time"), errors="coerce", utc=True)
                if pd.isna(end_ts):
                    continue

                future = local[local["timestamp"] > end_ts]
                if future.empty:
                    continue

                top = float(fvg["top"])
                bottom = float(fvg["bottom"])

                if fvg["type"] == "bullish":
                    invalidated = bool((future["low"] < bottom).any())
                    if invalidated:
                        ifvgs.append({
                            "type": "bearish_ifvg",
                            "top": top,
                            "bottom": bottom,
                            "source_type": "bullish_fvg",
                            "flipped_at": str(future.loc[future["low"] < bottom, "timestamp"].iloc[0]),
                            "end_time": fvg.get("end_time")
                        })
                else:
                    invalidated = bool((future["high"] > top).any())
                    if invalidated:
                        ifvgs.append({
                            "type": "bullish_ifvg",
                            "top": top,
                            "bottom": bottom,
                            "source_type": "bearish_fvg",
                            "flipped_at": str(future.loc[future["high"] > top, "timestamp"].iloc[0]),
                            "end_time": fvg.get("end_time")
                        })
            except Exception:
                continue

        return ifvgs

    def detect_order_blocks(self) -> List[Dict]:
        """
        Detects Bullish/Bearish Order Blocks.
        Bullish OB: The last DOWN candle before a sequence that breaks structure or rises sharply.
        Bearish OB: The last UP candle before a sharp drop.
        """
        obs = []
        df = self.df
        if len(df) < 5: return obs
        
        # Simplified Logic for Robustness:
        # Bullish OB: Red Candle followed by Green Candle that Engulfs or moves strongly
        # We look for "Impulse" moves
        
        for i in range(2, len(df)-2):
            try:
                curr = df.iloc[i]
                prev = df.iloc[i-1]
                nex = df.iloc[i+1]
                
                # Identify Bullish OB
                # 1. Previous candle was Red (Close < Open)
                is_red = prev['close'] < prev['open']
                # 2. Current/Next sequence moves Up strongly (e.g. Next closes above Prev High)
                strong_move_up = nex['close'] > prev['high']
                
                if is_red and strong_move_up:
                    obs.append({
                        "type": "bullish_ob",
                        "top": float(prev['high']),
                        "bottom": float(prev['low']),
                        "time": str(prev['timestamp']),
                        "mitigated": False
                    })
                    
                # Identify Bearish OB
                # 1. Previous candle was Green
                is_green = prev['close'] > prev['open']
                # 2. Current/Next sequence moves Down strongly
                strong_move_down = nex['close'] < prev['low']
                
                if is_green and strong_move_down:
                    obs.append({
                        "type": "bearish_ob",
                        "top": float(prev['high']),
                        "bottom": float(prev['low']),
                        "time": str(prev['timestamp']),
                        "mitigated": False
                    })
            except:
                continue
                
        return obs

    def detect_supply_demand_zones(self) -> List[Dict]:
        """
        Detects Supply and Demand zones (Rally-Base-Drop, Drop-Base-Rally).
        A 'Base' is a consolidation candle with a small body.
        """
        zones = []
        df = self.df
        if len(df) < 3: return zones

        for i in range(1, len(df) - 1):
            try:
                prev = df.iloc[i-1]
                base = df.iloc[i]
                nex = df.iloc[i+1]

                # Calculate body size for "Base" candle detection
                base_body = abs(base['close'] - base['open'])
                base_range = base['high'] - base['low']
                is_base = base_body < (base_range * 0.4) # Small body relative to range

                if not is_base: continue

                # Rally-Base-Drop (Supply Zone)
                if prev['close'] > prev['open'] and nex['close'] < nex['low']:
                    zones.append({
                        "type": "supply",
                        "top": float(base['high']),
                        "bottom": float(base['low']),
                        "time": str(base['timestamp']),
                        "description": "Rally-Base-Drop"
                    })

                # Drop-Base-Rally (Demand Zone)
                if prev['close'] < prev['open'] and nex['close'] > nex['high']:
                    zones.append({
                        "type": "demand",
                        "top": float(base['high']),
                        "bottom": float(base['low']),
                        "time": str(base['timestamp']),
                        "description": "Drop-Base-Rally"
                    })
            except:
                continue
        return zones

    def detect_liquidity_sweeps(self) -> List[Dict]:
        """
        Detects sweeps of previous highs/lows (Stop Hunts).
        """
        sweeps = []
        df = self.df
        if len(df) < 10: return sweeps

        for i in range(5, len(df)):
            try:
                curr = df.iloc[i]
                # Look for a 5-candle swing low/high
                lookback = df.iloc[i-5:i]
                prev_low = lookback['low'].min()
                prev_high = lookback['high'].max()

                # Bullish Sweep: Price dips below previous low but closes above it
                if curr['low'] < prev_low and curr['close'] > prev_low:
                    sweeps.append({
                        "type": "bullish_sweep",
                        "level": float(prev_low),
                        "time": str(curr['timestamp']),
                        "description": "Liquidity Grab (Low)"
                    })

                # Bearish Sweep: Price spikes above previous high but closes below it
                if curr['high'] > prev_high and curr['close'] < prev_high:
                    sweeps.append({
                        "type": "bearish_sweep",
                        "level": float(prev_high),
                        "time": str(curr['timestamp']),
                        "description": "Liquidity Grab (High)"
                    })
            except:
                continue
        return sweeps

    def analyze(self) -> Dict:
        """
        Returns full analysis report including MQL5 expansions.
        """
        return {
            "fvg": self.detect_fair_value_gaps(),
            "ifvg": self.detect_inverse_fair_value_gaps(),
            "ob": self.detect_order_blocks(),
            "snd": self.detect_supply_demand_zones(),
            "sweeps": self.detect_liquidity_sweeps()
        }
