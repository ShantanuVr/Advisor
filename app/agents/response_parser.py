"""Response parser - parses Cursor analysis responses."""

import json
import re
from typing import Any, Dict


def extract_json_from_response(text: str) -> str:
    """
    Extract JSON from a response that might contain markdown code blocks
    or other text around it.
    """
    # Try to find JSON in code blocks first
    code_block_pattern = r'```(?:json)?\s*([\s\S]*?)\s*```'
    matches = re.findall(code_block_pattern, text)
    
    if matches:
        # Return the largest match (most likely to be the main JSON)
        return max(matches, key=len)
    
    # Try to find raw JSON (starts with { and ends with })
    # Look for the outermost braces
    start = text.find('{')
    if start == -1:
        raise ValueError("No JSON object found in response")
    
    # Find matching closing brace
    depth = 0
    for i, char in enumerate(text[start:], start):
        if char == '{':
            depth += 1
        elif char == '}':
            depth -= 1
            if depth == 0:
                return text[start:i+1]
    
    raise ValueError("No complete JSON object found in response")


def validate_signal_structure(signal: Dict[str, Any], symbol: str) -> Dict[str, Any]:
    """
    Validate and normalize a signal structure.
    Returns normalized signal with defaults for missing fields.
    """
    normalized = {
        "bias": signal.get("bias", "neutral"),
        "confidence": signal.get("confidence", 50),
        "levels": signal.get("levels", {}),
        "ict_notes": signal.get("ict_notes", ""),
        "turtle_soup": signal.get("turtle_soup"),
        "trade_plan": signal.get("trade_plan", {}),
    }
    
    # Validate bias
    if normalized["bias"] not in ["bullish", "bearish", "neutral"]:
        normalized["bias"] = "neutral"
    
    # Validate confidence
    try:
        normalized["confidence"] = float(normalized["confidence"])
        normalized["confidence"] = max(0, min(100, normalized["confidence"]))
    except (TypeError, ValueError):
        normalized["confidence"] = 50
    
    # Normalize turtle_soup
    if normalized["turtle_soup"]:
        ts = normalized["turtle_soup"]
        normalized["turtle_soup"] = {
            "detected": ts.get("detected", False),
            "direction": ts.get("direction"),
            "entry": ts.get("entry"),
            "invalidation": ts.get("invalidation"),
            "tp1": ts.get("tp1"),
            "tp2": ts.get("tp2"),
            "description": ts.get("description", ""),
        }
    
    return normalized


def parse_cursor_response(response_text: str) -> Dict[str, Any]:
    """
    Parse a Cursor analysis response into structured data.
    
    Expected input is JSON (possibly wrapped in markdown code blocks)
    with the structure defined in the prompt generator.
    
    Returns parsed data structure.
    Raises ValueError if parsing fails.
    """
    # Extract JSON from response
    json_str = extract_json_from_response(response_text)
    
    # Parse JSON
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON: {e}")
    
    # Validate structure
    if "signals" not in data:
        raise ValueError("Response must contain 'signals' object")
    
    signals = data["signals"]
    if not isinstance(signals, dict):
        raise ValueError("'signals' must be an object")
    
    # Normalize each signal
    normalized_signals = {}
    for symbol, signal in signals.items():
        if isinstance(signal, dict):
            normalized_signals[symbol.upper()] = validate_signal_structure(signal, symbol)
    
    return {
        "signals": normalized_signals,
        "market_context": data.get("market_context", ""),
        "news_impact": data.get("news_impact", ""),
    }


def save_response_to_file(response_text: str, date_str: str) -> str:
    """
    Save a response to the responses directory.
    Returns the file path.
    """
    from app.config import RESPONSES_DIR
    
    file_path = RESPONSES_DIR / f"{date_str}_response.json"
    
    # Try to parse and pretty-print
    try:
        json_str = extract_json_from_response(response_text)
        data = json.loads(json_str)
        formatted = json.dumps(data, indent=2)
    except Exception:
        formatted = response_text
    
    with open(file_path, "w") as f:
        f.write(formatted)
    
    return str(file_path)
