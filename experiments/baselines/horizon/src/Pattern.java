import java.io.BufferedReader;
import java.io.FileNotFoundException;
import java.io.FileReader;
import java.io.IOException;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Iterator;
import java.util.List;
import java.util.PriorityQueue;


public class Pattern {
	
	FD fd;
	static String data_file;
	static String separator;
	static String ground;
	static String fd_file;
	
	HashSet<String> visited_p = new HashSet<String>();
	
	HashMap<String, PriorityQueue<Value>> value_map; 
	
	HashMap<String, HashMap<Integer, String>> attributeId_to_value;
	
	HashSet<String> visited; //used during DFS. Stores LHS key
	
	//Used in propagation score computation. Maps LHS to average of all RHSs
	HashMap<String, Double> NodeQualityMap;
	
	HashMap<Integer, HashMap<String, HashSet<String>>> chaseIndex; //given chase index ID: map partial chase key value -> full LHS key (to be fetched from value_map)
	
	
	static List<HashMap<String, Double>> Node_Quality_Index;
	
	//static HashMap<Integer, ArrayList<Value>> back_edges;
	
	static ArrayList<BackEdge> back_edges;
	
	ArrayList<Pattern> parent_patterns;
	ArrayList<Pattern> children_patterns;
	
	
	public static int getTotalSizeAttributes()
	{
		try (BufferedReader br = new BufferedReader(new FileReader(data_file))) {
		    String line;
		    
		    //Skip first line (column headers)
		    br.readLine();
		    
		    while ((line = br.readLine()) != null) {
		    	
		    	if (line.isEmpty()) continue;
		    	
		    	String vals[] = CsvUtils.parseCsvLine(line);
		    	
		    	return vals.length;
		    	
		    }
		} catch (FileNotFoundException e) {
			e.printStackTrace();
		} catch (IOException e) {
			e.printStackTrace();
		}
		
		return 0;
	}
	
	
	public static void initialize_node_quality_index()
	{
		
		int attribute_size = getTotalSizeAttributes();
		
		Node_Quality_Index = new ArrayList<HashMap<String, Double>>(attribute_size);
		
		for (int i = 0; i < attribute_size; i++)
		{
			HashMap<String, Double> map = new HashMap<String, Double>();
			Node_Quality_Index.add(map);
		}
		
		
		//back_edges = new HashMap<Integer, ArrayList<Value>>();
		back_edges = new ArrayList<BackEdge>();
	}	
	
	public void buildRepairCover(ArrayList<ArrayList<Pattern>> pattern_list)
	{
		//Get parent patterns
		if (Graph.DEBUG) System.out.println("Building repair cover");
		for (Pattern parent_pattern: getParentPatterns(pattern_list))
		{
			parent_patterns.add(parent_pattern);
		}

		
		//Get children patterns
		for (Pattern children_pattern: getAdjacentPatterns(pattern_list))		
		{
			children_patterns.add(children_pattern);
		}
	}
	
	public static void PropagateScores(ArrayList<ArrayList<Pattern>> pattern_list)
	{
		
		//Pattern root_pattern = pattern_list.get(1).get(0);
		
		//assert(root_pattern != null);
		
		
		for (ArrayList<Pattern> plist: pattern_list)
		{
			for (Pattern p: plist)
			{
				for (String LHS: p.value_map.keySet())
				{
					
					if (Graph.DEBUG) System.out.println(">>>> Pattern: "+LHS+" "+p.fd);
					//p.computePropagationScores(pattern_list, LHS);
					p.computePropagationScores_simple(pattern_list, LHS, 0);
					
					
					if (Graph.DEBUG)  System.out.println("---");
				}				
			}
		}
		
		
		
		//reorder elements
		for (ArrayList<Pattern> plist: pattern_list)
		{
			for (Pattern p: plist)
			{
				for (String LHS: p.value_map.keySet())
				{
					ArrayList<Value> al = new ArrayList<Value>(p.value_map.get(LHS));
					
					p.value_map.get(LHS).clear();
					
					//re-insert
					for (Value v: al)
						p.value_map.get(LHS).offer(v);
				}				
			}
		}		
		
		
		//if (Graph.DEBUG) printNodeQualityIndex();
		
		
		for (BackEdge be: back_edges)
		{
			if (Graph.DEBUG) 
				{
					System.out.println("Processing "+be);
				}
			// Null check: skip if node or value not in Node_Quality_Index
			HashMap<String, Double> nodeIndex = Node_Quality_Index.get(be.node_id);
			if (nodeIndex != null && nodeIndex.containsKey(be.value.value)) {
				be.updateBackEdgeScore(nodeIndex.get(be.value.value));
			} else {
				if (Graph.DEBUG) {
					System.out.println("Warning: BackEdge value not found in Node_Quality_Index, using support as score");
				}
				be.updateBackEdgeScore(be.value.support);
			}
		}
		
		
		
/*		for (Integer node_id: back_edges.keySet())
		{
			if (Graph.DEBUG) System.out.println(node_id);
			Iterator<Value> it = back_edges.get(node_id).iterator();
			
			while (it.hasNext())
			{
				Value v = it.next();
				double s = (v.support + Node_Quality_Index.get(node_id).get(v.value))/2;
				v.updateScore(s);
				
				//TODO: Fix the back edge case. At the end of DFS, we should update the nodex index + pattern support values of back edges.
				
				
			}	
		}
*/
		
	}
	
