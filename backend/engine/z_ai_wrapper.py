"""
z_ai_wrapper.py — Python wrapper for z.ai API (equivalent to z-ai-web-dev-sdk).

Reimplements the SDK's HTTP calls in Python so the HF Space backend
(or Render backend) can use z.ai without needing Node.js.

Auth: reads from .z-ai-config file or environment variables.
"""
import json, os, urllib.request

class ZAIWrapper:
    """Python equivalent of z-ai-web-dev-sdk for backend use."""
    
    def __init__(self, config=None):
        if config is None:
            config = self._load_config()
        self.config = config
        self.base_url = config.get("baseUrl", "https://internal-api.z.ai/v1")
        self.api_key = config.get("apiKey", "Z.ai")
        self.token = config.get("token", os.environ.get("ZAI_TOKEN", ""))
        self.chat_id = config.get("chatId", os.environ.get("ZAI_CHAT_ID", ""))
        self.user_id = config.get("userId", os.environ.get("ZAI_USER_ID", ""))
    
    def _load_config(self):
        """Load config from file or environment."""
        # Try config files
        for path in ["/etc/.z-ai-config", os.path.expanduser("~/.z-ai-config"), ".z-ai-config"]:
            if os.path.exists(path):
                with open(path) as f:
                    return json.load(f)
        # Fall back to environment variables
        return {
            "baseUrl": "https://internal-api.z.ai/v1",
            "apiKey": "Z.ai",
            "token": os.environ.get("ZAI_TOKEN", ""),
            "chatId": os.environ.get("ZAI_CHAT_ID", ""),
            "userId": os.environ.get("ZAI_USER_ID", ""),
        }
    
    def _headers(self):
        """Build auth headers (matches SDK exactly)."""
        h = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "X-Z-AI-From": "Z",
        }
        if self.chat_id:
            h["X-Chat-Id"] = self.chat_id
        if self.user_id:
            h["X-User-Id"] = self.user_id
        if self.token:
            h["X-Token"] = self.token
        return h
    
    def chat_completion(self, messages, model="glm-4-flash", temperature=0.7, max_tokens=8000):
        """Generate text via z.ai chat completions."""
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode(),
            headers=self._headers(),
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read().decode())
    
    def generate_image(self, prompt, size="1024x1024", model="cogview-3-flash"):
        """Generate an image via z.ai image generations."""
        payload = {
            "model": model,
            "prompt": prompt,
            "size": size,
        }
        req = urllib.request.Request(
            f"{self.base_url}/images/generations",
            data=json.dumps(payload).encode(),
            headers=self._headers(),
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read().decode())
    
    def generate_html_app(self, prompt, app_name, configure=""):
        """Generate a complete HTML app from a text prompt.
        
        Returns: HTML string
        """
        sys_prompt = f"""You are an expert app developer. Generate a COMPLETE, self-contained HTML file for an Android app called "{app_name}".
Requirements:
- Single HTML with embedded CSS+JS, dark theme (#0f0f1e bg, #e94560 accent)
- Mobile-first responsive design
- App purpose: {prompt}
- Additional config: {configure or 'none'}
- Include a top bar with app name + WhatsApp icon (opens https://whatsapp.com/channel/0029VaijFIC5Ejxq4oG6wX0E via intent URI)
- Privacy and Rate icons
- Professional UI
Return ONLY HTML code, no explanations."""
        
        resp = self.chat_completion([
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": "Generate the HTML app now."}
        ])
        
        html = resp.get("choices", [{}])[0].get("message", {}).get("content", "")
        
        # Extract HTML from code block
        if "```html" in html:
            html = html[html.find("```html") + 7:html.rfind("```")].strip()
        elif "```" in html:
            html = html[html.find("```") + 3:html.rfind("```")].strip()
        
        if not html.strip().startswith("<"):
            html = "<!DOCTYPE html>\n" + html
        
        return html
