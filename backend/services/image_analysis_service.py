"""
Image analysis service for processing trading charts with AI vision.
Handles multiple AI model fallbacks and provides robust error handling.
"""

import asyncio
import json
import re
from typing import List, Dict, Any, Optional, Union
from PIL import Image
import io
from google import genai

from backend.config.secure_config import config_manager
from backend.exceptions import ModelGenerationError, APIKeyMissingError

class ImageAnalysisService:
    """Service for analyzing trading charts using AI vision models"""
    
    def __init__(self):
        self.api_key = None
        self.client = None
        self._initialize_client()
    
    def _initialize_client(self):
        """Initialize Gemini client with secure API key"""
        try:
            self.api_key = config_manager.get_required_api_key("gemini")
            self.client = genai.Client(api_key=self.api_key)
        except APIKeyMissingError:
            print("Warning: Gemini API key not configured")
            self.client = None
    
    async def analyze_images(self, images: List[Image.Image]) -> Dict[str, Any]:
        """
        Analyze multiple trading chart images and provide unified analysis.
        
        Args:
            images: List of PIL Image objects
            
        Returns:
            Dictionary containing analysis results
        """
        if not images:
            raise ValueError("No images provided for analysis")
        
        if not self.client:
            raise ModelGenerationError("Gemini client not initialized")
        
        try:
            # Generate analysis using fallback logic
            result = await self._generate_with_fallback(images)
            
            # Enhance with real-time data if ticker detected
            if result.get('ticker_detected') and result['ticker_detected'] != 'NULL':
                result = await self._enrich_with_real_data(result)
            
            return result
            
        except Exception as e:
            return self._create_error_response(str(e))
    
    async def _generate_with_fallback(self, images: List[Image.Image]) -> Dict[str, Any]:
        """Generate analysis with multiple model fallbacks"""
        
        # Priority list of models
        models = [
            'gemini-2.0-flash',
            'gemini-1.5-flash', 
            'gemini-1.5-pro'
        ]
        
        prompt = self._create_analysis_prompt(len(images))
        
        last_error = None
        
        for model_name in models:
            try:
                print(f"Attempting analysis with model: {model_name}")
                
                # Prepare input for the model
                model_input = [prompt] + images
                
                try:
                    # Check if client is available
                    if self.client is None:
                        raise ModelGenerationError("Gemini client not initialized")
                    
                    # Simple approach - use direct API call
                    response = await asyncio.get_event_loop().run_in_executor(
                        None,
                        lambda: self.client.models.generate_content(
                            model=model_name,
                            contents=model_input
                        )
                    )
                    
                    if response and response.text:
                        print(f"Success with {model_name}")
                        return self._parse_response(response.text)
                        
                except Exception as api_error:
                    print(f"Failed with {model_name}: {api_error}")
                    last_error = api_error
                    continue
                
                if response and response.text:
                    print(f"Success with {model_name}")
                    return self._parse_response(response.text)
                    
            except Exception as e:
                print(f"Failed with {model_name}: {e}")
                last_error = e
                continue
        
        # All models failed
        if last_error:
            raise ModelGenerationError(f"All AI models failed: {last_error}")
        else:
            raise ModelGenerationError("No response from any model")
    
    def _create_analysis_prompt(self, num_images: int) -> str:
        """Create detailed prompt for chart analysis"""
        
        if num_images == 1:
            timeframe_context = "the provided chart"
        else:
            timeframe_context = "the provided charts as CROSS-TIMEFRAME context"
        
        return f"""Analyze the provided financial chart(s) as an elite Hedge Fund Analyst.
        
        If multiple images are provided, treat them as {timeframe_context}.
        Synthesize a single, unified trade plan.

        YOUR TASKS:
        1. **OCR & Context**: 
           - EXTRACT Ticker (e.g., "NIFTY", "BANKNIFTY", "RELIANCE").
           - **CRITICAL**: If you see "SENSEX", "BSE", or "S&P BSE SENSEX", identify the ticker as "^BSESN".
           - Identify Timeframes (e.g., 5m, 1H, 1D).
        
        2. **Technical Analysis**: 
           - Identify patterns (Head & Shoulders, Flags, ICT FVG, Order Blocks).
           - Key Support/Resistance levels.
           - Volume analysis.
           - Trend direction and strength.
        
        3. **Action Plan (The "Trade Intelligence"):**
           - Decide: **BUY CALL** (Long), **BUY PUT** (Short), or **WAIT**.
           - Define specific **Entry Zone**.
           - Define **Target** (Take Profit).
           - Define **Stop Loss**.
           - Confidence level in the analysis.

        Return ONLY a valid JSON object:
        {{
            "is_chart": true,
            "ticker_detected": "SYMBOL OR NULL",
            "timeframe": "15m OR NULL",
            "current_price": 123.45,
            "patterns": ["Pattern1", "Pattern2"],
            "sentiment": "Bullish/Bearish/Neutral",
            "confidence": 0.85,
            "action_type": "BUY CALL | BUY PUT | WAIT", 
            "entry_zone": "120-122",
            "target": 130.0,
            "stop_loss": 115.0,
            "recommendation": "Detailed summary (e.g. 'Enter Long on pullback')",
            "analysis": "Comprehensive technical breakdown..."
        }}"""
    
    def _parse_response(self, response_text: str) -> Dict[str, Any]:
        """Parse AI model response and extract JSON"""
        try:
            response_text = response_text.strip()
            
            # Use regex to find JSON block more reliably
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
            else:
                json_str = response_text
            
            result = json.loads(json_str)
            
            # Validate required fields
            required_fields = ['is_chart', 'sentiment', 'confidence', 'action_type']
            for field in required_fields:
                if field not in result:
                    result[field] = 'UNKNOWN' if field != 'confidence' else 0.0
            
            return result
            
        except json.JSONDecodeError as e:
            raise ModelGenerationError(f"Failed to parse JSON response: {e}")
        except Exception as e:
            raise ModelGenerationError(f"Error parsing response: {e}")
    
    async def _enrich_with_real_data(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Enhance AI analysis with real-time market data"""
        try:
            ticker = result.get("ticker_detected")
            
            # Normalize Sensex ticker
            if ticker and any(x in ticker.upper() for x in ["SENSEX", "BSE"]):
                ticker = "^BSESN"
                result["ticker_detected"] = ticker
            
            if not ticker or ticker == "NULL":
                return result
            
            print(f"Fetching real-time data for {ticker}...")
            
            # Import here to avoid circular dependencies
            from backend.market_intelligence import get_market_intelligence
            
            # Auto-correct ticker for Yahoo Finance
            search_ticker = ticker
            if not ticker.startswith("^") and ticker.isalpha() and not ticker.endswith(".NS"):
                search_ticker = f"{ticker}.NS"
            
            tech_data = get_market_intelligence(search_ticker)
            
            # Synthesize AI vision with real data
            if "error" not in tech_data:
                analysis_addition = "\\n\\n**REAL-TIME DATA VERIFICATION**:\\n"
                analysis_addition += f"- Trend: {tech_data.get('trend', 'N/A')}\\n"
                analysis_addition += f"- RSI: {tech_data.get('momentum_rsi', 'N/A')} (Momentum)\\n"
                analysis_addition += f"- Volatility: {tech_data.get('volatility_atr', 'N/A')}\\n"
                
                result['analysis'] += analysis_addition
                
                # Sanity check confidence
                trend = tech_data.get('trend', '').lower()
                action = result.get('action_type', '').lower()
                
                if 'bullish' in trend and 'put' in action:
                    result['analysis'] += "\\n⚠️ **WARNING**: Chart looks Bearish but Real-Time Trend is Bullish. Reduce position size."
                    result['confidence'] = max(0.0, result['confidence'] - 0.2)
                elif 'bearish' in trend and 'call' in action:
                    result['analysis'] += "\\n⚠️ **WARNING**: Chart looks Bullish but Real-Time Trend is Bearish. Reduce position size."
                    result['confidence'] = max(0.0, result['confidence'] - 0.2)
            
            return result
            
        except Exception as e:
            print(f"Error enriching with real data: {e}")
            # Return original result if enrichment fails
            return result
    
    def _create_error_response(self, error_message: str) -> Dict[str, Any]:
        """Create standardized error response"""
        return {
            "is_chart": False,
            "patterns": ["System Error"],
            "sentiment": "Neutral",
            "confidence": 0.0,
            "action_type": "WAIT",
            "recommendation": "Analysis Failed",
            "analysis": f"System Error: {error_message}",
            "error": error_message
        }

# Global service instance
image_analysis_service = ImageAnalysisService()