	public void printNodeQualityMap()
	{
		for (String lhs: NodeQualityMap.keySet())
			System.out.println("KEY: "+lhs + " PROPA SCORE: "+NodeQualityMap.get(lhs));
	}
	
	
	public String getValueFromAttributeId(String key, int id)
	{
		//System.out.println(key +" "+id);
		return attributeId_to_value.get(key).get(id);
	}
	
	public void update_node_quality_index(String key, double score)
	{
		HashSet<Integer> LHS_indexes = this.fd.getLHSColumnIndexes();
		

		NodeQualityMap.put(key, score);

		
		for (int index: LHS_indexes)
		{
			HashMap<String, Double> map = Node_Quality_Index.get(index);
			
			
			
			//System.out.println(key +" | "+ index);
			String val = getValueFromAttributeId(key, index);
			
			double d = 0;
			
			if (map.containsKey(val))
			{
				d = map.get(val);
				if (d > 0) continue;
			}
			
			//System.out.println("\t\t Putting "+val+" "+score);
			
			map.put(val, score);
			
			if (Graph.DEBUG) System.out.println("*updating node index val "+val +" to "+score);
		}
		

	}
	
	public void updateScore(String LHS, ArrayList<Value> vlist)
	{
		//value_map.get(LHS).remove(v);
		
		for (Value v: vlist)
		{
			value_map.get(LHS).add(v);		
		}
		
		
	}
	
	public static void printIndent(int level)
	{
		for (int i = 0; i < level; i++)
			System.out.print(" ");
	}
	
	public ArrayList<Value> getArrayList(PriorityQueue<Value> pq)
	{
		
		ArrayList<Value> ret = new ArrayList<Value>();
		
		
		for (Value v: pq)
		{
			ret.add(v);
		}
		
		return ret;
		
	}
	
	public static void indent(int indent_level)
	{
		for (int i = 0; i < indent_level; i++)
			System.out.print("  ");
	}
	
	// Max depth for propagation to prevent stack overflow on deep graphs
	private static final int MAX_PROPAGATION_DEPTH = 20;
	
