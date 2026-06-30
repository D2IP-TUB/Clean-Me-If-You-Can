import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.FileNotFoundException;
import java.io.FileReader;
import java.io.FileWriter;
import java.io.IOException;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.PriorityQueue;


public class Repairer {
	
	static int algo; //0 for greedy. 1 for RC
	
	static ArrayList<ArrayList<Pattern>> repair_tables;
	
	ArrayList<ArrayList<Pattern>> pattern_list;
	
	public Repairer(ArrayList<ArrayList<Pattern>> pattern_list)
	{
		this.pattern_list = pattern_list;
		
		init_repair_tables();
	}
	
	public void init_repair_tables()
	{
		repair_tables = new ArrayList<ArrayList<Pattern>>();
		
		
		for (int i = 0; i < pattern_list.size(); i++)
		{
			ArrayList<Pattern> al = new ArrayList<Pattern>();
			repair_tables.add(al);
			
			for (Pattern p: pattern_list.get(i))
			{
				Pattern pn = new Pattern(p.fd);
				al.add(pn);
			}
		}
		
		//printCleanPatterns();
	}
	
	
	public PatternEntry getMaxEdge(Pattern p, HashMap<Integer, String> chase_graph_map, int parent_RHS_index, String join_key, String[] vals)
	{
		FD f = p.fd;
		
		PatternEntry pe = null;
		
		String key = "";
		
		for (Integer i: f.getLHSColumnIndexes())
		{
			if (i == parent_RHS_index) key += " " + join_key;
			else if (i < vals.length) key += " " + vals[i];
			else return null;
		}
		
		key = key.trim();
		
		Pattern child_repair_table = null;
		
    	ArrayList<Pattern> plist = pattern_list.get(f.getOrder());
    	for (int i = 0; i < plist.size(); i++)
    	{
    		Pattern pp = plist.get(i);
    		if (pp.fd.equals(f))
    		{
    			child_repair_table = repair_tables.get(f.getOrder()).get(i);
    			break;
    		}
    	}
    	
    	assert(child_repair_table != null);		
    	
    	if (!child_repair_table.value_map.containsKey(key))
    	{
    		int cRHS_index = f.getRHSColumnIndex();
    		if (cRHS_index >= vals.length) return null;
	    	String cRHS_val = vals[cRHS_index];
	    	cRHS_val = cRHS_val.trim();       
	    	
    		if (chase_graph_map.containsKey(cRHS_index)) //RHS value has been set
    		{

    			//Add LHS and RHS to repair table
    			String fixed_value = chase_graph_map.get(cRHS_index);
    			
    			if (Graph.DEBUG) System.out.println("getMaxEdge: RHS assigned already for FD " + f +"   "+fixed_value);
    			
    			Value cv = new Value(fixed_value, 0);
    			PriorityQueue<Value> pq = new PriorityQueue<Value>();
    			pq.add(cv);
    			
    			//Fetch key, rhs_val in pattern table, if not found, assign 0 as this edge does not exist in IG
    			
    			if (Graph.DEBUG)
    				System.out.println("key to fetch RC for is: "+key);
    			
    			if (p.value_map.containsKey(key))    		
    			{
	    			for (Value v: p.value_map.get(key))
	    			{
	    				if (v.value.equals(fixed_value))
	    				{
	    					cv.score = v.support;
	    					cv.support = v.support;
	    					break;
	    				}
	    			}
	    			
	    			
	    			pe = new PatternEntry(key, cv.value, cv.score, f, child_repair_table, p);    			
	    			
	    			if (Graph.DEBUG) System.out.println("\t\t (chase graph has RHS val assigned) winning value "+cv.value + "has score "+cv.score);
	    			
    			}
    			else
    			{
    				if (Graph.DEBUG) System.out.println(key + "does not exist in original data");
        			Value vwin = new Value(vals[f.getRHSColumnIndex()], 0);
        			
        			if (Graph.DEBUG) System.out.println("\t\t winning value "+vwin.value + "has score "+vwin.score);
        			
        			pe = new PatternEntry(key, vwin.value, vwin.score, f, child_repair_table, p);      				
    			}

    			
    			//child_repair_table.value_map.put(key, pq);

    		}
    		else
    		{
    			//System.out.println("Attempting key "+key);
    			
    			if (p.value_map.containsKey(key)) //BUG FIXED: It is possible that the made up key does not exist in original IG
    			{
        			Value vwin = p.value_map.get(key).element();
        			
        			if (Graph.DEBUG) System.out.println("\t\t winning value "+vwin.value + "has score "+vwin.score);
        			
        			pe = new PatternEntry(key, vwin.value, vwin.support, f, child_repair_table, p);    				
    			}
    			else
    			{
        			Value vwin = new Value(vals[f.getRHSColumnIndex()], 0);
        			
        			if (Graph.DEBUG) System.out.println("\t\t winning value "+vwin.value + "has score "+vwin.score);
        			
        			pe = new PatternEntry(key, vwin.value, vwin.support, f, child_repair_table, p);       				
    			}
    			


    		}
	    	
    	}
    	else
    	{
    		
        	//There was already a RHS assigned to LHS
        	Value v = child_repair_table.value_map.get(key).element();
        	
        	if (Graph.DEBUG) System.out.println("\t\t (RHS ASSIGNED TO LHS in Repair Table) winning value "+v.value + "has score "+v.score);
        	
        	pe = new PatternEntry(key, v.value, v.support, f, child_repair_table, p);     		
    	}

    	
		return pe;
	}
	
