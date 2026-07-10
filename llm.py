"""
Quant-Core AI — llm.py (Phase 4)
----------------------------------
Responsible for calling the configured LLM API (OpenAI, Anthropic, or Gemini)
to generate a final trading recommendation (BUY/SELL/HOLD) and rationale.
"""

import os
import json
import re
import asyncio
from typing import Tuple, Optional
from dotenv import load_dotenv

# Load variables from .env
load_dotenv()

def get_llm_verdict(
    ticker: str,
    current_price: float,
    price_change_pct: float,
    rsi: Optional[float],
    sma_50: Optional[float],
    sma_200: Optional[float],
    macd: Optional[float],
    macd_signal: Optional[float],
    pe_ratio: Optional[float],
    market_cap: Optional[str],
    sector: Optional[str],
    industry: Optional[str],
    signal_tags: list[str],
    signal_summary: str
) -> Tuple[str, str]:
    """
    Calls the selected LLM provider to get a trading verdict (BUY/SELL/HOLD) and rationale.
    
    Returns:
        Tuple[str, str]: (verdict, rationale)
        verdict is one of: "BUY", "SELL", "HOLD"
    """
    provider = os.getenv("LLM_PROVIDER", "openai").lower().strip()
    
    # ── 1. Prompt Construction ────────────────────────────────────────────────
    tags_str = ", ".join(f"`{t}`" for t in signal_tags) if signal_tags else "None"
    
    prompt = f"""You are a professional quantitative financial analyst bot named Quant-Core AI.
Analyze the following stock data and technical indicators for {ticker}:

[Price Data]
- Current Price: ${current_price:,.2f}
- Daily Change: {price_change_pct:+.2f}%

[Technical Indicators]
- RSI (14): {rsi if rsi is not None else "N/A"}
- SMA 50: {f"${sma_50:,.2f}" if sma_50 is not None else "N/A"}
- SMA 200: {f"${sma_200:,.2f}" if sma_200 is not None else "N/A"}
- MACD: {macd if macd is not None else "N/A"}
- MACD Signal: {macd_signal if macd_signal is not None else "N/A"}

[Company Fundamentals]
- P/E Ratio: {pe_ratio if pe_ratio is not None else "N/A"}
- Market Cap: {market_cap or "N/A"}
- Sector: {sector or "N/A"}
- Industry: {industry or "N/A"}

[Quant Signal Tags]
{tags_str}

[Quant Signal Details]
{signal_summary or "No strong directional signals."}

Based on this information, provide a trading recommendation (BUY, SELL, or HOLD) and a concise, professional, bulleted explanation (maximum 3 sentences or bullet points).

Your response MUST be a valid JSON object in this exact format:
{{
  "verdict": "BUY",
  "rationale": "Your short rationale here."
}}

Response:"""

    # ── 2. Call Provider API ──────────────────────────────────────────────────
    try:
        if provider == "openai":
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key or api_key.startswith("sk-..."):
                return "HOLD", "⚠️ **Awaiting OpenAI API Key Configuration** — Please set `OPENAI_API_KEY` in your `.env` file."
            
            from openai import OpenAI
            client = OpenAI(api_key=api_key, timeout=15.0)
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a quantitative financial analyst. Output raw JSON only."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.2,
                max_tokens=250
            )
            raw_text = response.choices[0].message.content or ""
            
        elif provider == "gemini":
            api_key = os.getenv("GEMINI_API_KEY")
            if not api_key or api_key == "...":
                return "HOLD", "⚠️ **Awaiting Gemini API Key Configuration** — Please set `GEMINI_API_KEY` in your `.env` file."
            
            # Using Gemini via the OpenAI-compatible endpoint
            from openai import OpenAI
            client = OpenAI(
                api_key=api_key,
                base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
                timeout=15.0
            )
            response = client.chat.completions.create(
                model="gemini-1.5-flash",
                messages=[
                    {"role": "system", "content": "You are a quantitative financial analyst. Output raw JSON only."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.2,
                max_tokens=250
            )
            raw_text = response.choices[0].message.content or ""
            
        elif provider == "anthropic":
            api_key = os.getenv("ANTHROPIC_API_KEY")
            if not api_key or api_key.startswith("sk-ant-..."):
                return "HOLD", "⚠️ **Awaiting Anthropic API Key Configuration** — Please set `ANTHROPIC_API_KEY` in your `.env` file."
            
            from anthropic import Anthropic
            client = Anthropic(api_key=api_key, timeout=15.0)
            response = client.messages.create(
                model="claude-3-haiku-20240307",
                max_tokens=250,
                temperature=0.2,
                system="You are a quantitative financial analyst. Output raw JSON only.",
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            # Anthropic returns content blocks
            raw_text = response.content[0].text if response.content else ""
            
        else:
            return "HOLD", f"❌ **Error:** Unsupported LLM provider: `{provider}`. Supported: `openai`, `gemini`, `anthropic`"

        # ── 3. Parse JSON Response ────────────────────────────────────────────
        match = re.search(r"\{.*\}", raw_text, re.DOTALL)
        if match:
            data = json.loads(match.group(0))
            verdict = data.get("verdict", "HOLD").upper().strip()
            rationale = data.get("rationale", "No explanation provided.")
            
            # Sanity check verdict values
            if verdict not in ["BUY", "SELL", "HOLD"]:
                verdict = "HOLD"
                
            return verdict, rationale
        else:
            return "HOLD", f"❌ **Error:** Failed to parse JSON from LLM response. Raw output:\n```\n{raw_text[:200]}\n```"
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        return "HOLD", f"❌ **Error invoking LLM ({provider}).** Please check the bot logs for details."
