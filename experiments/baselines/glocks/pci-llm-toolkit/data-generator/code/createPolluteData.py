import pandas as pd
from random import sample
import math
import numpy as np

from createDataErrorUtils import dataPollutor, run_pollutions

from faker import Faker
from pathlib import Path
import os
from pydantic_settings import BaseSettings

def getFirstName(nVal=1, dataDir='../data/in/'):
    fnDf_boy = pd.read_csv(Path(dataDir)/'boynames_1984_2023.csv')
    fnDf_girl = pd.read_csv(Path(dataDir)/'girlnames_1984_2023.csv')
    fnDf_boy['name'] = fnDf_boy.iloc[:,0]
    fnDf_boy_fil = pd.DataFrame(fnDf_boy[fnDf_boy['name'].str.contains(r'\?', na=False) == False])
    fnDf_boy_fil['probVal'] = fnDf_boy_fil['Anzahl ... 1984-2023']/sum(fnDf_boy_fil['Anzahl ... 1984-2023'])

    fnDf_girl['name'] = fnDf_girl.iloc[:,0]
    fnDf_girl_fil = pd.DataFrame(fnDf_girl[fnDf_girl['name'].str.contains(r'\?', na=False) == False])
    fnDf_girl_fil['probVal'] = fnDf_girl_fil['Anzahl ... 1984-2023']/sum(fnDf_girl_fil['Anzahl ... 1984-2023'])

    if np.random.choice([1,2])==1:
        fnVec = np.random.choice(fnDf_boy_fil['name'], size=nVal, replace=True, p=fnDf_boy_fil['probVal'])
    else:
        fnVec = np.random.choice(fnDf_girl_fil['name'], size=nVal, replace=True, p=fnDf_girl_fil['probVal'])
    fnStr = [str(fnStr).title() for fnStr in fnVec]
    return fnStr

def getLastName(nVal=1, dataDir='../data/in/'):
    lnDf = pd.read_csv(Path(dataDir)/'lastnamesAut.csv')
    lnDf_fil = pd.DataFrame(lnDf[lnDf['lastname'].str.contains(r'\?', na=False) == False])
    lnDf_fil['probVal'] = lnDf_fil['count']/sum(lnDf_fil['count'])
    samVecLN = np.random.choice(lnDf_fil['lastname'], size=nVal, replace=True, p=lnDf_fil['probVal'])
    lnStr = [str(lnStr).title() for lnStr in samVecLN]
    return lnStr

def getEmail(nVal=1, dataDir='../data/in/'):
    emailDf = pd.read_csv(Path(dataDir)/'addresses-email-W3C.txt',sep=' ',header=None)
    emailDf_fil = pd.DataFrame(emailDf[emailDf.iloc[:,1].str.contains(r'@[0-9]*\\.[0-9]+', na=False) == False])
    emailDf_fil = pd.DataFrame(emailDf_fil[emailDf_fil.iloc[:,1].str.contains(r'"@', na=False) == False])
    sampMail = np.random.choice(emailDf_fil.iloc[:,1],size=nVal)
    return sampMail

def getLandVorwahl():
    return 43

def getVorwahlAut(nVal=1):
    allVorwahlAut = ['501', '502', '503', '504', '505', '506', '507', '508', '509', '517', '057', '059' , '650', '651', 
                     '652', '653', '655', '657', '659', '660', '661', '663','664','665','666','667','668','669','670',
                     '671','672','673','674','675','676','677','678','679','680','681','682','683','684','685','686',
                    '687','688','689','690','691','692','693','694','695','696','697','698','699', '718', '720', '780', 
                    '800', '810', '820', '821', '804', '828', '900', '901', '930', '931', '939', '1', '10', '111', 
                    '118', '130', '120', '123', '1484', '1455', '1450']
    sampVorwahl = np.random.choice(allVorwahlAut,size=nVal)
    return sampVorwahl

def getTeleNum(nVal=1):
    sampTele = [''.join(str(x) for x in np.random.choice(range(0,9),size=np.random.choice(range(3,7)))) for i in range(0,nVal)]
    return sampTele

def getLand():
    return 'AUT'

