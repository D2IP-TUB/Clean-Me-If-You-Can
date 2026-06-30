# Data Generator and Polluter
A Python tool for the generation and pollution of synthetic personal contact information of an Austrian citizen.

## Data preparation
We use data from multiple sources and save the data into [data/in/](data/in):<br>
* Data from [Statistics Austria](www.statistik.at)
Statistics Austria is responsible for the collection, compilation, analysis, and publication of official statistics for Austria. We downloaded the information on first names and age distribution from Statistics Austria. 
    * We obtained the first name from the file [fistname.ods](https://www.statistik.at/fileadmin/pages/426/Vornamen_1984_bis_2023_original_Schreibweise.ods). We manually extracted the 12th sheet into 'boynames_1984_2023.csv' and the 13th sheet into 'girlnames_1984_2023.csv'. 
    * To obtain the age distribution for the Austrian population, we extracted the columns ('Männer und Frauen' and '01.01.2024') from sheet 'Ö' [austrian_age_distribution.ods](https://www.statistik.at/fileadmin/pages/406/Bev_nach_Alter_Geschlecht_Staatsangeh_Bundesl_Zeitreihe.ods) into 'ageDistribution.csv'.

* We found a list of Austrian last names on [nachnamen.net](https://nachnamen.net/osterreich/). As this website does not provide a download, we crawled the names. To run the crawler:
    > python .\code\lastnameCrawler.py

* The Emailaddresses we download from [tides.umiacs.umd.edu](https://tides.umiacs.umd.edu/webtrec/trecent/parsed_w3c_corpus.html) and use the 'addresses-email-W3C.txt' file. 

* We found Austrian addresses on the official Austrian address register. We used the files from the [address_table.zip](https://data.bev.gv.at/download/Adressregister/Archiv_Adressregister/Adresse_Relationale_Tabellen_Stichtagsdaten_20241001.zip). Extract the files from the zip file to the [data/in](data/in/) folder.

<br>

After downloading the files your data/in directory should contain the following files:
* addresses-email-W3C.txt ... email addresses
* lastnamesAut.csv ... last names
* ageDistribution.csv ... age distribution
* boynames_1984_2023.csv ... male first names
* girlnames_1984_2023.csv ... femail first names
* Austrian addresses: 
    * ADRESSE_GST.csv
    * ADRESSE.csv
    * GEBAEUDE_FUNKTION.csv
    * GEBAEUDE.csv
    * GEMEINDE.csv
    * ORTSCHAFT.csv
    * STRASSE.csv
    * ZAEHLSPRENGEL.csv

## .env
The variables can be set using a .env file:
* dataInDir ... path to the directory where the input files (address files, first names, ...) can be found.
* dirOut ... path where the generated and polluted data are written to. A subdirectory is created with the name '_<dataRows>'. The clean data set is named 'trainGenData_adressPerson_<dataRows>.csv' and the polluted ones are named like this: 'trainGenData_adressPerson_dirtyPol_whole_<pollution_grade>.csv'.
* dataDirAdd ... any additional name the output dir should have, it will always start with '_<dataRows>'.
* dataRows ... specifies the number of rows to generate.
* pollPerc ... specifies how many errors will be introduced to the clean dataset. '30' means 30% of the rows will be polluted at the end, some might be polluted with more than one error. '025' would mean 2.5% of rows are affected.  

Default values:
> dataInDir = '/data/in/'  \
> dirOut = "/data/out/DataRows5000" \
> dataDirAdd = "" \
> pollPerc = ["025","05","15","20","25","30","40","75"] \
> dataRows = 5000  

## CMD
Run via command line:
> pip install -r requirements.txt \
> cd code \
> python createPolluteData.py

## Docker
We provide a Dockerfile to run the code:

Build the container:
> docker build -t gen-data .

Run the container:<br>
The two volumns provide the data and the code.
> docker run --name gen-data --gpus all -v ./data:/data -v ./code:/code -it gen-data


