import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.FileNotFoundException;
import java.io.FileReader;
import java.io.FileWriter;
import java.io.IOException;
import java.util.ArrayList;
import java.util.PriorityQueue;


public class LocalDependencyGraphManager {
	
	static InfluenceVSet inf;
	String filename; //input data file
	PatternsIndex pindex;
	
	public LocalDependencyGraphManager(InfluenceVSet inf, PatternsIndex pindex)
	{
		this.inf = inf;
		this.filename = Pattern.data_file;
		this.pindex = pindex;
	}
	
	public void GenerateLocalDepGraphsFromFile()
	{
		BufferedWriter out = null;

		
		try (BufferedReader br = new BufferedReader(new FileReader(filename))) {
			
		    FileWriter fstream = new FileWriter("clean_horizon.csv", false);
		    out = new BufferedWriter(fstream);
		    
		    
		    String line;
		    
		    
		    //Skip first line (column headers)
		    line = br.readLine();
		    out.write(line+"\n");
		    
		    RepairManager.init_clean_patterns(pindex);
		    
		    while ((line = br.readLine()) != null) {
		    	
		    	if (line.isEmpty()) continue;
		    	
		    	LocalDependecyGraph g = new LocalDependecyGraph(line);
		    	
		    	g.ComputeVConfidenceFromFile();
		    	
		    	//System.out.println("Tuple: "+line);
		    	
		    	//g.printVConfidenceMap();
		    	
		    	g.ComputeEConfidence(line);
		    	
		    	//g.printEConfidence();
		    	
		    	Marker marker = new Marker(g);
		    	
		    	marker.assignNodes_partial_cover();
		    	
		    	//marker.printAssignments();
		    	
		    	g.computeRepairCovers(marker);
		    	
		    	RepairManager rm = new RepairManager(marker, g, pindex);
		    	
		    	
		    	//System.out.println("*** Repairing");
		    	rm.repair(line, out);
		    	
		    	

		    }
		    
		    out.close();
		    	
		    	
		} catch (FileNotFoundException e) {
			e.printStackTrace();
		} catch (IOException e) {
			e.printStackTrace();
		}
		
		//RepairManager.printCleanPatterns();
		
	}	

}
