
import re
import pandas as pd

# Display labels used in prompts / parseAnswer (column_name → label).
_FIELD_DISPLAY = {
    "house_number": "House Number",
    "country_code": "Country Code",
    "date_published": "Date Published",
    "number_of_pages": "Number Of Pages",
}

# Other-domain prompt IDs (detection / correction).
_OTHER_DETECTION_IDS = {"p21", "p23"}
_OTHER_CORRECTION_IDS = {"p22", "p24"}
_OTHER_PROMPT_FIELDS = {
    "p21": ["title", "author", "isbn", "date_published", "publisher", "number_of_pages"],
    "p22": ["title", "author", "isbn", "date_published", "publisher", "number_of_pages"],
    "p23": ["title", "director", "actor", "date_published", "duration", "genre"],
    "p24": ["title", "director", "actor", "date_published", "duration", "genre"],
}


def _field_display(field: str) -> str:
    if field in _FIELD_DISPLAY:
        return _FIELD_DISPLAY[field]
    if field == "_id":
        return "Id"
    return field.replace("_", " ").title()


def _corr_label(field: str) -> str:
    """Correction answer label, e.g. date_published → Date_Published_corr."""
    return _field_display(field).replace(" ", "_") + "_corr"


class llmPrompt:
    promptId : str = str()
    promptStr : str = str()
    promptVarDict : dict = dict()
    colNameMatchingDict : dict = dict()

    def __init__(self) -> None:
        pass

    def __init__(self,promptId,promptStr,promptVarDict):
        self.promptId = promptId
        self.promptStr = promptStr
        self.promptVarDict = promptVarDict

    def __init__(self,promptId,promptStr,promptVarDict,colNameMatchingDict):
        self.promptId = promptId
        self.promptStr = promptStr
        self.promptVarDict = promptVarDict
        self.colNameMatchingDict = colNameMatchingDict

    def getPrompt(self):
        pStr = self.promptStr.format(**self.promptVarDict)
        pStr = pStr.replace('\\\\,',',')
        pStr = pStr.replace('\\,',',')
        return pStr
    
    def setValues(self,row):
        for key, value in self.colNameMatchingDict.items():
            if key not in row.index:
                continue
            self.promptVarDict[value] = None if pd.isna(row[key]) else row[key]
    
    def setColNameDict(self,colNameMatchingDictVal):
        self.colNameMatchingDict = colNameMatchingDictVal
        
    def setErrorFields(self, error_fields_list):
        """
        Set the error_fields variable with a formatted list of fields known to be erroneous
        
        Args:
            error_fields_list: List of field names that contain errors
        """
        if 'error_fields' in self.promptVarDict:
            error_fields_formatted = ""
            for field in error_fields_list:
                if field == "_id":
                    continue
                display_field = _field_display(field)
                error_fields_formatted += f'    "{display_field}": "contains error",\n'
            
            # Remove the last comma and newline
            if error_fields_formatted:
                error_fields_formatted = error_fields_formatted.rstrip(',\n')
            
            self.promptVarDict['error_fields'] = error_fields_formatted
    
    
def initPromptDict(prompt_connection_config,colNameMatchingDict=dict()):
    promptDict = dict()
    for key in prompt_connection_config:
        promptStr = "\n".join(prompt_connection_config[key]["promptStr"])
        colName = prompt_connection_config[key]["colname"]
        promptDict[key]=llmPrompt(key,promptStr,colName,colNameMatchingDict)

    return promptDict

def extractLineVal(answerStr,patternStr):
    findRes = re.findall(patternStr,answerStr)
    if len(findRes) > 0:
        resSplit = re.split(': ',findRes[0])
        if len(resSplit) > 1:
            return resSplit[1]
        else:
            return ''
    else:
        return ''


def _parse_labeled_fields(answerStr, fields, correction: bool) -> dict:
    """Extract per-field answers using display labels; rest-of-line capture."""
    out = {}
    for col in fields:
        if correction:
            label = _corr_label(col)
        else:
            label = _field_display(col)
        # Rest of line after "Label: " — permissive for titles/names with punctuation.
        pat = rf"{re.escape(label)}:[^\n]*"
        out[col] = extractLineVal(answerStr, pat).strip()
    return out