def getGebDatum(nVal=1, dataDir='data/in/'):
    fake = Faker()
    altersVerDf = pd.read_csv(Path(dataDir)/'ageDistribution.csv',sep=';')
    altersVerDf = altersVerDf.iloc[1:,]
    altersVerDf['altNum'] = [int(alt.split(' ')[0]) for alt in altersVerDf['Alter']]
    altersVerDf_fil = pd.DataFrame(altersVerDf[altersVerDf['altNum']>=18])
    allVollPersAlter = sum(altersVerDf_fil['2024'])
    altersVerDf_fil['percVal'] = altersVerDf_fil['2024']/allVollPersAlter
    sampGeb = [str(fake.date_between(start_date=''.join(['-',str(np.random.choice(altersVerDf_fil['altNum'],
                                                                                  p=altersVerDf_fil['percVal'])),'y']), 
                                                                                  end_date='now')) for i in range(0,nVal)]
    return sampGeb

def getPersonData(nVal=1, dataDir=None):
    if dataDir is None:
        result = pd.DataFrame({
            'email': getEmail(nVal),
            'vorname': getFirstName(nVal),
            'nachname': getLastName(nVal),
            'landVorwahl': getLandVorwahl(),
            'vorwahl': getVorwahlAut(nVal),
            'telNr': getTeleNum(nVal),
            'land': getLand(),
            'gebDat': getGebDatum(nVal),
        })
    else:
        result = pd.DataFrame({
            'email': getEmail(nVal,dataDir=dataDir),
            'vorname': getFirstName(nVal,dataDir=dataDir),
            'nachname': getLastName(nVal,dataDir=dataDir),
            'landVorwahl': getLandVorwahl(),
            'vorwahl': getVorwahlAut(nVal),
            'telNr': getTeleNum(nVal),
            'land': getLand(),
            'gebDat': getGebDatum(nVal,dataDir=dataDir),
        })
    return result


def hnrSup(s):    
    if pd.isna(s):
        return ''
    if isinstance(s,float):
        s = str(int(s))
    if len(s) == 0:
        return ''
    elif s == ' ':
        return ''
    else:
        return s

def combHnr(hnrZahl, hnrBuch, hnrVerb):
    hnrStrVal = ''
    
    # Initialisiere ein DataFrame
    cDf = pd.DataFrame({
        'zahl': [None],
        'buch': [None],
        'verb': [None],
        'keepVerb': [False],
        'hnr': [False],
        'stg': [False],
        'tnr': [False],
        'str': ['']
    })
    
    # Überprüfen, ob hnrZahl nicht NaN ist
    if hnrZahl is not None and not math.isnan(hnrZahl):
        hnrStrVal += str(hnrZahl.astype(int))
        cDf.at[0, 'zahl'] = hnrZahl.astype(int)
    
    # Überprüfen, ob hnrBuch nicht leer ist
    if not pd.isna(hnrBuch):
        hnrStrVal += hnrBuch
        cDf.at[0, 'buch'] = hnrBuch
    
    # Überprüfen, ob hnrVerb nicht leer ist
    if not pd.isna(hnrVerb):
        if hnrVerb in ['Stg.', 'Block']:
            cDf.at[0, 'stg'] = True
        if hnrVerb in ['Haus', 'Obj.']:
            cDf.at[0, 'tnr'] = True
        if hnrVerb in ['-']:
            cDf.at[0, 'hnr'] = True
            cDf.at[0, 'keepVerb'] = True
        hnrStrVal += hnrVerb
        cDf.at[0, 'verb'] = str(hnrVerb)
    
    # Füge den kombinierten String hinzu
    cDf.at[0, 'str'] = hnrStrVal
    
    return cDf