	// Entry point
	public double computePropagationScores_simple(ArrayList<ArrayList<Pattern>> pattern_list, String LHS, int indent)
	{
		// If already visited globally, return cached score or support
		if (isLHSvisited(LHS))
		{
			Double cachedScore = NodeQualityMap.get(LHS);
			if (cachedScore != null) return cachedScore;
			return value_map.containsKey(LHS) && !value_map.get(LHS).isEmpty() 
				? value_map.get(LHS).peek().support : 0.0;
		}
		
		// Limit depth to prevent stack overflow on deep (non-cyclic) graphs
		if (indent >= MAX_PROPAGATION_DEPTH)
		{
			double supportVal = value_map.containsKey(LHS) && !value_map.get(LHS).isEmpty() 
				? value_map.get(LHS).peek().support 
				: 0.0;
			visit(LHS);
			update_node_quality_index(LHS, supportVal);
			return supportVal;
		}
		
		ArrayList<Pattern> adjacent_patterns = getAdjacentPatterns(pattern_list);

		int key_id = fd.getRHSColumnIndex();
		
		visit(LHS);
		
		double score_global = 0;
		
		if (!value_map.containsKey(LHS) || value_map.get(LHS).isEmpty())
		{
			update_node_quality_index(LHS, 0.0);
			return 0.0;
		}
		
		Iterator<Value> it = value_map.get(LHS).iterator();
						
		if (Graph.DEBUG)
		{
			System.out.println();
			indent(indent);
			System.out.print(LHS + "-->");
		}	
		
		int rhs_size = 0;
		
		
		while (it.hasNext())
		{
			Value v = it.next();
			String key_value = v.value;		
						
			double score = v.support;
			double childSum = 0;
			int childCount = 0;
			
			if (Graph.DEBUG)
			{
				
				indent(indent);
				System.out.print("r: "+v.value+": "+score);
			}			
			
						
			for (Pattern p: adjacent_patterns)
			{
				//Get LHS keys for that adjacent pattern
				HashSet<String> adj_keys = p.getLHSFromJoinId(key_id, key_value);
				
				//if (Graph.DEBUG) System.out.println(p.fd);
				
				for (String lhs_key: adj_keys)
				{
					if (!p.isLHSvisited(lhs_key))
					{
						// Not visited yet - recurse
						double childScore = p.computePropagationScores_simple(pattern_list, lhs_key, indent + 1);
						
						if (Graph.DEBUG)
						{
							indent(indent);
							System.out.print(lhs_key+": "+childScore);
						}
						
						childSum += childScore;
						childCount++;
					}
					else
					{
						// Already visited - use cached score or support as fallback
						Double visitedScore = p.NodeQualityMap.get(lhs_key);
						if (visitedScore == null) {
							// Back edge case - score not computed yet
							visitedScore = v.support;
							
							// Record for post-propagation update
							BackEdge be = new BackEdge(key_id, LHS, v, this);
							back_edges.add(be);
						}
						double childScore = visitedScore;
						if (Graph.DEBUG) {
							indent(indent);
							System.out.print("*v"+lhs_key+": "+childScore);
						}
						childSum += childScore;
						childCount++;
					}
				}
			}
			
			double averagedScore = score;
			if (childCount > 0)
			{
				double childAvg = childSum / childCount;
				averagedScore = (score + childAvg) / 2.0;
			}
			
			//update prio queue of value map
			v.updateScore(averagedScore);
			
			score_global += averagedScore;
			rhs_size++;

			// Uncomment for pure greedy
			// //update prio queue of value map
			// //v.updateScore(v.support);
			// //score_global += v.support;

			if (Graph.DEBUG && indent == 0)
			{
				System.out.println();
			}

			//it.remove();
			//v.score = score;
			
		
		}
		
		if (rhs_size > 0)
			score_global = score_global/rhs_size;
		
		
		update_node_quality_index(LHS, score_global);
		
		return score_global;
		
	}

	
	public double computePropagationScores(ArrayList<ArrayList<Pattern>> pattern_list, String LHS)
	{

		ArrayList<Pattern> adjacent_patterns = getAdjacentPatterns(pattern_list);
		
		//	for (String LHS: value_map.keySet())
		//	{
				if (Graph.DEBUG)
					{
						System.out.println("Visiting: "+LHS + " || "+fd);
					}
				
				if (isLHSvisited(LHS))
				{
					if (Graph.DEBUG) System.out.println("Already visited "+LHS);
					return 0;
				}
				


				
				double score = 0;
				double adj_edges = 0;				
		
				visit(LHS);
				
				update_node_quality_index(LHS, 0);
				NodeQualityMap.put(LHS, score);

				
				
				int key_id = fd.getRHSColumnIndex();
				
				Iterator<Value> it = value_map.get(LHS).iterator();
				ArrayList<Value> toAdd = new ArrayList<Value>();
				
				
				while (it.hasNext())
				{
					
					Value v = it.next();
					String key_value = v.value;
					
					
					score = v.support;
					
					
					if (Graph.DEBUG) System.out.println("*** SUPPORT: "+ v.support + " Value: "+v.value);
					
					
					
					adj_edges = 1;
					
					if (Node_Quality_Index.get(key_id).containsKey(key_value))
					{
						double s = Node_Quality_Index.get(key_id).get(key_value);
						
						if (Graph.DEBUG) System.out.println("Existing value for that attribute in node index "+key_id+ " | "+key_value + " and its score: "+s);
						
						//Node has been assigned a score
						if (s > 0)
						{
							if (Graph.DEBUG) System.out.println("Node has been assigned a score > 0. My support "+score);
							score = score + s;
							v.updateScore((score));
							//updateScore(LHS, v);
							
							if (Graph.DEBUG) System.out.println("Updated score for "+v.value+" is "+score);
							
							toAdd.add(v);
							//it.remove();

							
							//v.score = (score + s) / 2;

							NodeQualityMap.put(LHS, score);
							
							
							
							update_node_quality_index(LHS, score);
							
							//System.out.println("Score: "+v.score);
							
							update_node_quality_index(LHS, score);
							
							//return v.score;
						}
						else if (s == 0) //visited but not assigned a score yet
						{
							if (Graph.DEBUG) System.out.println("Back edge "+fd);
							
							BackEdge be = new BackEdge(key_id, LHS, v, this);
							back_edges.add(be);
							
							//v.updateScore((score+v.support));
							//updateScore(LHS, v);
							
							toAdd.add(v);
							//it.remove();
							
							if (Graph.DEBUG) System.out.println(be);
							
							//NodeQualityMap.put(LHS, v.support);
							update_node_quality_index(LHS, v.support);
							
							return v.support;
							
/*							if (back_edges.containsKey(key_id))
							{
								back_edges.get(key_id).add(v);
							}
							else
							{
								ArrayList<Value> list = new ArrayList<Value>();
								list.add(v);
								back_edges.put(key_id, list);
							}*/
							
							//return 0;
						}
						
						//continue;
					}

					HashSet<Pattern> visited = new HashSet<Pattern>();
					for (Pattern p: adjacent_patterns)
					{
						//Get LHS keys for that adjacent pattern
						HashSet<String> adj_keys = p.getLHSFromJoinId(key_id, key_value);
						
						if (Graph.DEBUG) System.out.println(p.fd);
						
						for (String lhs_key: adj_keys)
						{
							//TODO: Back edge case. When loading values from file, assign each index to its values and the associated score
							
							
							//System.out.println("ADJ KEY "+lhs_key);
							if (!p.isLHSvisited(lhs_key))
							{
								//System.out.println("SUP: "+v.support);
								score += p.computePropagationScores(pattern_list, lhs_key);
								adj_edges++;
							}
							else
							{
								Double visitedScore = p.NodeQualityMap.get(lhs_key);
								if (visitedScore == null) {
									// Cycle/early-visit case: score not computed yet.
									visitedScore = 0.0;
								}
								//System.out.println("Visited LHS node "+visitedScore);
								//p.printNodeQualityMap();
								if (Graph.DEBUG) System.out.println(lhs_key);
								score += visitedScore;
								score = score ;
								
								//NodeQualityMap.put(LHS, score);
								update_node_quality_index(LHS, score);
								if (Graph.DEBUG) System.out.println(">>> Propagation Score for "+LHS+": "+score);
								return score;
							}
							
							
						}
						
						
						
						if (Graph.DEBUG) System.out.println("adj edges and support "+adj_edges+", "+score);
						
						score = score/adj_edges ;
						
						
						
						if (Graph.DEBUG) System.out.println(">> Propagation Score for "+LHS+": "+score);
						
						v.updateScore(score);
						//updateScore(LHS, v);
						
						toAdd.add(v);
						
						//it.remove();
						//v.score = score;
					}
					
					if (adjacent_patterns.size() == 0) //No patterns connected to RHS
					{
						v.updateScore(v.support);
						//updateScore(LHS, v);
						
						toAdd.add(v);
						
						if (Graph.DEBUG) System.out.println("> Propagation Score for "+LHS+": "+score);
						
						
						//v.score = v.support;
					}

					//it.remove();
					
				}
				

				updateScore(LHS, toAdd);	
					
				//NodeQualityMap.put(LHS, score);
					
				update_node_quality_index(LHS, score);
					
				if (Graph.DEBUG) System.out.println("Returning "+score);
					
				return score;					

				

				
			
		//	}
		

	}
	