	public void repair_rc(String LHS, Pattern p, String[] vals, HashMap<Integer, String> chase_graph_map)
	{
		FD fd = p.fd;
		
    	//Get repair table corresponding to current pattern
    	Pattern repair_table = null;
    	
    	ArrayList<Pattern> plist = pattern_list.get(fd.getOrder());
    	

    	for (int i = 0; i < plist.size(); i++)
    	{
    		Pattern pp = plist.get(i);
    		if (pp.fd.equals(fd))
    		{
    			repair_table = repair_tables.get(fd.getOrder()).get(i);
    			break;
    		}
    	}
    	
    	assert(repair_table != null);		
    
    	
    	if (Graph.DEBUG) System.out.println("LHS key: "+LHS+" for FD: "+fd);

    	
    	//Check if LHS has been assigned a RHS already
    	if (!repair_table.value_map.containsKey(LHS))
    	{
    		int RHS_index = fd.getRHSColumnIndex();
	    	if (RHS_index >= vals.length) return;
	    	String RHS_val = vals[RHS_index];
	    	RHS_val = RHS_val.trim();
	    	
	    	
	    	
    		if (chase_graph_map.containsKey(RHS_index)) //RHS value has been set
    		{
    			//Add LHS and RHS to repair table
    			Value v = new Value(chase_graph_map.get(RHS_index), 0);
    			PriorityQueue<Value> pq = new PriorityQueue<Value>();
    			pq.add(v);
    			
    			repair_table.value_map.put(LHS, pq);
    			
    			if (!p.value_map.containsKey(LHS))
    			{
    				p.addPattern(LHS, v, vals);
    			}
    			
    			
    			if (Graph.DEBUG) System.out.println("RHS value has been assigned "+chase_graph_map.get(RHS_index));
    			
    			return;
    		}
    		
    		//Need to traverse Chase graph to get best RCs
    		//ArrayList<Pattern> adj_patterns;
    		
    		PriorityQueue<PatternList> patterns = new PriorityQueue<>(5, new PatternList());
    		

    		
    		if (!p.value_map.containsKey(LHS))
    		{
    			if (fd.getRHSColumnIndex() >= vals.length) return;
    			Value new_edge = new Value(vals[fd.getRHSColumnIndex()], 0);
    			p.addPattern(LHS, new_edge, vals);
    		}
    		
    		//p.printPattern();
    		
    		for (Value v: p.value_map.get(LHS))
    		{
    			
    			if (Graph.DEBUG) System.out.println("\t RHS value: "+v.value+" "+v.score);
    			PatternList plist1 = new PatternList();
    			
    			PatternEntry pe1 = new PatternEntry(LHS, v.value, v.score, fd, repair_table, p);
    			
    			plist1.add_pattern_entry(pe1);

    			
    			
    			String join_key = v.value;
    			//System.out.println()
    			
    			//System.out.println("This has "+p.children_patterns.size() + "adjacent patterns");
    			
        		for (Pattern p_out: p.children_patterns)
        		{
        			if (Graph.DEBUG) System.out.println("Child pattern "+p_out.fd);
        			PatternEntry pe = getMaxEdge(p_out, chase_graph_map, RHS_index, join_key, vals);
        			
        			if (pe == null) continue;
        			
        			if (Graph.DEBUG) System.out.println("Max edge is: "+pe.LHS + " | "+pe.RHS);
        			
        			plist1.add_pattern_entry(pe);
        			
        		}
        		
        		//plist1.print();
        		
        		patterns.offer(plist1);

    		}
     		if (Graph.DEBUG)
    		{
     			System.out.println("Candidate RCs");
     			
        		for (PatternList pl: patterns)
        		{
        			pl.print();
        		}     			
    		}
    		

    		
    		//Take max patterns and put them into repair tables
    		PatternList max_list = patterns.poll();
    		
    		if (Graph.DEBUG)
    		{
        		System.out.println("I choose Repair Cover: ");
        		max_list.print();    			
    		}

    		
    		for (PatternEntry pe: max_list.pattern_list)
    		{
    			Pattern rt_max = pe.repair_table;
    			Pattern org_pattern = pe.org_pattern;
    			
    			if (!rt_max.value_map.containsKey(pe.LHS))
    			{
	    			FD fd_max = pe.fd;
	    			
	    			PriorityQueue<Value> pq_max = new PriorityQueue<Value>();
	    			pq_max.add(new Value(pe.RHS, pe.score));
	    			
	    			rt_max.value_map.put(pe.LHS, pq_max);
	    			
    				if (!org_pattern.value_map.containsKey(pe.LHS))
    				{
    					if (fd_max.getRHSColumnIndex() >= vals.length) continue;
    					Value new_edge = new Value(vals[fd_max.getRHSColumnIndex()], 0);
    					org_pattern.addPattern(pe.LHS, new_edge, vals);
    				}	    			
	    			
	    			//Update chase graph
	    			for (int index: fd_max.getLHSColumnIndexes())
	    			{
	    				if (Graph.DEBUG) System.out.println("Fetching "+pe.LHS+ " "+index);
	    				

	    				
	    				String val = org_pattern.getValueFromAttributeId(pe.LHS, index);
	    				
	    				if (!chase_graph_map.containsKey(index)) 
	    				{
		    				if (Graph.DEBUG) System.out.println("Updating chase graph ["+index+ ", "+val + "]");
		    				
		    				chase_graph_map.put(index, val);
	    				}
	    				else
	    				{
	    					if (Graph.DEBUG) System.out.println("Chase graph already contains val in that attribute "+chase_graph_map.get(index));
	    				}
	    			}
	    			
    				if (!chase_graph_map.containsKey(fd_max.getRHSColumnIndex())) 
    				{	    			
    					if (Graph.DEBUG) System.out.println("Updating chase graph ["+fd_max.getRHSColumnIndex()+ ", "+pe.RHS + "]");
		    			chase_graph_map.put(fd_max.getRHSColumnIndex(), pe.RHS);
    				}
	    			
    			}
    			
    		}

    		
    		
    	}
    	else
    	{
			//Update chase graph
    		if (Graph.DEBUG) System.out.println("LHS already has RHS " + repair_table.value_map.get(LHS).element().value + " | "+repair_table.value_map.get(LHS).element().score);

    		
			for (int index: fd.getLHSColumnIndexes())
			{
				
				String val = p.getValueFromAttributeId(LHS, index);
				if (!chase_graph_map.containsKey(index)) 
				{				
					if (Graph.DEBUG) System.out.println("Updating chase graph ["+index+ ", "+val + "]");
					chase_graph_map.put(index, val);
				}
			}    		
			
			if (!chase_graph_map.containsKey(fd.getRHSColumnIndex())) 
			{				
				if (Graph.DEBUG) System.out.println("Updating chase graph ["+fd.getRHSColumnIndex()+ ", "+repair_table.value_map.get(LHS).element().value + "]");
				chase_graph_map.put(fd.getRHSColumnIndex(), repair_table.value_map.get(LHS).element().value);
			}
			
    	}

    	
    	
    	
	}
	
