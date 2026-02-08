
from backend.options_indicators import OptionsGreeksAnalyzer

def analyze_specific_trade():
    analyzer = OptionsGreeksAnalyzer()
    
    # Example: Nifty 22000 CE, 7 days to expiry
    result = analyzer.calculate_black_scholes_greeks(
        spot_price=22150,
        strike_price=22000,
        time_to_expiry_days=7,
        implied_volatility=0.18,
        option_type="CE"
    )
    
    print("🔍 OPTION ANALYSIS")
    print("=" * 50)
    print(f"Spot: 22150 | Strike: 22000 | DTE: 7 | IV: 18%")
    print(f"Delta: {result['greeks']['delta']:.3f} (Directional exposure)")
    print(f"Gamma: {result['greeks']['gamma']:.5f} (Delta sensitivity)")
    print(f"Theta: {result['greeks']['theta']:.3f} (Time decay per day)")
    print(f"Vega: {result['greeks']['vega']:.3f} (Volatility sensitivity)")
    print(f"Probability ITM: {result['probabilities']['itm']:.1%}")
    
    print("\n⚠️  WARNINGS:")
    for signal in result['signals']:
        if signal[0] == "WARNING":
            print(f"  • {signal[2]}")
    
    print("\n🎯 RECOMMENDATION:")
    if result['greeks']['delta'] > 0.6:
        print("  High delta - Consider ITM or reduce position")
    elif result['greeks']['theta'] < -0.01:
        print("  High time decay - Avoid if holding > 2 days")
    else:
        print("  Good risk/rebalance - Consider entry")

if __name__ == "__main__":
    analyze_specific_trade()
