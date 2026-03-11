import pandas as pd
import numpy as np
from typing import Dict, List, Any

class VolumeProfile:
    """
    Implements Volume Profile concepts:
    - Point of Control (POC): Price level with highest volume
    - Value Area (VA): 70% of total volume around POC
    - High Volume Nodes (HVN) & Low Volume Nodes (LVN)
    """

    def __init__(self, df: pd.DataFrame, bins: int = 50):
        self.df = df.copy()
        self.bins = bins
        self.df.columns = [c.lower() for c in self.df.columns]
        
        if 'volume' not in self.df.columns:
            # If no volume data, profile is impossible
            self.profile = None
        else:
            self.profile = self._calculate_profile()

    def _calculate_profile(self) -> pd.DataFrame:
        """
        Groups volume by price levels (bins).
        """
        df = self.df
        price_min = df['low'].min()
        price_max = df['high'].max()
        
        if price_min == price_max:
            return None

        # Create price bins
        price_bins = np.linspace(price_min, price_max, self.bins + 1)
        
        # Calculate volume for each bin
        # We assign candle volume to the bin containing the close price (simplification)
        df['price_bin'] = pd.cut(df['close'], bins=price_bins)
        
        profile_raw = df.groupby('price_bin', observed=True)['volume'].sum().reset_index()
        
        # Brute-force: Reconstruct dataframe to strip ALL categorical metadata
        profile = pd.DataFrame({
            'bin_center': [float(x.mid) for x in profile_raw['price_bin']],
            'volume': profile_raw['volume'].astype(float)
        })
        
        profile = profile.sort_values('volume', ascending=False)
        return profile

    def get_poc(self) -> Dict[str, Any]:
        """
        Returns the Point of Control (highest volume price).
        """
        if self.profile is None or self.profile.empty:
            return {"price": 0, "volume": 0}
            
        poc_row = self.profile.iloc[0]
        return {
            "price": float(poc_row['bin_center']),
            "volume": float(poc_row['volume'])
        }

    def get_value_area(self, percentage: float = 0.7) -> Dict[str, Any]:
        """
        Calculates Value Area (VAH and VAL).
        """
        if self.profile is None or self.profile.empty:
            return {"vah": 0, "val": 0}

        # Sort by price to calculate cumulative volume from center
        sorted_profile = self.profile.sort_values('bin_center')
        total_volume = sorted_profile['volume'].sum()
        target_volume = total_volume * percentage
        
        poc_price = self.get_poc()['price']
        
        # Simple VA: Expand from POC until target volume reached
        # Real TPO/Volume profiles are more complex, but this works for signals
        sorted_profile['dist_from_poc'] = abs(sorted_profile['bin_center'] - poc_price)
        va_candidates = sorted_profile.sort_values('dist_from_poc')
        
        va_candidates['cum_volume'] = va_candidates['volume'].cumsum()
        va_bins = va_candidates[va_candidates['cum_volume'] <= target_volume]
        
        if va_bins.empty:
            return {"vah": poc_price, "val": poc_price}

        return {
            "vah": float(va_bins['bin_center'].max()),
            "val": float(va_bins['bin_center'].min())
        }

    def detect_high_low_nodes(self) -> Dict[str, List[float]]:
        """
        Returns HVN (peaks) and LVN (valleys) in the volume distribution.
        """
        if self.profile is None or self.profile.empty:
            return {"hvn": [], "lvn": []}

        sorted_profile = self.profile.sort_values('bin_center')
        vols = sorted_profile['volume'].values
        prices = sorted_profile['bin_center'].values
        
        hvn = []
        lvn = []
        
        # Peak/Valley detection
        for i in range(1, len(vols) - 1):
            # HVN: Local Maxima
            if vols[i] > vols[i-1] and vols[i] > vols[i+1]:
                hvn.append(float(prices[i]))
            # LVN: Local Minima (significant drop in volume)
            elif vols[i] < vols[i-1] and vols[i] < vols[i+1]:
                lvn.append(float(prices[i]))
                
        return {"hvn": hvn, "lvn": lvn}

    def analyze(self) -> Dict[str, Any]:
        """
        Full volume analysis.
        """
        if self.profile is None:
            return {"status": "error", "message": "No volume data found"}

        poc = self.get_poc()
        va = self.get_value_area()
        nodes = self.detect_high_low_nodes()
        
        return {
            "status": "success",
            "poc": poc['price'],
            "vah": va['vah'],
            "val": va['val'],
            "hvn": nodes['hvn'],
            "lvn": nodes['lvn']
        }
