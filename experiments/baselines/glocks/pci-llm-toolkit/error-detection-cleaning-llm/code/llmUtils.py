import pandas as pd


def getClient(llm_package,api_key,base_url):
    if llm_package == "ollama":
        import ollamaModels as ollamaMod
        client = ollamaMod.getClient(base_url)
    elif llm_package == "openai":
        import openAIModels as openAiMod
        client = openAiMod.getClient(api_key,base_url)
    elif llm_package == "google":
        import googleModels as googleMod
        client = googleMod.getClient()
    else:
        print("no llm package registered, no matching Client found")
        client = None
    return client

def askModel(llm_package,client,promptStr,modelname=None):
    if llm_package == "ollama":
        import ollamaModels as ollamaMod
        resStr = ollamaMod.askLLM(promptStr,client,modelname)
    elif llm_package == "openai":
        import openAIModels as openAiMod
        resStr = openAiMod.askLLM(promptStr,client,modelname)
    elif llm_package == "google":
        import googleModels as googleMod
        resStr = googleMod.askLLM(promptStr,client,modelname)
    elif llm_package == "huggingFace":
        import openAIModels as openAiMod
        resStr = openAiMod.askLLM(promptStr,client,modelname)
    else:
        print("no llm package registered, no matching Client found")
        resStr = None
    return resStr

def createResDf(list_of_tuples, colnames):
    dfAll = pd.DataFrame(list_of_tuples,
                    columns=colnames)
    return dfAll
