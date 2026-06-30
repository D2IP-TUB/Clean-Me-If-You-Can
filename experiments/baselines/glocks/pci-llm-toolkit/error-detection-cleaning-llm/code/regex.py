import re


s = "Name_corr: Bänzstraßeé (ciao)"

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

print(extractLineVal(s, r"Name_corr:[ \w.-/]*").strip())
print(extractLineVal(s, r"Name_corr:[ \w.-/äöüßÄÖÜ()]*").strip())



