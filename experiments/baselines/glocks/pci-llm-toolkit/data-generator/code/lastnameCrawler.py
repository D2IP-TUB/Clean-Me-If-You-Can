from lxml import etree
import requests
from string import ascii_lowercase
import pandas as pd

nameLi = list()
idx = 1
for c in ascii_lowercase:
    print('-----------------------------------------------------')
    print(c)
    nname_url = f"https://nachnamen.net/osterreich/{c}"

    response = requests.get(nname_url)

    if response.status_code == 200:
        dom = etree.HTML(response.text)
        elements = dom.xpath("//div[@class='desplegable-menu col3']")
        if len(elements)==0:
            continue
        elements = elements[1]
        for i in range(0,len(elements)-1):
            #print('----')
            #print(elements[i].text)
            nname_url = f"https://nachnamen.net/osterreich/{elements[i].text}"
            
            response1 = requests.get(nname_url)
            dom1 = etree.HTML(response.text)
            elements1 = dom1.xpath("//li[@class='list-item col-lg-4 col-xs-6 mb-2 vl']")

            for j in range(0,len(elements1)-1):
                #print('----')
                name = elements1[j][0].text
                count = elements1[j][0].tail.replace(' ','').replace('(','').replace(')','')
                #print(name,count)
                nameLi.append(dict({'idx':idx, 'lastname':name,'count':count}))

    else:
        print("Failed to fetch the webpage.")

namesDf=pd.DataFrame(nameLi)
namesDf.to_csv('data/in/lastnamesAut.csv')