# Project Directory Overview

## CleanLogs
**Cleaning Logs**
- Directory for storing logs generated during the one-click cleaning process.

## SampleScrubber
**Sample Cleaning Tools**
- **ModuleTest**: Unit tests for modules.
- **util**
    - `distance.py`: Computes distances between values.
    - `getNum.py`: Evaluates cleaning accuracy.
- `uniop_model.py`: Rule mining model.
- `param_builder.py`: Constructs rule parameters.
- `param_selector.py`: Selects optimal parameters.
- **cleaners**
    - `single.py`: Single-attribute operators.
    - `multiple.py`: Multi-attribute relational operators.
    - `soft.py`: Experimental or soft operators.
    - `clean_penalty.py`: Calculates cleaning costs (edit distance, semantic penalties, Jaccard penalties).


## Main Scripts
- `main.py`: Command-line entry point for one-click data cleaning.
- `logsetting.py`: Logging configuration for the one-click pipeline.
- `Clean.py`: Core script for terminal-based cleaning logic.
- `requirements.txt`: Dependency list for the one-click cleaning system.
``- `Plantuml.svg`: Flowchart visualizing the cleaning pipeline.