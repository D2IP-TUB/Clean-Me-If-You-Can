
import re
import pandas as pd

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
                    display_field = "Id"
                elif field == "house_number":
                    display_field = "House Number"
                elif field == "country_code":
                    display_field = "Country Code"
                else:
                    # Capitalize first letter
                    display_field = field.capitalize()
                
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

    # elif prompt.promptId in ['p1','p2','p3','p7','p8','p9','p10','p11','p12','p13','p15','p16','p18']:
    #     strRes = extractLineVal(answerStr,r"Stra[sß]e:[ \w.-/]*").strip().lower()
    #     hnRes = extractLineVal(answerStr,r"Hausnummer:[ \w.-/]*").strip().lower()
    #     stRes = extractLineVal(answerStr,r"Stiege:[ \w.-/]*").strip().lower()
    #     tnRes = extractLineVal(answerStr,r"Türnummer:[ \w.-/]*").strip().lower()
    #     plzRes = extractLineVal(answerStr,r"Postleitzahl:[ \w.-/]*").strip().lower()
    #     ortRes = extractLineVal(answerStr,r"Ort:[ \w.-/]*").strip().lower()
    #     resDict = {'id':id,'Strasse':strRes,'Hausnummer':hnRes,'Stiege':stRes,
    #                'Türnummer':tnRes,'Postleitzahl':plzRes,'Ort':ortRes,
    #                'PromptId':prompt.promptId,
    #                'Prompt':prompt.getPrompt(),'Antwort':answerStr}
        
    # elif prompt.promptId in ['p1']:                
    #     nnRes = extractLineVal(answerStr,r"Nachname:[ \w.-/]*").strip().lower()
    #     vnRes = extractLineVal(answerStr,r"Vorname:[ \w.-/]*").strip().lower()
    #     gebDatRes = extractLineVal(answerStr,r"Geburtsdatum:[ \w.-/]*").strip().lower()
    #     emailRes = extractLineVal(answerStr,r"Email:[ \w.-/]*").strip().lower()
    #     lvorRes = extractLineVal(answerStr,r"Laendervorwahl:[ \w.-/]*").strip().lower()
    #     vorRes = extractLineVal(answerStr,r"Vorwahl:[ \w.-/]*").strip().lower()
    #     telnrRes = extractLineVal(answerStr,r"Telefonnummer:[ \w.-/]*").strip().lower()

    #     strRes = extractLineVal(answerStr,r"Stra[sß]e:[ \w.-/]*").strip().lower()
    #     hnRes = extractLineVal(answerStr,r"Hausnummer:[ \w.-/]*").strip().lower()
    #     stRes = extractLineVal(answerStr,r"Stiege:[ \w.-/]*").strip().lower()
    #     tnRes = extractLineVal(answerStr,r"Türnummer:[ \w.-/]*").strip().lower()
    #     plzRes = extractLineVal(answerStr,r"Postleitzahl:[ \w.-/]*").strip().lower()
    #     ortRes = extractLineVal(answerStr,r"Ort:[ \w.-/]*").strip().lower()
    #     landRes = extractLineVal(answerStr,r"Land:[ \w.-/]*").strip().lower()

    #     resDict = {'id':id,
    #                'Nachname':nnRes, 'Vorname':vnRes,'Geburtsdatum':gebDatRes,
    #                'Email':emailRes,'Laendervorwahl':lvorRes,
    #                'Vorwahl':vorRes,'Telefonnummer':telnrRes,
    #                'Strasse':strRes,'Hausnummer':hnRes,'Stiege':stRes,
    #                'Türnummer':tnRes,'Postleitzahl':plzRes,'Ort':ortRes,
    #                'Land':landRes,
    #                'PromptId':prompt.promptId,
    #                'Prompt':prompt.getPrompt(),'Antwort':answerStr}

    # elif prompt.promptId in ['p5']:
    #     'blub'
    else:
        print(f'{prompt.promptId} does not exist')
    
    return resDict
