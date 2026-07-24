"""
Minimum Spanning Tree (MST) for Market Structure Analysis
Shows how Nifty 50 stocks are interconnected
"""

import numpy as np
import pandas as pd
import yfinance as yf
try:
    from scipy.sparse.csgraph import minimum_spanning_tree
    from scipy.spatial.distance import pdist, squareform
except ImportError:
    minimum_spanning_tree = None
    pdist = None
    squareform = None

try:
    import networkx as nx
except ImportError:
    nx = None

try:
    import plotly.graph_objects as go
except ImportError:
    go = None

from datetime import datetime, timedelta

try:
    import statsmodels.api as sm
except ImportError:
    sm = None

class MinimumSpanningTreeAnalysis:
    """
    MST Analysis for Indian Market Structure
    Uses correlation-based distances to build market network
    """
    
    def __init__(self, nifty_stocks=None):
        self.nifty_stocks = nifty_stocks or self._get_default_nifty_stocks()
        self.correlation_matrix = None
        self.distance_matrix = None
        self.mst = None
        self.graph = None
        
    def _get_default_nifty_stocks(self):
        """Get Nifty 50 stocks"""
        return [
            "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS",
            "HINDUNILVR.NS", "ITC.NS", "SBIN.NS", "BHARTIARTL.NS", "KOTAKBANK.NS",
            "BAJFINANCE.NS", "LT.NS", "HCLTECH.NS", "ASIANPAINT.NS", "AXISBANK.NS",
            "MARUTI.NS", "SUNPHARMA.NS", "TITAN.NS", "WIPRO.NS", "ONGC.NS",
            "NTPC.NS", "POWERGRID.NS", "ULTRACEMCO.NS", "M&M.NS", "TECHM.NS",
            "INDUSINDBK.NS", "BAJAJFINSV.NS", "NESTLEIND.NS", "TATASTEEL.NS",
            "JSWSTEEL.NS", "BPCL.NS", "DRREDDY.NS", "GRASIM.NS",
            "ADANIPORTS.NS", "CIPLA.NS", "BRITANNIA.NS", "HEROMOTOCO.NS",
            "EICHERMOT.NS", "DIVISLAB.NS", "COALINDIA.NS", "BAJAJ-AUTO.NS",
            "SBILIFE.NS", "HINDALCO.NS", "HDFCLIFE.NS", "APOLLOHOSP.NS"
        ]
    
    def fetch_stock_data(self, period="3mo", interval="1d"):
        """Fetch data for all stocks"""
        print(f"📊 Fetching data for {len(self.nifty_stocks)} Nifty stocks...")
        
        # Try to use centralized data service for better caching and fallbacks
        try:
            from backend.services.market_data_service import get_sync_market_data
        except ImportError:
            get_sync_market_data = None

        data = {}
        for stock in self.nifty_stocks:
            try:
                if get_sync_market_data:
                    df = get_sync_market_data(stock, period, interval)
                else:
                    df = yf.download(stock, period=period, interval=interval, progress=False)
                
                if not df.empty:
                    # Data is already normalized if it comes from get_sync_market_data
                    # But we double check for safety
                    if 'Close' not in df.columns:
                        print(f"   ❌ {stock}: 'Close' column not found")
                        continue
                    
                    data[stock] = df['Close']
                    print(f"   ✅ {stock}: Data received ({len(df)} rows)")
                else:
                    print(f"   ⚠️ {stock}: No data returned")
            except Exception as e:
                # Catch yfinance NoneType error specifically if it manifests as TypeError
                if "object is not subscriptable" in str(e):
                    print(f"   ⚠️ {stock}: Data feed interrupted (Subscript Error)")
                else:
                    print(f"   ❌ {stock}: Error: {e}")
                pass
        
        # Create DataFrame
        if not data:
            return pd.DataFrame()

        df_prices = pd.DataFrame(data)
        
        # Forward fill missing data
        df_prices = df_prices.ffill().bfill()
        
        print(f"✅ Data fetched: {len(df_prices)} days, {df_prices.shape[1]} stocks")
        return df_prices
    
    def build_mst(self, df_prices):
        """
        Build Minimum Spanning Tree from stock returns
        """
        # Calculate returns
        returns = df_prices.pct_change().dropna()
        
        if returns.empty:
             return None

        # Correlation matrix
        correlation_matrix = returns.corr()
        self.correlation_matrix = correlation_matrix
        
        # Convert correlation to distance: d = √(2(1-ρ))
        distance_matrix = np.sqrt(2 * (1 - correlation_matrix.values))
        # Handle potential NaNs in distance if correlation is perfectly 1 or -1 or NaN
        distance_matrix = np.nan_to_num(distance_matrix)
        self.distance_matrix = distance_matrix
        
        # Build MST
        mst_matrix = minimum_spanning_tree(distance_matrix)
        self.mst = mst_matrix.toarray()
        
        # Create NetworkX graph
        self._create_graph(correlation_matrix, self.mst)
        
        return {
            'correlation_matrix': correlation_matrix.to_dict(),
            'distance_matrix': distance_matrix.tolist(),
            'mst_matrix': self.mst.tolist(),
            'graph_info': self._get_graph_info()
        }
    
    def _create_graph(self, correlation_matrix, mst_matrix):
        """Create NetworkX graph from MST"""
        G = nx.Graph()
        
        # Add nodes
        stocks = correlation_matrix.columns.tolist()
        for i, stock in enumerate(stocks):
            G.add_node(stock, name=stock.replace('.NS', ''))
        
        # Add edges from MST
        rows, cols = np.where(mst_matrix > 0)
        for i, j in zip(rows, cols):
             weight = mst_matrix[i, j]
             if i < len(stocks) and j < len(stocks):
                G.add_edge(stocks[i], stocks[j], weight=weight,
                              correlation=correlation_matrix.iloc[i, j])
        
        self.graph = G
        return G
    
    def _get_graph_info(self):
        """Get graph statistics"""
        if self.graph is None:
            return None
        
        try:
            centrality = nx.degree_centrality(self.graph)
            betweenness = nx.betweenness_centrality(self.graph, weight='weight')
            
            # Find most central stocks
            top_central = sorted(centrality.items(), key=lambda x: x[1], reverse=True)[:10]
            top_between = sorted(betweenness.items(), key=lambda x: x[1], reverse=True)[:10]
            
            return {
                'num_nodes': self.graph.number_of_nodes(),
                'num_edges': self.graph.number_of_edges(),
                'average_degree': np.mean([d for n, d in self.graph.degree()]),
                'top_central_stocks': [(s.replace('.NS', ''), v) for s, v in top_central],
                'top_between_stocks': [(s.replace('.NS', ''), v) for s, v in top_between],
            }
        except Exception as e:
            print(f"Error calculating graph info: {e}")
            return {}
    
    def detect_market_regimes(self, df_prices, window=20):
        """
        Detect market regimes using MST dynamics
        """
        returns = df_prices.pct_change().dropna()
        regimes = []
        
        if len(returns) < window + 5:
             # Not enough data for rolling window
             return {'current_regime': 'INSUFFICIENT_DATA', 'regimes': pd.DataFrame()}

        for i in range(window, len(returns), 5):  # Step every 5 days
            window_returns = returns.iloc[i-window:i]
            
            if len(window_returns) < window: continue

            # Build MST for this window
            corr = window_returns.corr()
            dist = np.sqrt(2 * (1 - corr.values))
            dist = np.nan_to_num(dist)
            mst = minimum_spanning_tree(dist).toarray()
            
            # Calculate MST statistics
            # Normalised Tree Length could be simple sum of weights
            tree_length = np.sum(mst)
            
            # Track regime
            regimes.append({
                'date': returns.index[i],
                'mst_length': tree_length,
                'avg_correlation': corr.values.mean(),
                'market_stress': self._calculate_stress_index(corr)
            })
        
        df_regimes = pd.DataFrame(regimes)
        if df_regimes.empty:
            return {'current_regime': 'UNKNOWN', 'regimes': df_regimes}

        return {
            'regimes': df_regimes.to_dict(orient='records'),
            'current_regime': self._classify_current_regime(df_regimes.iloc[-1])
        }
    
    def _calculate_stress_index(self, correlation_matrix):
        """Calculate market stress index"""
        # When correlations approach 1, market is stressed
        avg_corr = correlation_matrix.values.mean()
        return min(1.0, max(0.0, (avg_corr - 0.3) / 0.7))  # Normalize to 0-1
    
    def _classify_current_regime(self, current_stats):
        """Classify current market regime"""
        if current_stats['market_stress'] > 0.7:
            return "HIGH_STRESS_CORRELATED"
        elif current_stats['market_stress'] < 0.3:
            return "LOW_STRESS_DIVERSE"
        else:
            return "NORMAL_MARKET"
    
    def generate_trading_ideas(self, df_prices):
        """
        Generate pairs trading ideas from MST analysis
        """
        returns = df_prices.pct_change().dropna()
        correlation_matrix = returns.corr()
        
        pairs = []
        
        # Find highly correlated pairs that are connected in MST
        if self.graph is None: return []
        
        nodes = list(self.graph.nodes())
        
        for i in range(len(nodes)):
            for j in range(i+1, len(nodes)):
                stock1 = nodes[i]
                stock2 = nodes[j]
                
                # Check if connected in MST (Direct Edge)
                if self.graph.has_edge(stock1, stock2):
                    edge_data = self.graph.get_edge_data(stock1, stock2)
                    corr = edge_data.get('correlation', 0)
                    
                    if corr > 0.7:
                        # Calculate spread
                        spread = returns[stock1] - returns[stock2]
                        
                        # Z-score of spread
                        spread_mean = spread.mean()
                        spread_std = spread.std()
                        if spread_std == 0: continue
                        
                        current_z = (spread.iloc[-1] - spread_mean) / spread_std
                        
                        pairs.append({
                            'pair': f"{stock1.replace('.NS', '')}-{stock2.replace('.NS', '')}",
                            'correlation': corr,
                            'current_z': current_z,
                            'trade_signal': self._generate_pair_signal(current_z),
                            'half_life': 5 # Simplified
                        })
        
        # Sort by correlation and Z-score
        pairs.sort(key=lambda x: (x['correlation'], abs(x['current_z'])), reverse=True)
        return pairs[:10]  # Top 10 pairs
    
    def _generate_pair_signal(self, z_score, entry_threshold=1.5, exit_threshold=0.5):
        """Generate trading signal for pairs"""
        if z_score > entry_threshold:
            return "SHORT_SPREAD"  # Sell stock1, Buy stock2
        elif z_score < -entry_threshold:
            return "LONG_SPREAD"   # Buy stock1, Sell stock2
        elif abs(z_score) < exit_threshold:
            return "EXIT_SPREAD"
        else:
            return "HOLD"
    
    def create_visualization(self):
        """Create interactive MST visualization"""
        if self.graph is None:
            return None
        
        try:
            # Get positions using spring layout
            pos = nx.spring_layout(self.graph, weight='weight', seed=42)
            
            # Create edges
            edge_x = []
            edge_y = []
            
            for edge in self.graph.edges():
                x0, y0 = pos[edge[0]]
                x1, y1 = pos[edge[1]]
                edge_x.extend([x0, x1, None])
                edge_y.extend([y0, y1, None])
            
            edge_trace = go.Scatter(
                x=edge_x, y=edge_y,
                line=dict(width=1, color='gray'),
                hoverinfo='none',
                mode='lines'
            )
            
            # Create nodes
            node_x = []
            node_y = []
            node_text = []
            
            for node in self.graph.nodes():
                x, y = pos[node]
                node_x.append(x)
                node_y.append(y)
                node_text.append(node.replace('.NS', ''))
            
            node_trace = go.Scatter(
                x=node_x, y=node_y,
                mode='markers+text',
                text=node_text,
                textposition="top center",
                marker=dict(
                    color='lightblue',
                    size=10,
                    line_width=2
                )
            )
            
            # Create figure
            fig = go.Figure(data=[edge_trace, node_trace],
                        layout=go.Layout(
                            title='Nifty 50 Minimum Spanning Tree',
                            showlegend=False,
                            hovermode='closest',
                            margin=dict(b=20, l=5, r=5, t=40),
                            xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                            yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                            height=700
                        ))
            
            return fig
        except Exception as e:
            print(f"Error creating visualization: {e}")
            return None