	public void repair_greedy(String LHS, Pattern p, String[] vals, HashMap<Integer, String> chase_graph_map)
	{
		FD fd = p.fd;
		
    	//Get repair table corresponding to current pattern
    	Pattern repair_table = null;
    	
    	ArrayList<Pattern> plist = pattern_list.get(fd.getOrder());
    	

    	for (int i = 0; i < plist.size(); i++)
    	{
    		Pattern pp = plist.get(i);
    		if (pp.fd.equals(fd))
    		{
    			repair_table = repair_tables.get(fd.getOrder()).get(i);
    			break;
    		}
    	}
    	
    	assert(repair_table != null);		
    	

    	
    	if (Graph.DEBUG) System.out.println("LHS key: "+LHS+" for FD: "+fd);

    	
    	//Check if LHS has been assigned a RHS already
    	if (!repair_table.value_map.containsKey(LHS))
    	{
    		int RHS_index = fd.getRHSColumnIndex();
	    	if (RHS_index >= vals.length) return;
	    	String RHS_val = vals[RHS_index];
	    	RHS_val = RHS_val.trim();
	    	
	    	
	    	
//    		if (chase_graph_map.containsKey(RHS_index)) //RHS value has been set
//    		{
//    			//Add LHS and RHS to repair table
//    			Value v = new Value(chase_graph_map.get(RHS_index), 0);
//    			PriorityQueue<Value> pq = new PriorityQueue<Value>();
//    			pq.add(v);
//    			
//    			repair_table.value_map.put(LHS, pq);
//    			
//    			if (!p.value_map.containsKey(LHS)) //If key is made up, add it to pattern list
//    			{
//    				p.addPattern(LHS, v, vals);
//    			}    			
//    			
//    			
//    			if (Graph.DEBUG) System.out.println("RHS value has been assigned "+chase_graph_map.get(RHS_index));
//    			
//    			return;
//    		}
    		
    		//Need to traverse Chase graph to get best RCs
    		//ArrayList<Pattern> adj_patterns;
    		
    		PriorityQueue<PatternList> patterns = new PriorityQueue<PatternList>();
    		
    		if (!p.value_map.containsKey(LHS))
    		{
    			if (fd.getRHSColumnIndex() >= vals.length) return;
    			Value new_edge = new Value(vals[fd.getRHSColumnIndex()], 0);
    			p.addPattern(LHS, new_edge, vals);
    		}
    		
    		//Take RHS value with max score
    		Value greedy_target_value = p.value_map.get(LHS).element();
    		
/*    		for (Value tt: p.value_map.get(LHS))
    		{
    			System.out.println("\t\t "+tt.value + " | "+tt.score);
    		}*/
    		
    		if (Graph.DEBUG) System.out.println("\t\t greedy max value is: "+greedy_target_value.value + " | "+greedy_target_value.score);
    		
			for (int index: fd.getLHSColumnIndexes())
			{
				
				String val = p.getValueFromAttributeId(LHS, index);
				if (!chase_graph_map.containsKey(index)) 
				{				
					if (Graph.DEBUG) System.out.println("Updating chase graph ["+index+ ", "+val + "]");
					chase_graph_map.put(index, val);
				}
				

			} 
			
		
			
			if (!chase_graph_map.containsKey(fd.getRHSColumnIndex())) 
			{				
				if (Graph.DEBUG) System.out.println("Updating chase graph ["+fd.getRHSColumnIndex()+ ", "+greedy_target_value.value + "]");
				chase_graph_map.put(fd.getRHSColumnIndex(), greedy_target_value.value);
			}    	
			
			PriorityQueue<Value> pq = new PriorityQueue<Value>();
			pq.add(greedy_target_value);				
			repair_table.value_map.put(LHS, pq);		
			

    		

    		
    		
    	}
    	else
    	{
			//Update chase graph
    		if (Graph.DEBUG) System.out.println("LHS already has RHS " + repair_table.value_map.get(LHS).element().value + " | "+repair_table.value_map.get(LHS).element().score);

    		
			for (int index: fd.getLHSColumnIndexes())
			{
				
				String val = p.getValueFromAttributeId(LHS, index);
				if (!chase_graph_map.containsKey(index)) 
				{				
					if (Graph.DEBUG) System.out.println("Updating chase graph ["+index+ ", "+val + "]");
					chase_graph_map.put(index, val);
				}
			}    		
			
			if (!chase_graph_map.containsKey(fd.getRHSColumnIndex())) 
			{				
				if (Graph.DEBUG) System.out.println("Updating chase graph ["+fd.getRHSColumnIndex()+ ", "+repair_table.value_map.get(LHS).element().value + "]");
				chase_graph_map.put(fd.getRHSColumnIndex(), repair_table.value_map.get(LHS).element().value);
			}
			
    	}		
	}
	
	
	//Greedy + RC
	public void repair_hybrid(String LHS, Pattern p, String[] vals, HashMap<Integer, String> chase_graph_map, double threshold)
	{

    	
		if (!p.value_map.containsKey(LHS))
		{
			repair_rc(LHS, p, vals, chase_graph_map);
			return;
		}
		
		//Take RHS value with max score
		Value greedy_target_value = p.value_map.get(LHS).element();
		
		//System.out.println("threshold: "+LHS+" > "+greedy_target_value.value + " | " + greedy_target_value.score + " | " + greedy_target_value.support);
		
		if (greedy_target_value.score > threshold)
		{
			repair_greedy(LHS, p, vals, chase_graph_map);
		}
		else
		{
			repair_rc(LHS, p, vals, chase_graph_map);
		}    	

    	
		
	}
	
	
	public void repair()
	{
		

		
		try (BufferedReader br = new BufferedReader(new FileReader(Pattern.data_file))) {
		    String line;
		    
			FileWriter fstream = new FileWriter(Pattern.ground+".a"+algo+".clean", false);
			BufferedWriter out = new BufferedWriter(fstream);		    
		    
		    //Skip first line (column headers)
			//Copy first line into out file (column headers)
			line = br.readLine();
			out.write(line);
			out.write("\n");
		    
		    while ((line = br.readLine()) != null) {
		    	
		    	if (line.isEmpty()) continue;
		    	
		    	String vals[] = CsvUtils.parseCsvLine(line);
		    	HashMap<Integer, String> chase_graph_map = new HashMap<Integer, String>();
		    	
		    	if (Graph.DEBUG)
		    		System.out.println("Repairing tuple: "+line);
		    	
		    	//Check LHS,RHS mappings for all FDs
		    	for (int i = 0; i < repair_tables.size(); i++)
		    	{
		    		ArrayList<Pattern> plist = repair_tables.get(i);
		    		
		    		
		    		
		    		for (int j = 0; j < plist.size(); j++)
		    		{
		    			
		    			Pattern p =  plist.get(j);
		    			FD fd = p.fd;
		    			
			        	ArrayList<Pattern> plist_raw = pattern_list.get(fd.getOrder());
			        	Pattern tp = null;

			        	for (int k = 0; k < plist_raw.size(); k++)
			        	{
			        		Pattern pp = plist_raw.get(k);
			        		if (pp.fd.equals(fd))
			        		{
			        			tp = pp;
			        			break;
			        		}
			        	}		    			
		    			
		    	    	String LHS = "";
		    	    	for (int k: fd.getLHSColumnIndexes())
		    	    	{
		    	    		if (chase_graph_map.containsKey(k))
		    	    		{
		    	    			if (Graph.DEBUG) System.out.println("(setting chase graph LHS) "+chase_graph_map.get(k));
		    	    			LHS += " "+chase_graph_map.get(k);
		    	    		}
		    	    		else if (k < vals.length) LHS += " "+vals[k];
		    	    		else { LHS = null; break; }
		    	    		//else LHS += " "+tp.value_map.get(key)
		    	    	}
		    	    	if (LHS == null) continue;
		    	    	LHS = LHS.trim();		
		    	    	
		    	    	if (Graph.DEBUG) System.out.println("(LHS is) "+LHS);
		    			
		    			if (p.value_map.containsKey(LHS))
		    			{
		    				//Update chase graph
		    				for (int index: fd.getLHSColumnIndexes())
		    				{
		    					
		    					
		    					
		    					String val = tp.getValueFromAttributeId(LHS, index);
		    					if (!chase_graph_map.containsKey(index)) 
		    					{				
		    						if (Graph.DEBUG) System.out.println("(mapping found) Updating chase graph ["+index+ ", "+val + "]");
		    						chase_graph_map.put(index, val);
		    					}
		    				}
		    				
		    				if (!chase_graph_map.containsKey(fd.getRHSColumnIndex())) 
		    				{				
		    					if (Graph.DEBUG) System.out.println("Updating chase graph ["+fd.getRHSColumnIndex()+ ", "+p.value_map.get(LHS).element().value + "]");
		    					chase_graph_map.put(fd.getRHSColumnIndex(), p.value_map.get(LHS).element().value);
		    				}
		    			}
		    		}
		    		
		    	}
		    	
		    	
		    	//for (int i = pattern_list.size()-1; i >= 0; i--)
		    	for (int i = 0; i < pattern_list.size(); i++)
		    	{
		    		ArrayList<Pattern> plist = pattern_list.get(i);
		    		for (int j = 0; j < plist.size(); j++)
		    		{
		    			
		    			Pattern p =  plist.get(j);
		    			
		    			//System.out.println("FD: "+p.fd);
		    			FD fd = p.fd;

		    	    	
		    	    	//Build LHS pattern
		    	    	String LHS = "";
		    	    	for (int k: fd.getLHSColumnIndexes())
		    	    	{
		    	    		if (chase_graph_map.containsKey(k))
		    	    		{
		    	    			LHS += " "+chase_graph_map.get(k);
		    	    		}
		    	    		else if (k < vals.length) LHS += " "+vals[k];
		    	    		else { LHS = null; break; }
		    	    	}
		    	    	if (LHS == null) continue;
		    	    	LHS = LHS.trim();	
		    	    	
		    			
		    			if (algo == 1) repair_rc(LHS, p, vals, chase_graph_map);
		    			
		    			else if (algo == 0) repair_greedy(LHS, p, vals, chase_graph_map);
		    			
		    			else if (algo == 2) repair_hybrid(LHS, p, vals, chase_graph_map, 0);
		    		}
		    	 }
		    	
		    	//Copy chase graph into file
		    	for (int i = 0; i < vals.length; i++)
		    	{
		    		if (chase_graph_map.containsKey(i))
		    		{
		    			vals[i] = chase_graph_map.get(i);
		    		}
		    	}
		    	CsvUtils.writeCsvLine(out, vals);
		    	
		    	}
		    
		    
		    out.close();
		    
		} catch (FileNotFoundException e) {
			e.printStackTrace();
		} catch (IOException e) {
			e.printStackTrace();
		}	
	}
	
	
	public void printCleanPatterns()
	{
		System.out.println("Printing clean patterns");
		
		for (ArrayList<Pattern> plist: repair_tables)
			for (Pattern p: plist)
				p.printPattern();
	}
	
	

}
