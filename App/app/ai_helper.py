import json
import requests
import time

def clean_text_with_ai(text, api_key, model="google/gemini-2.0-flash-001", prompt=""):
    if not api_key:
        print("AI Error: No OpenRouter API key provided.")
        return text

    if not text.strip():
        return text

    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/voysix/voysix", # Optional
        "X-Title": "Voysix", # Optional
    }

    data = {
        "model": model,
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": text}
        ]
    }

    try:
        print(f"AI: Sending request to OpenRouter ({model})...")
        start_time = time.time()
        response = requests.post(url, headers=headers, data=json.dumps(data), timeout=30)
        response.raise_for_status()
        
        result = response.json()
        if "choices" in result and len(result["choices"]) > 0:
            cleaned_text = result["choices"][0]["message"]["content"].strip()
            # Some models might return the text wrapped in quotes, let's strip them if they wrap the whole thing
            if cleaned_text.startswith('"') and cleaned_text.endswith('"'):
                cleaned_text = cleaned_text[1:-1].strip()
            
            elapsed = time.time() - start_time
            print(f"AI: Success ({elapsed:.2f}s). Original: '{text[:30]}...' -> Cleaned: '{cleaned_text[:30]}...'")
            return cleaned_text
        else:
            print(f"AI Error: Unexpected response format: {result}")
            return text
    except Exception as e:
        print(f"AI Error: {e}")
        return text

def get_openrouter_models():
    url = "https://openrouter.ai/api/v1/models"
    try:
        print("AI: Fetching models from OpenRouter...")
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        if "data" in data:
            return data["data"]
        return []
    except Exception as e:
        print(f"AI Error fetching models: {e}")
        return []