def getHnr(cAdr,cGeb):
    if pd.isna(cAdr['HAUSNRZAHL1']).iloc[0]:
        return {'hnr': '', 'stg': '', 'tnr': ''}

    if not pd.isna(cGeb.get('HAUSNRZAHL3', None)):
        nhr1 = combHnr(cAdr['HAUSNRZAHL1'].iloc[0], cAdr['HAUSNRBUCHSTABE1'].iloc[0], cAdr['HAUSNRVERBINDUNG1'].iloc[0])
        nhr2 = combHnr(cAdr['HAUSNRZAHL2'].iloc[0], cAdr['HAUSNRBUCHSTABE2'].iloc[0], cGeb['HAUSNRVERBINDUNG2'])
        nhr3 = combHnr(cGeb['HAUSNRZAHL3'], cGeb['HAUSNRBUCHSTABE3'], cGeb['HAUSNRVERBINDUNG3'])
        nhr4 = combHnr(cGeb['HAUSNRZAHL4'], cGeb['HAUSNRBUCHSTABE4'], '')
    else:
        nhr1 = combHnr(cAdr['HAUSNRZAHL1'].iloc[0], cAdr['HAUSNRBUCHSTABE1'].iloc[0], cAdr['HAUSNRVERBINDUNG1'].iloc[0])
        nhr2 = combHnr(cAdr['HAUSNRZAHL2'].iloc[0], cAdr['HAUSNRBUCHSTABE2'].iloc[0], '')
        nhr3 = pd.DataFrame()
        nhr4 = pd.DataFrame()

    cDf = pd.concat([nhr1, nhr2, nhr3, nhr4], ignore_index=True)

    # Spezielle Fälle für verb '/'
    if (cDf['verb'] == '/').sum() == 2:
        specIdx = cDf[cDf['verb'] == '/'].index
        cDf.loc[specIdx[0], 'stg'] = True
        cDf.loc[specIdx[1], 'tnr'] = True
    elif (cDf['verb'] == '/').sum() == 1:
        specIdx = cDf[cDf['verb'] == '/'].index[0]
        cDf.loc[specIdx, 'tnr'] = True

    # hnr
    hnrIdx = cDf[cDf['hnr']].index
    if not hnrIdx.empty:
        hnr = cDf.loc[hnrIdx[0] + 1, ['zahl', 'buch']].dropna()
        hnrStr = ''.join(hnr.astype(str))
        hnrOld = ''.join(cDf.loc[0, ['zahl', 'buch']].dropna().astype(str))
        hnr = f"{hnrOld}{cDf.loc[hnrIdx[0], 'verb']}{hnrStr}"
    else:
        hnr = ''.join(cDf.loc[0, ['zahl', 'buch']].dropna().astype(str))

    # stg
    stgIdx = cDf[cDf['stg']].index
    stg = ''.join(cDf.loc[stgIdx[0] + 1, ['zahl', 'buch']].dropna().astype(str)) if not stgIdx.empty else None

    # tnr
    tnrIdx = cDf[cDf['tnr']].index
    tnr = ''.join(cDf.loc[tnrIdx[0] + 1, ['zahl', 'buch']].dropna().astype(str)) if not tnrIdx.empty else None

    return {'hnr': hnr, 'stg': stg, 'tnr': tnr}

def getAdr(adrcdId, adr, str_df, geb, ort):
    cAdr = adr[adr['ADRCD'] == adrcdId]
    if cAdr.empty:
        return None
    
    strVal = str_df[str_df['SKZ'] == cAdr.iloc[0]['SKZ']]
    hNrVal = geb[geb['ADRCD'] == cAdr.iloc[0]['ADRCD']]
    
    hNrP1 = (
        (hnrSup(cAdr.iloc[0]['HAUSNRTEXT']) + ' ').strip() +
        hnrSup(cAdr.iloc[0]['HAUSNRZAHL1']) +
        hnrSup(cAdr.iloc[0]['HAUSNRBUCHSTABE1']) +
        hnrSup(cAdr.iloc[0]['HAUSNRVERBINDUNG1']) +
        hnrSup(cAdr.iloc[0]['HAUSNRZAHL2']) +
        hnrSup(cAdr.iloc[0]['HAUSNRBUCHSTABE2'])
    )
    
    if hNrVal.empty and len(hNrP1) == 1:
        return None
    
    if len(hNrVal) > 1:
        return None
    
    hNr = (
        (hnrSup(cAdr.iloc[0]['HAUSNRTEXT']) + ' ').strip() +
        hnrSup(cAdr.iloc[0]['HAUSNRZAHL1']) +
        hnrSup(cAdr.iloc[0]['HAUSNRBUCHSTABE1']) +
        hnrSup(cAdr.iloc[0]['HAUSNRVERBINDUNG1']) +
        hnrSup(cAdr.iloc[0]['HAUSNRZAHL2']) +
        hnrSup(cAdr.iloc[0]['HAUSNRBUCHSTABE2']) +
        hnrSup(hNrVal.iloc[0]['HAUSNRVERBINDUNG2']) +
        hnrSup(hNrVal.iloc[0]['HAUSNRZAHL3']) +
        hnrSup(hNrVal.iloc[0]['HAUSNRBUCHSTABE3']) +
        hnrSup(hNrVal.iloc[0]['HAUSNRVERBINDUNG3']) +
        hnrSup(hNrVal.iloc[0]['HAUSNRZAHL4']) +
        hnrSup(hNrVal.iloc[0]['HAUSNRBUCHSTABE4']) +
        (' ' + hnrSup(hNrVal.iloc[0]['HAUSNRGEBAEUDEBEZ']))
    ).strip()
    
    hnrDict = getHnr(cAdr,geb[geb['ADRCD'] == cAdr.iloc[0]['ADRCD']].iloc[0] if not geb[geb['ADRCD'] == cAdr.iloc[0]['ADRCD']].empty else pd.Series())
    ortVal = ort[(ort['OKZ'] == cAdr.iloc[0]['OKZ']) & (ort['GKZ'] == cAdr.iloc[0]['GKZ'])]
    plzVal = cAdr.iloc[0]['PLZ']
    
    result = pd.DataFrame({
        'straße': [strVal.iloc[0]['STRASSENNAME']],
        'hnr': hnrDict['hnr'],
        'stiege': hnrDict['stg'],
        'tnr': hnrDict['tnr'],
        'ort': [ortVal.iloc[0]['ORTSNAME'] if not ortVal.empty else None],
        'plz': [plzVal],
        'comb': [
            (strVal.iloc[0]['STRASSENNAME'].strip() + ' ' + hNr).strip() + ' ' +
            (str(plzVal).strip() + ' ' + ortVal.iloc[0]['ORTSNAME'].strip()).strip() if not ortVal.empty else None
        ]
    })
    
    return result

