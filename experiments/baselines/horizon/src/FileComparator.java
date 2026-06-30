

import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.FileNotFoundException;
import java.io.FileReader;
import java.io.FileWriter;
import java.io.IOException;
import java.io.PrintWriter;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Random;

public class FileComparator {

	/**
	 * Parse a CSV line respecting quoted fields (RFC 4180).
	 * Commas inside double-quoted fields do not split; "" is an escaped quote.
	 * Falls back to simple split if no quotes present.
	 */
	private static String[] parseCsvLine(String line) {
		if (line == null) return new String[0];
		List<String> fields = new ArrayList<>();
		StringBuilder sb = new StringBuilder();
		boolean inQuotes = false;
		for (int i = 0; i < line.length(); i++) {
			char c = line.charAt(i);
			if (c == '"') {
				if (inQuotes && i + 1 < line.length() && line.charAt(i + 1) == '"') {
					sb.append('"');
					i++;
				} else {
					inQuotes = !inQuotes;
				}
			} else if (c == ',' && !inQuotes) {
				fields.add(sb.toString());
				sb.setLength(0);
			} else {
				sb.append(c);
			}
		}
		fields.add(sb.toString());
		return fields.toArray(new String[0]);
	}

	String dirty;
	String cleaned;
	String ground;
	
	int numOfTuples;
	int totalCells;
	int numOfFVs;
	
	int numOfDirtyCells;			//This is actually the denominator of recall
	
	int numOfChangedCells;			//cleaned vs dirty, this is actually the denominator of precision
	
	double numerator;					//This is the numerator for precision, and recall.
									//This is also the so-called cost function in the paper
									//ignore this metric for now
	
	int numOfCorrectedChangedCells;	
	int numOfPartiallyCorrectedChangedCells;
	
	
	double precision;
	double recall;
	int distance;	//this is the distance for integer values
	int distance2;	//this is the distance for string values, i.e. edit distance
	
	
	/**
	 * @param runCompare if false, comparison is not run in constructor (call Compare() or CompareAndGenerateCells() yourself)
	 */
	public FileComparator(String dirtyFile, String cleanedFile, String groundFile, boolean runCompare)
	{
		this.dirty = dirtyFile;
		this.cleaned = cleanedFile;
		this.ground = groundFile;
		
		numOfTuples = 0;
		totalCells = 0;
		numOfFVs = 0;
		numOfDirtyCells = 0;
		numOfChangedCells = 0;
		numOfCorrectedChangedCells = 0;
		numOfPartiallyCorrectedChangedCells = 0;
		numerator = 0;
		precision = 0;
		recall = 0;
		distance = 0;
		distance2 = 0;
		
		System.out.println("Cleaned file: "+cleanedFile);
		System.out.println("dirty file: "+dirtyFile);
		if (runCompare)
			Compare();
	}

	public FileComparator(String dirtyFile, String cleanedFile, String groundFile)
	{
		this(dirtyFile, cleanedFile, groundFile, true);
	}
	
	
	int numFVInteger = 0;
	int numFVString = 0;
	
	int disIntegerMax = 0;
	int disStringMax = 0;
	