	public static void printNodeQualityIndex()
	{
		System.out.println("Printing Node Quality Index");
		for (int i = 0; i < Node_Quality_Index.size(); i++)
		{
			HashMap<String, Double> map = Node_Quality_Index.get(i);
			
			System.out.println("Node index: "+i);
			
			for (String nodeId: map.keySet())
				System.out.println("\t"+nodeId + " > "+map.get(nodeId));
				
		}
	}
	
	public boolean isLHSvisited(String LHS)
	{
		if (visited.contains(LHS)) return true;
		
		return false;
	}
	
	//Visit node during DFS
	public void visit(String LHS)
	{
		visited.add(LHS);
	}
	
	
	public Pattern(FD fd, ArrayList<FD>[] ordered_fds)
	{
		this.fd = fd;
		
		this.visited = new HashSet<String>();
		
		attributeId_to_value = new HashMap<String, HashMap<Integer, String>>();
		
		parent_patterns = new ArrayList<Pattern>();
		children_patterns = new ArrayList<Pattern>();

		
		value_map = new HashMap<String, PriorityQueue<Value>>();
		
		NodeQualityMap = new HashMap<String, Double>();
		
		chaseIndex = new HashMap<Integer, HashMap<String,HashSet<String>>>();
		
		//Does the LFS for the FD appear as RHS in other FDs?
		ArrayList<FD> parent_fds = fd.getParentFDs(ordered_fds);
		
		
		//Put key ids into the HashMap
		for (FD parent_fd: parent_fds)
		{
			int key_index = parent_fd.getRHSColumnIndex();
			
			HashMap<String,HashSet<String>> map = new HashMap<String, HashSet<String>>();
			if (!chaseIndex.containsKey(key_index))
			{
				chaseIndex.put(key_index, map);
			}
			
		}
	}	
	
	public void printChaseIndexIds()
	{
		System.out.println("---> Printing chase index ids for fd "+fd);
		for (int index: chaseIndex.keySet())
		{
			System.out.println(index);
		}
	}
	
	public void printChaseIndex()
	{
		System.out.println("---> Printing chase index for fd "+fd);
		
		for (int index: chaseIndex.keySet())
		{
			HashMap<String, HashSet<String>> map = chaseIndex.get(index);
			
			for (String key: map.keySet())
			{
				for (String v: map.get(key))
				{
					System.out.println("KEY: "+key+" LHS "+v);
				}
			
			   System.out.println();
			}
		}		
		
	}
	