class Settings(BaseSettings):
    """Settings for the application."""

    dirOut: str = "data/out/DataRows5000"
    pollPerc: list = ["025","05","15","20","25","30","40","75"]
    dataInDir: str = 'data/in/'
    dataRows: int = 500 # max: 2284637
    dataDirAdd: str = ""


    class Config:
        """Configuration for the [`Settings`][semdq.config.Settings] class.

        This class is required by pydantic to set up the `.env` file and encoding.
        """
        env_file = ".env"
        env_file_encoding = "utf-8"
        env_nested_delimiter = "__"



settings = Settings()
directory = settings.dirOut
pollPercLi = settings.pollPerc
dataDir = settings.dataInDir
print(f'{dataDir}')
print('---------------------------------------------------------')
print('')

# Read the CSV file into a DataFrame
adr = pd.read_csv(f'{dataDir}ADRESSE.csv',sep=';')
adr_gst = pd.read_csv(f'{dataDir}ADRESSE_GST.csv',sep=';')
geb = pd.read_csv(f'{dataDir}GEBAEUDE.csv',sep=';')
geb_fun = pd.read_csv(f'{dataDir}GEBAEUDE_FUNKTION.csv',sep=';')
gem = pd.read_csv(f'{dataDir}GEMEINDE.csv',sep=';')
ort = pd.read_csv(f'{dataDir}ORTSCHAFT.csv',sep=';')
str_df = pd.read_csv(f'{dataDir}STRASSE.csv',sep=';')
zahsp = pd.read_csv(f'{dataDir}ZAEHLSPRENGEL.csv',sep=';')

isIntroduceError = True
errorRateDict = {
    'plz': 0.1
}
borEnd = settings.dataRows
adLi = []
i = 1
adrcdLi = sample(list(geb['ADRCD'].unique()),round(borEnd+borEnd*0.1))

for adrcdId in adrcdLi:
    tmpAd = getAdr(adrcdId, adr, str_df, geb, ort)
    if tmpAd is None:
        continue
    adLi.append(tmpAd)
    
    if (i % 100) == 0:
        print(i)
    
    i += 1
    if i == borEnd+1:
        break

persDf = getPersonData(len(adLi),dataDir=dataDir)

# Concatenate all DataFrames in the list
adDf = pd.concat(adLi, ignore_index=True)
adPersDf = pd.concat([persDf, adDf], axis=1)

saveDir = Path(Path(directory)/f"_{borEnd}{settings.dataDirAdd}")
if not os.path.exists(saveDir):
    os.makedirs(saveDir)
# Write the result to a CSV file
adPersDf.loc[:,'pk']=range(0,len(adPersDf))
adPersDf.to_csv(saveDir/f'trainGenData_adressPerson_{len(adPersDf)}.csv', index=False)

run_pollutions(settings,adPersDf.astype('str'))
