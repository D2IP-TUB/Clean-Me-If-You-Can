
from google import genai
from google.genai import types

def getClient():
    client = genai.Client()
    return client

def askLLM(promptStr, client, modelname, picPath=None):
    model = modelname
    # Disable thinking for 2.5 models to ensure response.text is populated
    _config = types.GenerateContentConfig(
        thinking_config=types.ThinkingConfig(thinking_budget=0)
    )
    if picPath is None:
        response = client.models.generate_content(
            model=model,
            contents=promptStr,
            config=_config,
        )
    else:
        messages = [{
                "role": "user",
                "content": {
                    "content": "Hello, how are you?",
                    "files": [
                        {
                            "type": "image",
                            "path": 'C:\\Users\\glock\\Downloads\\002_smalldatajourney-1.png'
                        }
                    ]
                }
            }
        ]

    resStr = response.text
    if resStr is None:
        # Newer SDK versions don't expose .text directly — extract from candidates
        try:
            resStr = response.candidates[0].content.parts[0].text
        except (AttributeError, IndexError, TypeError):
            resStr = None
    if resStr is None:
        candidates = getattr(response, 'candidates', [])
        finish = getattr(candidates[0], 'finish_reason', None) if candidates else None
        raise ValueError(f"Empty response text (finish_reason={finish})")
    return resStr