	public Pattern(FD fd)
	{
		this.fd = fd;

		
		value_map = new HashMap<String, PriorityQueue<Value>>();
		
		NodeQualityMap = new HashMap<String, Double>();
		
		visited = new HashSet<String>();
		
		attributeId_to_value = new HashMap<String, HashMap<Integer, String>>();

		chaseIndex = new HashMap<Integer, HashMap<String, HashSet<String>>>();

		parent_patterns = new ArrayList<Pattern>();
		children_patterns = new ArrayList<Pattern>();
		
		//Does the LFS for the FD appear as RHS in other FDs?
		//ArrayList<FD> parent_fds = fd.getParentFDs(fd_list)
	}

	
	public String getFirstKey()
	{
		return value_map.keySet().iterator().next();
	}
	
	public void addPattern(String lhs_key, Value v)
	{
		PriorityQueue<Value> pq = new PriorityQueue<Value>();
		pq.add(v);
		value_map.put(lhs_key, pq);
		
		
	}	
	
	public void addPattern(String lhs_key, Value v, String[] vals)
	{
		PriorityQueue<Value> pq = new PriorityQueue<Value>();
		pq.add(v);
		value_map.put(lhs_key, pq);
		
		if (Graph.DEBUG) System.out.println("Adding value: "+lhs_key+" "+fd);
		//printPattern();
		
    	if (!attributeId_to_value.containsKey(lhs_key))
    	{
    		HashMap<Integer, String> map = new HashMap<Integer, String>();
    		
    		//System.out.println("Putting yy "+LHS + " ");
	    	for (int i: fd.getLHSColumnIndexes())
	    	{
	    		map.put(i, vals[i]);
	    		//System.out.println("\t "+i +" | "+vals[i]);
	    	}
	    	
	    	
	    	attributeId_to_value.put(lhs_key, map);
    		
    	}		
		
		
	}		
	
	public PriorityQueue<Value> getPattern(String key)
	{
		return value_map.get(key);
	}
	
	public Value getFirstPattern()
	{
		for (String k: value_map.keySet())
		{
			
			PriorityQueue<Value> pq = value_map.get(k);
			return pq.element();
		}
		
		return null;
	}
	