def parseAnswer(answerStr,prompt:llmPrompt,id:int):
    resDict = dict()
    if prompt.promptId in ['p5', 'p6', 'p14', 'p15', 'p16']:
        # Parse detected errors for address benchmark format
        idRes = extractLineVal(answerStr, r"Id:[ \w.-/]*").strip()
        nameRes = extractLineVal(answerStr, r"Name:[ \w.-/äöüßÄÖÜ(),']*").strip()
        hnRes = extractLineVal(answerStr, r"House Number:[ \w.-/]*").strip()
        roadRes = extractLineVal(answerStr, r"Road:[ \w.-/äöüßÄÖÜ(),']*").strip()
        postcodeRes = extractLineVal(answerStr, r"Postcode:[ \w.-/]*").strip()
        localityRes = extractLineVal(answerStr, r"Locality:[ \w.-/äöüßÄÖÜ(),']*").strip()
        regionRes = extractLineVal(answerStr, r"Region:[ \w.-/äöüßÄÖÜ(),']*").strip()
        countryRes = extractLineVal(answerStr, r"Country:[ \w.-/äöüßÄÖÜ(),']*").strip()
        countryCodeRes = extractLineVal(answerStr, r"Country Code:[ \w.-/]*").strip()
        
        resDict = {'id': id, '_id': idRes, 'name': nameRes, 'house_number': hnRes, 'road': roadRes,
                   'postcode': postcodeRes, 'locality': localityRes, 'region': regionRes,
                   'country': countryRes, 'country_code': countryCodeRes,
                   'PromptId': prompt.promptId,
                   'Prompt': prompt.getPrompt(), 'Antwort': answerStr}

    elif prompt.promptId in ['p9', 'p10', 'p18', 'p19', 'p20']:
        # Parse corrected values for address benchmark format
        idRes = extractLineVal(answerStr, r"Id_corr:[ \w.-/]*").strip()
        nameRes = extractLineVal(answerStr, r"Name_corr:[ \w.-/äöüßÄÖÜ(),']*").strip()
        hnRes = extractLineVal(answerStr, r"House_Number_corr:[ \w.-/]*").strip()
        roadRes = extractLineVal(answerStr, r"Road_corr:[ \w.-/äöüßÄÖÜ(),']*").strip()
        postcodeRes = extractLineVal(answerStr, r"Postcode_corr:[ \w.-/]*").strip()
        localityRes = extractLineVal(answerStr, r"Locality_corr:[ \w.-/äöüßÄÖÜ(),']*").strip()
        regionRes = extractLineVal(answerStr, r"Region_corr:[ \w.-/äöüßÄÖÜ(),']*").strip()
        countryRes = extractLineVal(answerStr, r"Country_corr:[ \w.-/äöüßÄÖÜ(),']*").strip()
        countryCodeRes = extractLineVal(answerStr, r"Country_Code_corr:[ \w.-/]*").strip()
        
        resDict = {'id': id, '_id': idRes, 'name': nameRes, 'house_number': hnRes, 'road': roadRes,
                   'postcode': postcodeRes, 'locality': localityRes, 'region': regionRes,
                   'country': countryRes, 'country_code': countryCodeRes,
                   'PromptId': prompt.promptId,
                   'Prompt': prompt.getPrompt(), 'Antwort': answerStr}

    elif prompt.promptId in _OTHER_DETECTION_IDS or prompt.promptId in _OTHER_CORRECTION_IDS:
        fields = _OTHER_PROMPT_FIELDS[prompt.promptId]
        parsed = _parse_labeled_fields(
            answerStr, fields, correction=(prompt.promptId in _OTHER_CORRECTION_IDS)
        )
        resDict = {'id': id, **parsed,
                   'PromptId': prompt.promptId,
                   'Prompt': prompt.getPrompt(), 'Antwort': answerStr}

    else:
        print(f'{prompt.promptId} does not exist')
    
    return resDict
