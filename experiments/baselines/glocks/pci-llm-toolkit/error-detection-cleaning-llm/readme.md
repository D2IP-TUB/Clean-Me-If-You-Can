# Error Detection and Cleaning with Large Language Models (LLM)
This Python program reads records from a list of .csv files. The data is used to fill out a prompt template, and the filled-out prompt is sent to the LLM. The result of the LLM is parsed and saved to a .csv file. 

The prompt that we use can be found in [prompt.json](data/experiments_5000/prompt.json). For our experiments, we use 'p4', but we also provide three prompts that are earlier stages of 'p4'. Note that due the addresses we used being Austrian the prompts are written in German. 

## Parameter
There are two files used to set important parameters.\
connection.json ... contains all the information necessary to connect to a LLM
* llm-package ... currently we support OpenAI and Ollama
* runtime_environment ... name of the environment, saved into the csv output
* modelname ... name of the model to use, e.g. casperhansen/llama-3.3-70b-instruct-awq
* api_key ... your api_key to connect to your model
* base_url ... Url to your model

parameter.json ... contains parameters to configure the workflow 
* location ... defines which workflow config should be used,
* modelConfigName ... name of the connection you want to use that is specified in the connection.json
* whichColMatchDict ... name of a dictionary to rename column names from different data inputs. The dictionary must be defined in the code. This is just a switch variable.  
* Paths ... define the paths where to find the files
    * Prompt ... where the prompt.json is located, e.g., /data
    * Data ... Parent directory for the input data, e.g.,/data
    * Result ... parent directory for the result files /data/experiments_5000/
* Input ... list of input files keys, e.g., '1', '2'
* Files ... array to specify different input files, the keys are used in the Input list
    * name": name of an input file (parent directory is specified in the paths list), e.g., trainGenData_adressPerson_dirtyPol_whole_025.csv
    * encoding ... any encoding that is not the default pandas.read_csv encoding, else None
    * delimiter ... any delimiter that is not the default pandas.read_csv encoding, else None
    * OutputSuffix ... a suffix for the output file, e.g., 025

## CMD
run via command line:
> pip install -r requirements.txt \
> cd code \
> pyhton main.py

## Docker
run vi docker:

> docker build -t llm-detect-clean .
>
> docker run --name llm-detect-clean --gpus all -v ./data/:/data -v ./code:/code -itd llm-detect-clean