	public final void LoadPatternsFromFileSingleEntry(String[] vals)
	{
    	
    	

    	
    	
    	// Skip rows with insufficient columns for LHS or RHS.
    	for (int i: fd.getLHSColumnIndexes()) { if (i >= vals.length) return; }
    	if (vals.length <= fd.getRHSColumnIndex()) return;

    	//Build LHS pattern
    	String LHS = "";
    	for (int i: fd.getLHSColumnIndexes())
    	{
    		LHS += " "+vals[i];
    		
    	}
    	
    	
    	
    	LHS = LHS.trim();
    	
    	if (!attributeId_to_value.containsKey(LHS))
    	{
    		HashMap<Integer, String> map = new HashMap<Integer, String>();
    		
    		//System.out.println("Putting yy "+LHS + " ");
	    	for (int i: fd.getLHSColumnIndexes())
	    	{
	    		map.put(i, vals[i]);
	    		//System.out.println("\t "+i +" | "+vals[i]);
	    	}
	    	
	    	
	    	attributeId_to_value.put(LHS, map);
    		
    	}
/*    	else
    	{
    		HashMap<Integer, String> map = attributeId_to_value.get(LHS);
    		map.get(key)
    		
    	}*/
    		
    	
    	if (vals.length <= fd.getRHSColumnIndex()) return;

    	
    	String RHS = vals[fd.getRHSColumnIndex()];
    	RHS = RHS.trim();
    	
    	
    	if (Graph.DEBUG)
    		System.out.println("adding pattern "+LHS+ " -> "+RHS);
    			    	
    	if (value_map.containsKey(LHS))
    	{
    		PriorityQueue<Value> pq = value_map.get(LHS);
    		
    		Iterator<Value> it = pq.iterator();
    		
    		boolean found_rhs = false;
    		ArrayList<Value> toAdd = new ArrayList<Value>();
    				    		
    		while (it.hasNext())
    		{
    			
    			Value v = it.next();
    			
    			
    			
    			if (v.getValue().equals(RHS))
    			{
    				v.updateSupport(v.getSupport() + 1);
    				v.count = v.getSupport();
    				//updateScore(LHS, v);

    				toAdd.add(v);
    				
    				it.remove();
    				
    				found_rhs = true;
    				break;
    			}
    		}
    		
    		updateScore(LHS, toAdd);
    		
    		if (!found_rhs) //Add RHS value to LHS
    		{
    			
    			Value RHS_val = new Value(RHS, 1);
    			pq.add(RHS_val);
    		}
    	}
    	else //LHS not found
    	{
    		//System.out.println("$$$ Adding "+LHS.trim()+"   "+RHS);
    		PriorityQueue<Value> pq = new PriorityQueue<Value>(20);
    		Value RHS_val = new Value(RHS, 1);
    		

    		
    		pq.add(RHS_val);
    		
    		value_map.put(LHS.trim(), pq);


    	}
    	
    	//Add chase index entries
    	for (int index: chaseIndex.keySet())
    	{
    		HashMap<String, HashSet<String>> map = chaseIndex.get(index);
    		
    		String key = vals[index].trim();
    		
    		if (map.containsKey(key))
    		{
    			
    			if (map.get(key) != null)
    			{
    				if (!map.get(key).equals(LHS))
    				{
    					HashSet<String> list = map.get(key);
		    			list.add(LHS);		    					
    				}

	    			//map.put(key, list);
    			}
    			
    		}
    		else
    		{
    			HashSet<String> list = new HashSet<String>();
    			list.add(LHS);
    			map.put(key, list);
    		}
    	}		
	}

	
	public final void LoadPatternsFromFile()
	{
		try (BufferedReader br = new BufferedReader(new FileReader(data_file))) {
		    String line;
		    
		    //Skip first line (column headers)
		    br.readLine();
		    
		    while ((line = br.readLine()) != null) {
		    	
		    	if (line.isEmpty()) continue;
		    	
		    	
		    			    	
		    	String vals[] = CsvUtils.parseCsvLine(line);
		    	
		    	// Skip rows with insufficient columns for LHS or RHS.
		    	boolean lhsOk = true;
		    	for (int i: fd.getLHSColumnIndexes()) { if (i >= vals.length) { lhsOk = false; break; } }
		    	if (!lhsOk || vals.length <= fd.getRHSColumnIndex()) continue;
		    	
		    	//Build LHS pattern
		    	String LHS = "";
		    	for (int i: fd.getLHSColumnIndexes())
		    	{
		    		LHS += " "+vals[i];
		    		
		    	}
		    	
		    	
		    	
		    	LHS = LHS.trim();
		    	
		    	if (!attributeId_to_value.containsKey(LHS))
		    	{
		    		HashMap<Integer, String> map = new HashMap<Integer, String>();
		    		
		    		//System.out.println("Putting yy "+LHS + " ");
			    	for (int i: fd.getLHSColumnIndexes())
			    	{
			    		map.put(i, vals[i]);
			    		//System.out.println("\t "+i +" | "+vals[i]);
			    	}
			    	
			    	
			    	attributeId_to_value.put(LHS, map);
		    		
		    	}
		    	
		    	if (vals.length <= fd.getRHSColumnIndex()) continue;
		    	
		    	String RHS = vals[fd.getRHSColumnIndex()];
		    	RHS = RHS.trim();
		    			    	
		    	if (value_map.containsKey(LHS))
		    	{
		    		PriorityQueue<Value> pq = value_map.get(LHS);
		    		
		    		Iterator<Value> it = pq.iterator();
		    		
		    		boolean found_rhs = false;
		    		ArrayList<Value> toAdd = new ArrayList<Value>();
		    				    		
		    		while (it.hasNext())
		    		{
		    			
		    			Value v = it.next();
		    			
		    			
		    			
		    			if (v.getValue().equals(RHS))
		    			{
		    				v.updateSupport(v.getSupport() + 1);
		    				v.count = v.getSupport();
		    				//updateScore(LHS, v);

		    				toAdd.add(v);
		    				
		    				it.remove();
		    				
		    				found_rhs = true;
		    				break;
		    			}
		    		}
		    		
		    		updateScore(LHS, toAdd);
		    		
		    		if (!found_rhs) //Add RHS value to LHS
		    		{
		    			
		    			Value RHS_val = new Value(RHS, 1);
		    			pq.add(RHS_val);
		    		}
		    	}
		    	else //LHS not found
		    	{
		    		//System.out.println("$$$ Adding "+LHS.trim()+"   "+RHS);
		    		PriorityQueue<Value> pq = new PriorityQueue<Value>(20);
		    		Value RHS_val = new Value(RHS, 1);
		    		

		    		
		    		pq.add(RHS_val);
		    		
		    		value_map.put(LHS.trim(), pq);


		    	}
		    	
		    	//Add chase index entries
		    	for (int index: chaseIndex.keySet())
		    	{
		    		HashMap<String, HashSet<String>> map = chaseIndex.get(index);
		    		
		    		String key = vals[index].trim();
		    		
		    		if (map.containsKey(key))
		    		{
		    			
		    			if (map.get(key) != null)
		    			{
		    				if (!map.get(key).equals(LHS))
		    				{
		    					HashSet<String> list = map.get(key);
				    			list.add(LHS);		    					
		    				}

			    			//map.put(key, list);
		    			}
		    			
		    		}
		    		else
		    		{
		    			HashSet<String> list = new HashSet<String>();
		    			list.add(LHS);
		    			map.put(key, list);
		    		}
		    	}
		    }
		    
		} catch (FileNotFoundException e) {
			e.printStackTrace();
		} catch (IOException e) {
			e.printStackTrace();
		}
		
		//Normalize the support values
		normalizeSupport();
	}
	
