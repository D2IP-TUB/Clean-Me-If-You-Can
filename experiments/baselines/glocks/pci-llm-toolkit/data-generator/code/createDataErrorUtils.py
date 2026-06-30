from random import sample
import random
import numpy as np
import editdistance
import string
from enum import Enum
import pandas as pd
from datetime import date, timedelta
import math
from pathlib import Path
import os
import glob

from pydantic_settings import BaseSettings

class dataPollutor:
    def __init__(self,dataDir):
        # Read the CSV file into a DataFrame
        self.adr = pd.read_csv(f'{dataDir}ADRESSE.csv',sep=';')
        self.adr_gst = pd.read_csv(f'{dataDir}ADRESSE_GST.csv',sep=';')
        self.geb = pd.read_csv(f'{dataDir}GEBAEUDE.csv',sep=';')
        self.geb_fun = pd.read_csv(f'{dataDir}GEBAEUDE_FUNKTION.csv',sep=';')
        self.gem = pd.read_csv(f'{dataDir}GEMEINDE.csv',sep=';')
        self.ort = pd.read_csv(f'{dataDir}ORTSCHAFT.csv',sep=';')
        self.str_df = pd.read_csv(f'{dataDir}STRASSE.csv',sep=';')
        self.zahsp = pd.read_csv(f'{dataDir}ZAEHLSPRENGEL.csv',sep=';')
        self.allPossibleErrors = self.getNumOfPossibleErrors()

    def getSimilarDict(self,adr):
        plzLi = list(set(adr.loc[:,'PLZ']))
        plzDict = dict()
        for plz1 in plzLi:
            for plz2 in plzLi:
                editDis = editdistance.eval(str(plz1),str(plz2))
                if editDis < 2 and editDis > 0:
                    plzDict.setdefault(plz1,[]).append(plz2)
        return plzDict

    def getPlzErr(self,dat,plzNp,useNonRealPlz=False,plzDict=None):
        if plzDict is None:
            plzDict=self.getSimilarDict(plzNp)
        
        datLen = len(dat.plz)
        if useNonRealPlz:
            allNum = np.arange(1000,9999,1)
            allNonPlz = allNum[np.invert(np.isin(allNum,plzNp))]
            sampVal = sample(range(1,len(allNonPlz)),datLen)
            dat.loc[:,'plz'] = allNonPlz[sampVal]
        else:
            sampVal = sample(range(1,len(plzNp)),datLen)
            datOrig = dat.copy()
            dat.loc[:,'plz'] = plzNp[sampVal]
            compRes = dat.plz==datOrig.plz
            if any(compRes):
                idxVec = np.where(compRes)[0].tolist()
                for idx in idxVec:
                    idxLi = np.delete(np.arange(0,len(plzNp)),np.where(plzNp==dat.plz.iloc[0])[0].tolist()).tolist()
                    dat.at[dat.index[idx],'plz'] = plzNp[sample(idxLi,1)]
                #print(idx)

        return dat

    def getErrorIdx(self,dataLen, errPerc, dataDf=None):
        if dataDf is None:
            errIdx = sample(range(0,dataLen),max([round(dataLen*errPerc),1]))
        else: 
            if isinstance(dataDf,pd.Series):
                dataDf = dataDf[dataDf.loc['isDirty']==False]
            else:
                dataDf = dataDf.reset_index(drop=True)
                dataDf = dataDf[dataDf.loc[:,'isDirty']==False]
            if len(list(dataDf.index)) < max([round(dataLen*errPerc),1]):
                dataLen = len(dataDf)
            if dataDf.empty:
                errIdx = [0]
            else:
                errIdx = sample(list(dataDf.index),max([math.floor(dataLen*errPerc),1]))
        return errIdx

    def getNewChar(self,type,exSpCh=''):
        newChar = ''
        match type:
            case self.charType.letter.value:
                letters = string.ascii_letters
                newChar = letters[sample(range(0,len(letters)),1)[0]]
            case self.charType.number.value:
                newChar = str(sample(range(0,10),1)[0])
            case self.charType.special_character.value:
                specialChar = string.punctuation.replace(exSpCh,'')
                newChar = specialChar[sample(range(0,len(specialChar)),1)[0]]
        return newChar

    class charType(Enum):
        letter = 'str'
        number = 'num'
        special_character = 'spec'

    def getOtherCorrectValues(self,colName,oldVal):
        newVal = oldVal
        match colName:
            case 'straße':
                while oldVal == newVal:
                    newVal = self.str_df.iloc[sample(range(0,len(self.str_df)),1)[0]]['STRASSENNAME']
            case 'hnr':
                while oldVal == newVal:
                    newVal = sample(range(1,101),1)[0]
            case 'ort':
                while oldVal == newVal:
                    newVal = self.ort.iloc[sample(range(0,len(self.ort)),1)[0]]['ORTSNAME']
            case 'plz':
                while oldVal == newVal:
                    newVal = self.adr.iloc[sample(range(0,len(self.adr)),1)[0]]['PLZ']
            case 'gebDat':
                while oldVal == newVal:
                    current_date = date.today()
                    ranDay = random.randint(0,timedelta(days=365*14).days)
                    ranDay = random.randint(0,timedelta(days=365*500).days)
                    newVal = str(current_date+timedelta(days=365*120)-timedelta(days=ranDay))
            case _:
                newVal = ''
        return newVal

    def addInfoCol(self,pollDataDf,errDfIdx,errorName,errCol):
        pollDataDf.loc[pollDataDf.index[errDfIdx],'isDirty'] = True
        if pd.isna(pollDataDf.loc[pollDataDf.index[errDfIdx],'errCol']):
            pollDataDf.loc[pollDataDf.index[errDfIdx],'errCol']= errCol
        else:
            pollDataDf.loc[pollDataDf.index[errDfIdx],'errCol']= pollDataDf.loc[pollDataDf.index[errDfIdx],'errCol'] + ';'+errCol
        if pd.isna(pollDataDf.loc[pollDataDf.index[errDfIdx],'errRule']):
            pollDataDf.loc[pollDataDf.index[errDfIdx],'errRule'] = errorName
        else:
            pollDataDf.loc[pollDataDf.index[errDfIdx],'errRule'] = pollDataDf.loc[pollDataDf.index[errDfIdx],'errRule'] + ';'+errorName
        return pollDataDf

    def addOrReplaceCharError(self,pollDataDf,errCol,addRepCharType='str',exSpCh='',errPerc=0.5,errOccMax=5,isVerbose=False):
        possErrDict = {'str':['straße','plz','ort','land','pac','landVorwahl','vorwahl','telNr','gebDat'],
                       'num':['straße','plz','ort','land','pac','vorname','nachname','gebDat'],
                       'spec':['straße','hnr','stiege','tnr','plz','ort','land','pac',
                               'email','vorname','nachname','landVorwahl','vorwahl','telNr','gebDat']}
        isRanCol = False
        if errCol is None:
            isRanCol = True
        
        isRanCharType = False
        if addRepCharType is None:
            isRanCharType = True

        dataLen = len(pollDataDf)
        errDfIdxLi = self.getErrorIdx(dataLen, errPerc, pollDataDf)
        for errDfIdx in errDfIdxLi:
            if isRanCharType:
                if isRanCol:
                    addRepCharType = random.choice(list(possErrDict.keys()))
                    errCol = random.choice(possErrDict[addRepCharType.values])
                    while errCol == 'pac':
                        errCol = random.choice(possErrDict[addRepCharType.values])
                else:
                    addRepCharType = random.choice([key for key, values in possErrDict.items() if errCol in values])
            else:
                if isRanCol:
                    errCol=random.choice(possErrDict[addRepCharType])
                    while errCol == 'pac':
                        errCol=random.choice(possErrDict[addRepCharType])
                    
            
            colVal = pollDataDf.loc[:,errCol].iloc[errDfIdx]
            if pd.isna(colVal): #math.isnan(colVal):
                colVal = self.getNewChar(addRepCharType,exSpCh)
                idxHelper = list(pollDataDf.index)[errDfIdx]
                pollDataDf.loc[idxHelper,errCol] = colVal
                pollDataDf = self.addInfoCol(pollDataDf,errDfIdx,'Add_Or_Replace_Character',errCol)
                continue
            else:
                colVal = str(colVal)
                colLen = len(colVal)
            errNum = sample(range(1,(max(2,colLen+1) if colLen < errOccMax else errOccMax)),1)[0]
            errIdx = sample(range(0,colLen+1),errNum)
            for i in errIdx:
                newChar = self.getNewChar(addRepCharType,exSpCh)
                if sample(range(0,2),1)[0]==0:
                    if isVerbose:
                        print(f'\tappend: \'{newChar}\' after \'{colVal[:i]}\'')
                    colVal = colVal[:i] + newChar + colVal[i:]
                else:
                    if isVerbose:
                        print(f'\treplace: use \'{newChar}\' to replace \'{colVal}\'')
                    colVal = colVal[:i] + newChar + colVal[i + 1:]
            if isVerbose:
                print(colVal)
            idxHelper = list(pollDataDf.index)[errDfIdx]
            pollDataDf.loc[idxHelper,errCol] = colVal
            pollDataDf = self.addInfoCol(pollDataDf,errDfIdx,'Add_Or_Replace_Character',errCol)
        
        return pollDataDf

    def startWithLowercase(self,pollDataDf,errCol,errPerc=0.5,isVerbose=False):
        isRanCol = False
        if errCol is None:
            isRanCol = True
        dataLen = len(pollDataDf)
        errDfIdxLi = self.getErrorIdx(dataLen, errPerc, pollDataDf)
        for errDfIdx in errDfIdxLi:
            if isRanCol:
                errCol=random.choice(['straße','ort','land','vorname','nachname'])
            colVal = pollDataDf.loc[:,errCol].iloc[errDfIdx]
            if pd.isna(colVal):
                return pollDataDf
            pollDataDf.loc[pollDataDf.index[errDfIdx],errCol] = colVal[0].lower()+colVal[(0+1):]
            pollDataDf = self.addInfoCol(pollDataDf,errDfIdx,'Start_With_Lowercase',errCol)
        return pollDataDf

    def additionalInformation(self,pollDataDf,errCol,errPerc=0.5,isVerbose=False):
        isRanCol = False
        if errCol is None:
            isRanCol = True
        dataLen = len(pollDataDf)
        errDfIdxLi = self.getErrorIdx(dataLen, errPerc, pollDataDf)
        for errDfIdx in errDfIdxLi:
            if isRanCol:
                errCol=random.choice(['ort','plz'])
            cRow = pollDataDf.iloc[errDfIdx,:]
            colVal = pollDataDf.iloc[errDfIdx].loc[errCol]
            
            if 'plz' in cRow.loc['errCol'] or 'ort' in cRow.loc['errCol']:
                continue
            adrRows = self.adr.loc[self.adr['PLZ'].astype('str')==cRow.loc['plz']]
            gemRow = self.gem.loc[self.gem['GKZ'].isin(set(adrRows['GKZ']))]
            gemName = gemRow.loc[:,'GEMEINDENAME'].iloc[0]
            if not gemName == (cRow.loc['ort']) or errCol=='plz':
                colVal = str(colVal)+','+gemName
            else: 
                okzDf = adrRows.groupby('OKZ').count().iloc[:,:1]
                wei = list(adrRows.groupby('OKZ').count().iloc[:,1])
                okzOpt = random.choices(range(1,len(wei)+1),weights=wei)[0]
                okzVal = okzDf.index[(okzOpt-1)]
                ortName = self.ort.loc[self.ort['OKZ']==okzVal,'ORTSNAME'].values[0]
                colVal = ortName
            pollDataDf.loc[pollDataDf.index[errDfIdx],errCol] = colVal
            pollDataDf = self.addInfoCol(pollDataDf,errDfIdx,'additional_infromation',errCol)
        return pollDataDf

    def includeOtherCols(self,pollDataDf,errCol,errPerc=0.5,isVerbose=False):
        if errCol is None:
            errCol=random.choice(['ort','plz','straße','hnr','stiege','tnr','land'])

        dataLen = len(pollDataDf)
        errDfIdxLi = self.getErrorIdx(dataLen, errPerc, pollDataDf)
        colLi = list(pollDataDf.columns)
        colLi.remove('comb')
        colLi.remove('isDirty')
        colLi.remove('errCol')
        colLi.remove('errRule')
        colLi.remove(errCol)
        for errDfIdx in errDfIdxLi:
            colVal = pollDataDf.loc[:,errCol].iloc[errDfIdx]
            if pd.isna(colVal):
                colVal=''
            colVal = str(colVal) + ' ' + str(pollDataDf.loc[pollDataDf.index[errDfIdx],colLi[sample(range(0,len(colLi)),1)[0]]])
            pollDataDf.loc[pollDataDf.index[errDfIdx],errCol] = colVal[0].lower()+colVal[(0+1):]
            pollDataDf = self.addInfoCol(pollDataDf,errDfIdx,'Include_other_column',errCol)
        return pollDataDf

    def mismatch(self,pollDataDf,errCol,errPerc=0.5,isVerbose=False):
        isRanCol = False
        if errCol is None:
            isRanCol = True

        dataLen = len(pollDataDf)
        errDfIdxLi = self.getErrorIdx(dataLen, errPerc, pollDataDf)
        for errDfIdx in errDfIdxLi:
            if isRanCol:
                errCol=random.choice(['ort','plz','straße','land','gebDat'])
            colVal = pollDataDf.loc[:,errCol].iloc[errDfIdx]
            colVal = self.getOtherCorrectValues(errCol,colVal)
            pollDataDf.loc[pollDataDf.index[errDfIdx],errCol] = colVal
            pollDataDf = self.addInfoCol(pollDataDf,errDfIdx,'mismatch',errCol)
        return pollDataDf

    def getCloseValueByColumn(self,colName,oldVal):
        newVal = oldVal
        match colName:
            case 'straße':
                while oldVal == newVal:
                    newVal = self.getCloseValue(oldVal,list(set(self.str_df['STRASSENNAME'])))
            case 'ort':
                while oldVal == newVal:
                    newVal = self.getCloseValue(oldVal,list(set(self.ort['ORTSNAME'])))
            case 'plz':
                while oldVal == newVal:
                    newVal = self.getCloseValue(str(oldVal),list(set(self.adr['PLZ'])))
            case _:
                newVal = ''
        return newVal

    def getCloseValue(self,oldVal, possNewValLi):
        disLi = []
        i = 0
        for val in possNewValLi:
            val = str(val)
            if val != oldVal:
                disLi.append(editdistance.eval(str(val),oldVal))
            else:
                disLi.append(99999999)

        minVal = min(disLi)
        closeLiIdx = [i for i, value in enumerate(disLi) if value == minVal]
        sampIdx = sample(range(0,len(closeLiIdx)),1)[0]
        newVal = possNewValLi[closeLiIdx[sampIdx]]
        return newVal

    def similarButDifferent(self,pollDataDf,errCol,errPerc=0.5,isVerbose=False):
        isRanCol = False
        if errCol is None:
            isRanCol = True

        dataLen = len(pollDataDf)
        if isinstance(pollDataDf,pd.Series):
            if isRanCol:
                errCol=random.choice(['ort','plz','straße','land'])
            colVal = pollDataDf[errCol]
            pollDataDf[errCol] = self.getCloseValueByColumn(errCol,colVal)
            pollDataDf = self.addInfoCol(pollDataDf,errDfIdx,'Similar_Different',errCol)
        else:
            errDfIdxLi = self.getErrorIdx(dataLen, errPerc, pollDataDf)
            for errDfIdx in errDfIdxLi:
                if isRanCol:
                    errCol=random.choice(['ort','plz','straße','land'])
                colVal = pollDataDf.loc[pollDataDf.index[errDfIdx],errCol]
                pollDataDf.loc[pollDataDf.index[errDfIdx],errCol] = self.getCloseValueByColumn(errCol,colVal)
                pollDataDf = self.addInfoCol(pollDataDf,errDfIdx,'Similar_Different',errCol)
        return pollDataDf

    class ErrorType(Enum):
        addOrReplaceChar_str = 1.1
        addOrReplaceChar_num = 1.2
        addOrReplaceChar_spec = 1.3
        startWithLowercase = 2
        additionalInformation = 3
        mismatch = 4
        includeOtherCols = 5
        similarButDifferent = 6

    def getNumOfPossibleErrors(self):
        numOfErr = 0
        for errtype in self.ErrorType:
            numOfErr = numOfErr + len(self.getErrColByType(errtype)) 
        return numOfErr

    def getErrColByType(self,errType): 
        match errType:
            case self.ErrorType.addOrReplaceChar_str:                
                return ['straße','plz','ort','land','landVorwahl','vorwahl','telNr','gebDat'] 
            case self.ErrorType.addOrReplaceChar_num:
                return ['straße','plz','ort','land','vorname','nachname','gebDat'] 
            case self.ErrorType.addOrReplaceChar_spec:
                return ['straße','hnr','stiege','tnr','plz','ort','land','email','vorname','nachname','landVorwahl','vorwahl','telNr','gebDat'] 
            case self.ErrorType.startWithLowercase:
                return ['straße','ort','land','vorname','nachname']
            case self.ErrorType.additionalInformation:
                return ['ort','plz']
            case self.ErrorType.mismatch:
                return ['straße','plz','ort','land','gebDat']
            case self.ErrorType.includeOtherCols:
                return ['straße','hnr','stiege','tnr','plz','ort','land','email','vorname','nachname','landVorwahl','vorwahl','telNr','gebDat'] 
            case self.ErrorType.similarButDifferent:
                return ['straße','plz','ort','land']
            case _:
                return None
            
    def getErrorPercWhole(self,pollDataDf,errPerc,errPercDict=None,exSpCh=''):
        useErrDict = errPercDict is None
        dfLen = pollDataDf.shape[0]
        idxDirty = sample(range(0,dfLen),(int)(pollDataDf.shape[0]*errPerc))
        adDf_dirty = pollDataDf.loc[idxDirty]
        cleanDf = pollDataDf.loc[pollDataDf.index.difference(idxDirty)]

        if useErrDict:
            errPerc = 1/self.allPossibleErrors
            print(errPerc)
        else:
            print('TODO')
            return None
        j=0
        for errtype in self.ErrorType:
            colnameLi = self.getErrColByType(errtype)
            for colname in colnameLi:                
                match errtype:
                    case self.ErrorType.addOrReplaceChar_str:                
                        adDf_dirty = self.addOrReplaceCharError(adDf_dirty,colname,errPerc=errPerc,addRepCharType='str')
                    case self.ErrorType.addOrReplaceChar_num:
                        adDf_dirty = self.addOrReplaceCharError(adDf_dirty,colname,errPerc=errPerc,addRepCharType='num')
                    case self.ErrorType.addOrReplaceChar_spec:
                        adDf_dirty = self.addOrReplaceCharError(adDf_dirty,colname,errPerc=errPerc,
                                                                addRepCharType='spec',exSpCh=exSpCh)
                    case self.ErrorType.startWithLowercase:
                        adDf_dirty = self.startWithLowercase(adDf_dirty,colname,errPerc)
                    case self.ErrorType.additionalInformation:
                        adDf_dirty = self.additionalInformation(adDf_dirty,colname,errPerc)
                    case self.ErrorType.mismatch:
                        adDf_dirty = self.mismatch(adDf_dirty,colname,errPerc)
                    case self.ErrorType.includeOtherCols:
                        adDf_dirty = self.includeOtherCols(adDf_dirty,colname,errPerc)
                    case self.ErrorType.similarButDifferent:
                        adDf_dirty = self.similarButDifferent(adDf_dirty,colname,errPerc)
                j = j+1

        #-------------------------------------------------------------------------------------------------------------
        resAll = pd.concat([adDf_dirty,cleanDf])
        # Example output of np.unique
        unique_values, counts = np.unique(resAll.isDirty.values, return_counts=True)
        # Convert to dictionary for easy lookup
        count_dict = dict(zip(unique_values, counts))
        if count_dict[True] < len(adDf_dirty):
            colname = None
            errPerc = 1
            diffVal = len(adDf_dirty) - count_dict[True]
            errIdx = sample(range(0,len(resAll)),diffVal)
            for i in errIdx:
                row = pd.DataFrame(dict(resAll.iloc[i,:]),index=[i])
                errtype = random.choice(list(self.ErrorType))
                match errtype:
                    case self.ErrorType.addOrReplaceChar_str:                
                        row = self.addOrReplaceCharError(row,colname,errPerc=errPerc,addRepCharType='str')
                    case self.ErrorType.addOrReplaceChar_num:
                        row = self.addOrReplaceCharError(row,colname,errPerc=errPerc,addRepCharType='num')
                    case self.ErrorType.addOrReplaceChar_spec:
                        row = self.addOrReplaceCharError(row,colname,errPerc=errPerc,
                                                                addRepCharType='spec',exSpCh=exSpCh)
                    case self.ErrorType.startWithLowercase:
                        row = self.startWithLowercase(row,colname,errPerc)
                    case self.ErrorType.additionalInformation:
                        row = self.additionalInformation(row,colname,errPerc)
                    case self.ErrorType.mismatch:
                        row = self.mismatch(row,colname,errPerc)
                    case self.ErrorType.includeOtherCols:
                        row = self.includeOtherCols(row,colname,errPerc)
                    case self.ErrorType.similarButDifferent:
                        row = self.similarButDifferent(row,colname,errPerc)
                if not row.isDirty.values:
                    print(i)
                resAll.iloc[i,:] = row.iloc[0,:]
        #-------------------------------------------------------------------------------------------------------------

        return resAll

def run_pollutions(settings,adPersDf:pd.DataFrame=None):    
    directory = settings.dirOut
    pollPercLi = settings.pollPerc
    dataPath = Path(Path(directory)/f"_{settings.dataRows}{settings.dataDirAdd}")

    if adPersDf is None:
        pattern = 'trainGenData_adressPerson_[0-9]*.csv'
        filenames = glob.glob(directory + '/' + pattern)

        adPersDf = pd.read_csv(filenames[0])

    dpol = dataPollutor(settings.dataInDir)

    errPerc=0.1

    for pollPerc in pollPercLi:
        adDf_dirty = adPersDf.copy()
        adDf_dirty.loc[:,'isDirty'] = False
        adDf_dirty.loc[:,'errCol'] = ''
        adDf_dirty.loc[:,'errRule'] = ''
        errPerc = float(f"0.{pollPerc}")
        adDf_dirty = dpol.getErrorPercWhole(adDf_dirty,errPerc=errPerc)
        adDf_dirty.to_csv(dataPath/f"trainGenData_adressPerson_dirtyPol_whole_{pollPerc}.csv", index=False)
