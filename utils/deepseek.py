"""
RankPilot — DeepSeek API helper (shared across all AI features).
Uses deepseek-chat (V3) for all tasks — fast, cheap, capable.
"""
import os, sys, requests
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DEEPSEEK_API_URL = 'https://api.deepseek.com/v1/chat/completions'


def chat(prompt: str, max_tokens: int = 1500, temperature: float = 0.3,
         system: str = '') -> str:
    """Send a prompt to DeepSeek and return the response text. Returns '' on failure."""
    from core.config import DEEPSEEK_API_KEY
    if not DEEPSEEK_API_KEY:
        return ''
    messages = []
    if system:
        messages.append({'role': 'system', 'content': system})
    messages.append({'role': 'user', 'content': prompt})
    try:
        r = requests.post(
            DEEPSEEK_API_URL,
            headers={
                'Authorization': f'Bearer {DEEPSEEK_API_KEY}',
                'Content-Type': 'application/json',
            },
            json={
                'model': 'deepseek-chat',
                'messages': messages,
                'max_tokens': max_tokens,
                'temperature': temperature,
            },
            timeout=45
        )
        if r.status_code == 200:
            return r.json()['choices'][0]['message']['content'].strip()
        print(f'  ⚠️ DeepSeek API: HTTP {r.status_code} — {r.text[:200]}')
    except Exception as e:
        print(f'  ⚠️ DeepSeek API error: {e}')
    return ''


def is_available() -> bool:
    from core.config import DEEPSEEK_API_KEY
    return bool(DEEPSEEK_API_KEY)