class RealTimeMSTTrader:
    """Real-time MST-based trading system"""
    
    def __init__(self):
        self.mst_analyzer = MinimumSpanningTreeAnalysis()
        self.current_mst = None
        self.current_regime = None
        
    def run_daily_analysis(self):
        """Run daily MST analysis"""
        print("\n" + "="*70)
        print("🌳 MINIMUM SPANNING TREE ANALYSIS - NIFTY 50")
        print("="*70)
        
        try:
            # Fetch data
            df_prices = self.mst_analyzer.fetch_stock_data(period="3mo", interval="1d")
            
            if df_prices.empty:
                print("❌ No data available")
                return None
            
            # Build MST
            print("\n🔗 Building Minimum Spanning Tree...")
            mst_data = self.mst_analyzer.build_mst(df_prices)
            if not mst_data:
                 print("Could not build MST (Correlation error).")
                 return None

            # Detect regimes
            print("\n📊 Analyzing market regimes...")
            regime_data = self.mst_analyzer.detect_market_regimes(df_prices)
            
            # Generate trading ideas
            print("\n🎯 Generating pairs trading ideas...")
            pairs = self.mst_analyzer.generate_trading_ideas(df_prices)
            
            # Get graph info
            graph_info = mst_data['graph_info']
            
            # Store current state
            self.current_mst = mst_data
            self.current_regime = regime_data['current_regime']
            
            # Print results
            print(f"\n📈 MARKET STRUCTURE:")
            print(f"   Current Regime: {regime_data['current_regime']}")
            
            if pairs:
                print(f"\n💡 PAIRS TRADING OPPORTUNITIES:")
                for pair in pairs[:5]:
                    signal = pair['trade_signal']
                    print(f"   • {pair['pair']}: {signal} (Z={pair['current_z']:.2f}, Corr={pair['correlation']:.3f})")
            
            # Create visualization
            print(f"\n📊 Generating visualization...")
            fig = self.mst_analyzer.create_visualization()
            if fig:
                fig.write_html("nifty_mst_visualization.html")
                print(f"   ✅ Visualization saved to 'nifty_mst_visualization.html'")
            
            return {
                'mst_data': mst_data,
                'regime_data': regime_data,
                'trading_pairs': pairs,
                'graph_info': graph_info,
                'timestamp': datetime.now().isoformat()
            }
        except Exception as e:
            import traceback
            print(f"❌ Error in MST Analysis: {e}")
            traceback.print_exc()
            return None
