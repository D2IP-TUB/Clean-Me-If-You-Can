# ZeroDCcorrection
**ZeroDCcorrection** is a training-free and explainable error correction system powered by large language models (LLMs). This repository contains the source code for the paper "ZeroDCcorrection: A Zero-Training Error Correction System with Large Language Models".
## Getting Started

### Installation

To set up the environment and get started with ZeroDCcorrection, follow these steps:

   ```
   # Create a new environment with Python 3.10
   conda create -n zerodccorrection python=3.10
   conda activate zerodccorrection

   # Install PyTorch with the specified version and CUDA toolkit
   conda install pytorch==1.13.1 cudatoolkit=11.7 -c pytorch -c conda-forge

   # Clone the ZeroDCcorrection repository
   git clone https://github.com/YangChen32768/ZeroC.git
   cd ZeroC

   # Install required dependencies
   pip install -r requirements.txt
   ```
### Dataset

All the data used in this work can be found in `datasets` folder.

## Running ZeroDCcorrection

ZeroDCcorrection employs large language models (LLMs) for effective and explainable error correction. You can choose any LLM to run ZeroDCcorrection.

To run ZeroDCcorrection, specify the following parameters:

* `OPENAI_API_BASE`: the base URL of the LLM API (e.g., OpenAI API)
* `MODEL_NAME`: the name of the LLM model (e.g., "gpt-3.5-turbo" or "gpt-4o")

You can also use a local LLM by performing end-to-end calls to the LLM.

To correct errors in a dataset, provide the dirty dataset and the error detection results, and run:
```
python correction.py
```

## Related Work
- Holoclean: [Paper](https://www.vldb.org/pvldb/vol10/p1190-rekatsinas.pdf) and [Code](https://github.com/HoloClean/holoclean)
- Baran: [Paper](https://vldb.org/pvldb/vol13/p1948-mahdavi.pdf) and [Code](https://github.com/BigDaMa/raha)
