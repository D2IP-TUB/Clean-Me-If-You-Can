from ollama import Client

def getClient(base_url):
    client = Client(host=base_url)
    return client

def askLLM(promptStr, client, modelname='mistral:7b'):
    response = client.chat(model=modelname, messages=[
      {
        'role': 'user',
        'content': promptStr,
      },
    ])

    resStr = response['message']['content']
    return resStr