	public void CompareAndGenerateCells()
	{
		// Reset counters so this run is independent (avoids double-counting if constructor already ran Compare())
		numOfTuples = 0;
		totalCells = 0;
		numOfFVs = 0;
		numOfDirtyCells = 0;
		numOfChangedCells = 0;
		numOfCorrectedChangedCells = 0;
		numOfPartiallyCorrectedChangedCells = 0;
		numerator = 0;
		precision = 0;
		recall = 0;
		distance = 0;
		distance2 = 0;

		Random randomNum = new Random();
		int result;
		int n_cells = 0;
		
		try {
			BufferedReader br1 = new BufferedReader(new FileReader(dirty));
			BufferedReader br2 = new BufferedReader(new FileReader(cleaned));
			BufferedReader br3 = new BufferedReader(new FileReader(ground));
			
			FileWriter fstream = new FileWriter("wrong_changes_cells.txt", false);
			BufferedWriter br4 = new BufferedWriter(fstream);	

			FileWriter fstream2 = new FileWriter("sample_cells_100.txt", false);
			BufferedWriter br5 = new BufferedWriter(fstream2);	
			
			String line1, line2, line3;
			boolean colHead = true;
			//String[] colTypes = null;
			while ((line1 = br1.readLine()) != null) {
				line2 = br2.readLine();
				line3 = br3.readLine();
				if (colHead) {
					colHead = false;// the first row is column head information, skip
					String[] cols = line1.split(",");
					// colTypes = new String[cols.length];
					for (int i = 0; i < cols.length; i++) {
						String col = cols[i];
						// colTypes[i] = col.substring(col.indexOf("(") + 1, col.length() - 1);
					}
					continue;
				}
				assert (line2 != null);
				assert (line3 != null);
				String[] col1 = parseCsvLine(line1);
				String[] col2 = parseCsvLine(line2);
				String[] col3 = parseCsvLine(line3);
				int nCols = Math.min(col1.length, Math.min(col2.length, col3.length));
				if (col1.length != col2.length || col1.length != col3.length) {
					System.err.println("Warning: row " + (numOfTuples + 1) + " column count mismatch (dirty=" + col1.length + ", cleaned=" + col2.length + ", ground=" + col3.length + "), comparing first " + nCols + " columns only.");
				}
				numOfTuples++;
				for (int i = 0; i < nCols; i++) {
					String cell1 = col1[i].trim();
					String cell2 = col2[i].trim();
					String cell3 = col3[i].trim();
					totalCells++;

					// System.out.println(cell1);
					// System.out.println(cell2);
					// System.out.println(cell3);

					if (cell3.equals("NULL")) {
						cell3 = "";
					}

					if (!cell1.equals(cell3)) {
						// System.out.println(cell1+" vs. "+cell3);
						numOfDirtyCells++;
					}

					if (!cell2.equals(cell1)) {
						
						//System.out.println(cell1 + " "+ cell2);

						numOfChangedCells++;

						if (cell2.equals(cell3) && !cell1.equals(cell3)) {
							numOfCorrectedChangedCells++;
							numerator += 1.0;
						} else {
							br4.write("Tuple: " + line1 + "\n");
							br4.write("Dirty: " + cell1 + " Cleaned: " + cell2 + " Ground: " + cell3 + "\n");
						}

						// flip a coin to select cell
						if (n_cells < 100) {
							result = randomNum.nextInt(2);

							if (result == 0) {
								System.out.println(n_cells + ": "+cell1 + " -> " + cell2);
								cell1 = cell2;
								
								
								
								n_cells++;
								
							}
						}

					}
					
						// write line to sample cells file
						if (i == nCols - 1)
							br5.write(cell1);
						else
							br5.write(cell1 + ",");
					

					
				
			}
				
				br5.write("\n");
				
				
				
			}
			
			br4.close();
			br5.close();
		
		} catch (FileNotFoundException e) {
			// TODO Auto-generated catch block
			e.printStackTrace();
		}
		catch (IOException e) {
			
			e.printStackTrace();
		}
		
		distance += disIntegerMax * numFVInteger;
		
		//double ave2 = (double)distance2/ (totalCells - numOfFVs);
		distance2 += disStringMax * numFVString;
		
		precision = numerator / numOfChangedCells;
		recall = numerator / numOfDirtyCells;
		
		printStatToConsole(0);
		
	}	
	
	
	
	public void Compare()
	{
		try {
			BufferedReader br1 = new BufferedReader(new FileReader(dirty));
			BufferedReader br2 = new BufferedReader(new FileReader(cleaned));
			BufferedReader br3 = new BufferedReader(new FileReader(ground));
			
			FileWriter fstream = new FileWriter("wrong_changes_cells.txt", false);
			BufferedWriter br4 = new BufferedWriter(fstream);	

			
			String line1, line2, line3;
			boolean colHead = true;
			//String[] colTypes = null;
			while((line1 = br1.readLine())!=null)
			{
				line2 = br2.readLine();
				line3 = br3.readLine();
				if(colHead)
				{
					colHead=false;//the first row is column head information, skip
					String[] cols = line1.split(",");
					//colTypes = new String[cols.length];
					for(int i = 0 ; i < cols.length; i++)
					{
						String col = cols[i];
						//colTypes[i] = col.substring(col.indexOf("(") + 1, col.length() - 1);
					}
					continue;
				}
				assert(line2!=null);
				assert(line3!=null);
				String[] col1 = parseCsvLine(line1);
				String[] col2 = parseCsvLine(line2);
				String[] col3 = parseCsvLine(line3);
				int nCols = Math.min(col1.length, Math.min(col2.length, col3.length));
				if (col1.length != col2.length || col1.length != col3.length) {
					System.err.println("Warning: row " + (numOfTuples + 1) + " column count mismatch (dirty=" + col1.length + ", cleaned=" + col2.length + ", ground=" + col3.length + "), comparing first " + nCols + " columns only.");
				}
				numOfTuples++;
				for(int i = 0; i < nCols; i++)
				{
					String cell1 = col1[i].trim();
					String cell2 = col2[i].trim();
					String cell3 = col3[i].trim();
					totalCells++;
					
					if (cell3.equals("NULL"))
					{
						cell3 = "";
					}

					
					if(!cell1.equals(cell3))
					{
						//System.out.println(cell1+" vs. "+cell3);
						numOfDirtyCells++;
					}
					
					
					if(!cell2.equals(cell1))
					{
						numOfChangedCells++;
						
						if(cell2.equals(cell3)   && ! cell1.equals(cell3))
						{
							numOfCorrectedChangedCells++;
							numerator += 1.0;
						}
						else
						{
							br4.write("Tuple: "+line1+"\n");
							br4.write("Dirty: "+cell1 + " Cleaned: "+cell2+" Ground: "+cell3+"\n");
						}
				}
				
			}
			}
			
			br4.close();
		
		} catch (FileNotFoundException e) {
			// TODO Auto-generated catch block
			e.printStackTrace();
		}
		catch (IOException e) {
			
			e.printStackTrace();
		}
		
		distance += disIntegerMax * numFVInteger;
		
		//double ave2 = (double)distance2/ (totalCells - numOfFVs);
		distance2 += disStringMax * numFVString;
		
		precision = numerator / numOfChangedCells;
		recall = numerator / numOfDirtyCells;
		
		printStatToConsole(0);
		
	}
	