	public HashSet<String> getLHSFromJoinId(int join_id, String key)
	{
		if (!chaseIndex.containsKey(join_id))
			return new HashSet<String>();
		
		HashMap<String, HashSet<String>> map = chaseIndex.get(join_id);
		
		if (!map.containsKey(key))
			return new HashSet<String>();
		
		return map.get(key);
	}
	
	public ArrayList<Integer> getJoinIds()
	{
		ArrayList<Integer> join_ids = new ArrayList<Integer>();
		
		for (int index: chaseIndex.keySet())
			join_ids.add(index);
		
		return join_ids;
	}
	
	public double getSumSupport()
	{
		double sum_support = 0;
		
		for (String key: value_map.keySet())
		{
			PriorityQueue<Value> pq = value_map.get(key);
			
			for (Value v: pq)
			{
				sum_support += v.getSupport();
			}		
		}	
		
		return sum_support;		
	}
	
	public double getMaxSupport()
	{
		double max_support = 1;
		
		for (String key: value_map.keySet())
		{
			PriorityQueue<Value> pq = value_map.get(key);
			
			for (Value v: pq)
			{
				//System.out.println("\t\t"+key + " | "+v.value + " | "+v.count);
				if (v.count > max_support)
					max_support = v.count;
			}			
		}	
		
		return max_support;
	}
	
	public double getMaxCount()
	{
		double max_count = 0;
		
		for (String key: value_map.keySet())
		{
			double t = 0;
			PriorityQueue<Value> pq = value_map.get(key);
			
			for (Value v: pq)
			{
				//System.out.println("\t\t"+key + " | "+v.value + " | "+v.count);
				
					t += v.count;
			}
			
			if (t > max_count)
			{
				max_count = t;
			}
		}	
		
		return max_count;
	}	
	
	public void normalizeSupport()
	{
		double sum_support_pattern = getSumSupport();
		//System.out.println("SUM SUPPORT FOR: "+this.fd + " "+sum_support_pattern);
		//double max_s = getMaxCount();
		double max_s = getMaxSupport();
		
		for (String key: value_map.keySet())
		{
			//System.out.println(key);
			PriorityQueue<Value> pq = value_map.get(key);
			double sum_support = 0;
			
			for (Value v: pq)
			{
				sum_support += v.getSupport();
			}
			
			Iterator<Value> it = pq.iterator();
			
			ArrayList<Value> toAdd = new ArrayList<Value>();
			
			while (it.hasNext())
			{
				Value v = it.next();
/*				if (v.support < 2) v.updateSupport(v.getSupport()/sum_support/2);
				
				else*/
				
				//System.out.println("SUMMMM: "+getMaxSupport() + "  | "+v.getSupport() + " | "+key + " | "+v.value);
				
					double confidence =  (double)v.getSupport() / (double)sum_support;
					double support = (double)v.getSupport() / max_s;
					
					
					//System.out.println(support);
					//double quality = (0.25*support+0.25*confidence);
					//double quality = (support+confidence)/2;
					double quality = support;
					
					
					v.updateSupport(quality);
					
					toAdd.add(v);
					it.remove();
					
					//updateScore(key, v);
					
					
					
					//v.updateSupport(v.getSupport()/max_support);
			}
			
			
			
			updateScore(key, toAdd);
		}
	}
	

	
	@Override
	public boolean equals(Object obj)
	{
		Pattern p = (Pattern)obj;
		
		if (this.fd.equals(p.fd)) return true;
		
		return false;
	}
	
	public ArrayList<Pattern> getParentPatterns(ArrayList<ArrayList<Pattern>> pattern_list)
	{
		ArrayList<Pattern> parent_patterns = new ArrayList<Pattern>();
		
		

		for (ArrayList<Pattern> list: pattern_list)
			for (Pattern p: list)
			{
				
				FD f = p.fd;
				
				if (f.equals(fd)) continue;
				
				for (int i: fd.getLHSColumnIndexes())
				{
					if (i == f.getRHSColumnIndex())
					{
						parent_patterns.add(p);
						break;
					}
				}
				
			}
		
		return parent_patterns;
				
	}		
	

	
	
