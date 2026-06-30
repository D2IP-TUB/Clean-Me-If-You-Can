
from openai import OpenAI

def getClient(api_key,base_url):
    client = OpenAI(
        api_key=api_key,
        base_url=base_url
    )
    return client

def askLLM(promptStr, client, modelname, picPath=None):
    model = modelname 
    if picPath is None:
        response = client.chat.completions.create(
            model=model,
            messages=[{
                    "role": "user",
                    "content": promptStr
                }
            ],
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

    resStr = response.to_dict()["choices"][0]["message"]["content"]
    return resStr