	public void ComparePatterns(ArrayList<FD>[] fds)
	{
		//put all fds into one arraylist
		HashMap<FD, List<Integer>> ic_hits = new HashMap<FD, List<Integer>>();
		try {
			BufferedReader br1 = new BufferedReader(new FileReader(dirty));
			BufferedReader br2 = new BufferedReader(new FileReader(cleaned));
			BufferedReader br3 = new BufferedReader(new FileReader(ground));
			
			FileWriter fstream = new FileWriter("wrong_changes.txt", false);
			BufferedWriter br4 = new BufferedWriter(fstream);	

			

			
        	for (int i = 0; i < fds.length; i++)
        	{
        		ArrayList<FD> ar = fds[i];
        		for (FD f: ar)
        		{
        			ArrayList<Integer> l = new ArrayList<Integer>();
        			l.add(0);
        			l.add(0);
        			ic_hits.put(f, l);
        		
        		}
        	}			

			
			String line1, line2, line3;
			boolean colHead = true;
			//String[] colTypes = null;
			while((line1 = br1.readLine())!=null)
			{
				line2 = br2.readLine();
				line3 = br3.readLine();
				if(colHead)
				{
					colHead=false;//the first row is column head information, skip
					String[] cols = line1.split(",");
					//colTypes = new String[cols.length];
					for(int i = 0 ; i < cols.length; i++)
					{
						String col = cols[i];
						//colTypes[i] = col.substring(col.indexOf("(") + 1, col.length() - 1);
					}
					continue;
				}
				assert(line2!=null);
				assert(line3!=null);
				String[] col1 = parseCsvLine(line1);
				String[] col2 = parseCsvLine(line2);
				String[] col3 = parseCsvLine(line3);
				int nColsCompare = Math.min(col1.length, Math.min(col2.length, col3.length));
				if (col1.length != col2.length || col1.length != col3.length) {
					System.err.println("Warning: row " + (numOfTuples + 1) + " column count mismatch (dirty=" + col1.length + ", cleaned=" + col2.length + ", ground=" + col3.length + "), comparing first " + nColsCompare + " columns only.");
				}
				numOfTuples++;
				
				//get patterns
	        	for (int i = 0; i < fds.length; i++)
	        	{
	        		ArrayList<FD> ar = fds[i];
	        		for (FD f: ar)
	        		{
	        			int rhsIdx = f.getRHSColumnIndex();
	        			boolean outOfBounds = rhsIdx >= nColsCompare;
	        			for (int lhs_index : f.getLHSColumnIndexes()) {
	        				if (lhs_index >= nColsCompare) { outOfBounds = true; break; }
	        			}
	        			if (outOfBounds) continue;
	        			
	        			List<String> cell1 = new ArrayList<String>();
	        			List<String> cell2 = new ArrayList<String>();
	        			List<String> cell3 = new ArrayList<String>();
	        			
	        			totalCells++;
	        			
	        			for (int lhs_index: f.getLHSColumnIndexes())
	        			{
	    					 cell1.add(col1[lhs_index].trim());
	    					 cell2.add(col2[lhs_index].trim());
	    					 cell3.add(col3[lhs_index].trim());;	        				
	        			}
	        			
	  					 cell1.add(col1[rhsIdx].trim());
    					 cell2.add(col2[rhsIdx].trim());
    					 cell3.add(col3[rhsIdx].trim());
    					 
						List<Integer> ratio = ic_hits.get(f);

    					 
    						if(!cell1.equals(cell3))
    						{
    							//System.out.println(cell1+" vs. "+cell3);
    							numOfDirtyCells++;
    						}
    						
    						
    						if(!cell2.equals(cell1))
    						{
    							numOfChangedCells++;
    							
    							if(cell2.equals(cell3)   && ! cell1.equals(cell3))
    							{
    								numOfCorrectedChangedCells++;
    								numerator += 1.0;
    								
    								int hits = ratio.get(0);
    								ratio.set(0, hits + 1);
    							}
    							else
    							{
    								int misses = ratio.get(1);
    								ratio.set(1, misses + 1);
    								
    								br4.write("Tuple: "+line1+"\n");
    								br4.write("Dirty: "+cell1 + " Cleaned: "+cell2+" Ground: "+cell3+"\n");
    							}    					 
    						}
	        		
	        		
	        			
	        		}
					
	        		
	        	}  
	        	

			}
			
			br4.close();
		
		} catch (FileNotFoundException e) {
			// TODO Auto-generated catch block
			e.printStackTrace();
		}
		catch (IOException e) {
			
			e.printStackTrace();
		}
		
		distance += disIntegerMax * numFVInteger;
		
		//double ave2 = (double)distance2/ (totalCells - numOfFVs);
		distance2 += disStringMax * numFVString;
		
		precision = numerator / numOfChangedCells;
		recall = numerator / numOfDirtyCells;
		
		System.out.println("********************************(patterns) Holistic Cleaning Stats*******************************");
		for (FD f: ic_hits.keySet())
		{
			System.out.println("FD: " + f + " hits: " + ic_hits.get(f).get(0) + " misses: " + ic_hits.get(f).get(1));
			
		}
		
		printStatToConsole(0);
		
	}
		
	
	public void printStatToFile(String setting, String filePath, long runningTime)
	{
		
		try {
			PrintWriter out = new PrintWriter(new FileWriter(dirty.replace("inputDB.csv", "repairStats.txt")));			
			out.println("********************************Holistic Cleaning Stats*******************************");
			out.println("The input is: " + dirty);
			out.println("The running time is (in milliseconds): " + runningTime);
			out.println("The total number of tuples is: " + numOfTuples);
			out.println("The total number of cells is: " + totalCells);
			out.println("The total number of fresh values is: " + numOfFVs);
			out.println("The total number of dirty cells is " + numOfDirtyCells);
			out.println("The total number of changed cells is: " + numOfChangedCells);
			out.println("The total number of correctly changed cells is " + numOfCorrectedChangedCells);
			out.println("The total number of partially correctly changed cells is " + numOfPartiallyCorrectedChangedCells);
			//out.println("The total number of wrongly changed cells is " + numOfWronglyChangedCells);
			out.println("The numerator function is : " + numerator);
			out.println("The precision of our system is : " + precision);
			out.println("The recall of our system is: " + recall);
			out.println("The integer distance function is: " + distance);
			//out.println(totalCells + " & " + numOfFVs + " & " +numOfDirtyCells+ " & " +numOfChangedCells+ " & " +numOfCorrectedChangedCells+ " & " +numOfPartiallyCorrectedChangedCells+ " & " +precision+ " & " +recall);
			out.println("setting" + "," + "totalCells" + "," + "numOfFVs" + "," + "numOfDirtyCells" +"," + "numOfChangedCells"+"," +"numOfCorrectedChangedCells"+"," + "numOfPartiallyCorrectedChangedCells "+ "," + "precision" +"," + "recall" + "," + "running time");
			out.println(setting + "," + totalCells + "," + numOfFVs + "," +numOfDirtyCells+"," +numOfChangedCells+"," +numOfCorrectedChangedCells+"," +numOfPartiallyCorrectedChangedCells+ "," +precision+"," +recall + "," + runningTime);
			out.println("********************************The End***********************************************");
			out.close();
		} catch (IOException e) {
			// TODO Auto-generated catch block
			e.printStackTrace();
		} 
		
	}
	public void printStatToConsole(long runningTime)
	{
		System.out.println("********************************Holistic Cleaning Stats******************************");
		System.out.println("The input is: " + dirty);
		System.out.println("The running time is (in milliseconds): " + runningTime);
		System.out.println("The total number of tuples is: " + numOfTuples);
		System.out.println("The total number of cells is: " + totalCells);
		System.out.println("The total number of fresh values is: " + numOfFVs);
		System.out.println("The total number of dirty cells is " + numOfDirtyCells);
		System.out.println("The total number of changed cells is: " + numOfChangedCells);
		System.out.println("The total number of correctly changed cells is " + numOfCorrectedChangedCells);
		System.out.println("The total number of partially correctly changed cells is " + numOfPartiallyCorrectedChangedCells);
		//out.println("The total number of wrongly changed cells is " + numOfWronglyChangedCells);
		System.out.println("The numerator function is  : " + numerator);
		System.out.println("The precision of our system is : " + precision);
		System.out.println("The recall of our system is: " + recall);
		System.out.println("The integer distance function is: " + distance);
		System.out.println("totalCells" + "," + "numOfFVs" + "," + "numOfDirtyCells" +"," + "numOfChangedCells"+"," +"numOfCorrectedChangedCells"+"," + "numOfPartiallyCorrectedChangedCells "+ "," + "precision" +"," + "recall");
		System.out.println(totalCells + "," + numOfFVs + "," +numOfDirtyCells+"," +numOfChangedCells+"," +numOfCorrectedChangedCells+"," +numOfPartiallyCorrectedChangedCells+ "," +precision+"," +recall);
		
		System.out.println("********************************The End***********************************************");
		
		//System.out.println(totalCells + " & " + numOfFVs + " & " +numOfDirtyCells+ " & " +numOfChangedCells+ " & " +numOfCorrectedChangedCells+ " & " +numOfPartiallyCorrectedChangedCells+ " & " +precision+ " & " +recall);
		
	}
	public String toString()
	{
		StringBuilder sb = new StringBuilder();
		sb.append("********************************Holistic Cleaning Stats******************************");
		sb.append("\n");
		sb.append("The input is: " + dirty);sb.append("\n");
		sb.append("The total number of tuples is: " + numOfTuples);sb.append("\n");
		sb.append("The total number of cells is: " + totalCells);sb.append("\n");
		sb.append("The total number of fresh values is: " + numOfFVs);sb.append("\n");
		sb.append("The total number of dirty cells is " + numOfDirtyCells);sb.append("\n");
		sb.append("The total number of changed cells is: " + numOfChangedCells);sb.append("\n");
		sb.append("The total number of correctly changed cells is " + numOfCorrectedChangedCells);sb.append("\n");
		sb.append("The total number of partially correctly changed cells is " + numOfPartiallyCorrectedChangedCells);sb.append("\n");
		//out.println("The total number of wrongly changed cells is " + numOfWronglyChangedCells);
		sb.append("The numerator function is  : " + numerator);sb.append("\n");
		sb.append("The precision of our system is : " + precision);sb.append("\n");
		sb.append("The recall of our system is: " + recall);sb.append("\n");
		sb.append("The distance function is: " + distance); sb.append("\n");

		sb.append("totalCells" + "," + "numOfFVs" + "," + "numOfDirtyCells" +"," + "numOfChangedCells"+"," +"numOfCorrectedChangedCells"+"," + "numOfPartiallyCorrectedChangedCells "+ "," + "precision" +"," + "recall");
		sb.append("\n");
		sb.append(totalCells + "," + numOfFVs + "," +numOfDirtyCells+"," +numOfChangedCells+"," +numOfCorrectedChangedCells+"," +numOfPartiallyCorrectedChangedCells+ "," +precision+"," +recall);
		sb.append("\n");
		sb.append("********************************The End***********************************************");sb.append("\n");
		
		return new String(sb);
	}
	
	public void printStatToCSV(String setting, long runningTime)
	{
		try {
			
			PrintWriter out = new PrintWriter(new FileWriter("ExpReport.csv", true));
			out.println(setting + "," + 
					numOfTuples + "," +
					totalCells + "," + 
					numOfFVs + "," +
					numOfDirtyCells+"," +numOfChangedCells+"," +
					numOfCorrectedChangedCells+"," +numOfPartiallyCorrectedChangedCells+ "," +
					precision+"," +recall + "," + 
					getF1(precision,recall) + ","+
					(runningTime/1000+1) + "," +
					distance + "," + distance2);
			out.close();
		} catch (IOException e) {
			// TODO Auto-generated catch block
			e.printStackTrace();
		} 
	}
	private double getF1(double pre, double rec)
	{
		return 2  * pre * rec / (pre + rec);
	}
	
	/**
	 * Get the number of changes, to choose between multiple runs
	 * @return
	 */
	public int getNumChanges()
	{
		return numOfChangedCells;
	}
	
	

	
}