	//True if RHS appears in LHS of another FD
	public ArrayList<Pattern> getAdjacentPatterns(ArrayList<ArrayList<Pattern>> pattern_list)
	{
		ArrayList<Pattern> adj_patterns = new ArrayList<Pattern>();
		
		//System.out.println("Getting ajdacent patterns to "+fd);

		for (ArrayList<Pattern> list: pattern_list)
			for (Pattern p: list)
			{
				
				FD f = p.fd;
				
				if (f.equals(fd)) continue;
				
				//System.out.println(f);
				
				
				for (int i: f.getLHSColumnIndexes())
				{
					//System.out.println(i + " @ " + fd.getRHSColumnIndex());
					if (i == fd.getRHSColumnIndex())
					{
						
						adj_patterns.add(p);
						break;
					}
				}
				
				
			}
		
		return adj_patterns;
				
	}	
	
	
	
	
	public static ArrayList<PatternKey> GenerateHashKeyIds(ArrayList<Integer> RLindexes, ArrayList<Integer> MIndexes)
	{

		ArrayList<PatternKey> ids = new ArrayList<PatternKey>();
		
		Collections.sort(RLindexes);
		
		for (int i: MIndexes)
		{
			String s = "";
			
			ArrayList<Integer> tmp = new ArrayList<Integer>();
			
			for (int l: RLindexes)
			{
				tmp.add(l);
				

				//System.out.print(l +  " ");
			}
			
			for (int j: MIndexes)
			{
				//if (i >= j) continue;
				if (i == j) continue;
				
				tmp.add(j);
				

				//System.out.print(j+" ");
			}
			
			Collections.sort(tmp);
			
			for (int l: tmp)
				s += l + " ";
			
			s += i;
			
			PatternKey pk = new PatternKey(s);
			ids.add(pk);
			
			//System.out.print(", "+i);
			
			//System.out.println();
		}
		
		return ids;
	}	
	
	
	
	public static ArrayList<ArrayList<Pattern>> generatePatternList(ArrayList<FD>[] ordered_fds)
	{
		
		ArrayList<ArrayList<Pattern>> pattern_list = new ArrayList<ArrayList<Pattern>>();	
		
		
		
		try (BufferedReader br = new BufferedReader(new FileReader(data_file))) {
		    String line;		
		    
		    

	    	for (ArrayList<FD> list: ordered_fds)
	    	{
	    		ArrayList<Pattern> patterns = new ArrayList<Pattern>();
	    		for (FD f: list)
	    		{
	    			Pattern p = new Pattern(f, ordered_fds);
	    			patterns.add(p);	    			
	    		}
	    		
	    		pattern_list.add(patterns);
	    	
	    	}
		    
		    
		    br.readLine(); //Skip header
		    
		while ((line = br.readLine()) != null) {
			
			if (line.isEmpty()) continue;
		    			
		   	String vals[] = CsvUtils.parseCsvLine(line);
		   	
		   //	System.out.println(line);
		   	
	    	for (ArrayList<Pattern> patterns: pattern_list)
	    	{
	    		//if (list.size() == 0) continue;
	    		
	    		//ArrayList<Pattern> patterns = new ArrayList<Pattern>();
	    		//ArrayList<Pattern> patterns = pattern_list.get(index)
	    		
	    		
	    		for (Pattern p: patterns)
	    		{
	    			//FD f = p.fd;
	    			//Pattern p = new Pattern(f, ordered_fds);
	    			//patterns.add(p);
	    			
	    			
	    			
	    			//p.printChaseIndexIds();
	    			
	    			
	    			p.LoadPatternsFromFileSingleEntry(vals);
	    			//p.printPattern();
	    			
	    			
	    			//p.printChaseIndex();
	    		}
	    		
	    		//pattern_list.add(patterns);
	    	}
    	
		}
		
		for (ArrayList<Pattern> plist: pattern_list)
			for (Pattern p: plist)
			{
				
				p.buildRepairCover(pattern_list);
				//System.out.println(p.fd + "has adjacent patterns size "+p.children_patterns.size());
				p.normalizeSupport();
			}
		
		br.close();
		
	} catch (FileNotFoundException e) {
		e.printStackTrace();
	} catch (IOException e) {
		e.printStackTrace();
	}
    	
    	return pattern_list;
	}
	
	public static ArrayList<PatternKey> GenerateHashKeyIds(ArrayList<Integer> Indexes)
	{
		ArrayList<PatternKey> ids = new ArrayList<PatternKey>();
		
		for (int i: Indexes)
		{
			String s = "";
			
			for (int j: Indexes)
			{
				//if (i >= j) continue;
				if (i == j) continue;
				
				//System.out.print(j+" ");
				
				s += j + " ";
			}
			
			s += i;
			
			PatternKey pk = new PatternKey(s);			
			
			ids.add(pk);
			
			//System.out.print(", "+i);
			//System.out.println();
		}
		
		return ids;
		
		//System.out.println();
	}
	
	
	public void printPattern()
	{
		System.out.println("Printing patterns for FD: "+fd);
		
		for (String LHS: value_map.keySet())
			for (Value pq: value_map.get(LHS) )
			{
				System.out.println("["+LHS+", "+pq.getValue()+"("+pq.getSupport()+"), ("+pq.getScore()+")]");
			}
	}

}
