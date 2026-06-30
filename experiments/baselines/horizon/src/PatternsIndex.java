import java.io.BufferedReader;
import java.io.FileNotFoundException;
import java.io.FileReader;
import java.io.IOException;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.HashSet;
import java.util.PriorityQueue;


public class PatternsIndex {
	
	HashMap<PatternKey, HashMap<String, PriorityQueue<Value>>> map; //Stores keys and their values
	
	//HashMap<String, ArrayList<Pattern>> ids_pattern_map; //Map that maps ids to 2 patterns (when k = 1), these two patterns will belong to two connected FDs
	
	ArrayList<ArrayList<Pattern>> pattern_list;
	
	ArrayList<FD>[] ordered_fds;
	
	public PatternsIndex(ArrayList<FD>[] ordered_fds, ArrayList<ArrayList<Pattern>> pattern_list)
	{
		this.ordered_fds = ordered_fds;
		
		this.pattern_list = pattern_list;
		
		//Generate hash ids
		ArrayList<PatternKey> ids = generateHashIds();
		
		
		map = new HashMap<PatternKey, HashMap<String, PriorityQueue<Value>>>();
		
		//ids_pattern_map = new HashMap<String, ArrayList<Pattern>>(); 
		
		//buildIdsPatternMap();
		
/*		for (String s: ids_pattern_map.keySet())
		{
			System.out.println(">> Pattern key "+s);
			for (Pattern p: ids_pattern_map.get(s))
				p.printPattern();
		}*/
		
		for (PatternKey id: ids)
		{
			//Create entry in hashtable for each id
			
			//System.out.println(id);

			
			map.put(id, new HashMap<String, PriorityQueue<Value>>());
			
			
		}
	}
	
/*	
	// Geenrates patterns + support across different pattern tables
	public HashMap<String, PriorityQueue<Value>> generatePatternsFromId(
			String rawId, int targetId, String line) {
		
		assert (ids_pattern_map.containsKey(rawId));
		

		HashMap<String, PriorityQueue<Value>> patterns = new HashMap<String, PriorityQueue<Value>>();

		ArrayList<Pattern> plist = ids_pattern_map.get(rawId);

		
		//considering scneario v ---> targetId + others ----> w
		for (Pattern p : plist) {
			
			HashSet<Integer> lhs_ids = p.fd.getLHSColumnIndexes();
			
			if (p.fd.getRHSColumnIndex() == targetId) {
				//generate patterns with key (p.fd.lhs)
				

				
				ArrayList<Integer> l = new ArrayList<Integer>(lhs_ids);
				Collections.sort(l);

				ArrayList<Value> temp_keys = new ArrayList<Value>();
				
				String vals[] = CsvUtils.parseCsvLine(line);
				
				String o = "";
				
				for (int i: l)
				{
					o += vals[i] + " ";
				}
				
				o = o.trim();
				
				
				//Lookup association with lhs = o
				//Put all possible values for targeId that's associated with o (given)
				for (Value v: p.value_map.get(o))
				{
					temp_keys.add(v);
				}
				
				for (Pattern p2: plist)
				{
					if (p.fd == p2.fd) continue;
					
					HashSet<Integer> lhs2 = p2.fd.getLHSColumnIndexes();
					
					int lhs_rhs_key = -1;
					
					//targetId is assumed to be shared among fd1 and fd2
					for (int i: lhs2)
					{
						if (i == targetId)
						{
							lhs_rhs_key = i;
							break;
						}
					}
					
					assert (lhs_rhs_key != -1);
					
					String o2 = "";
					
					for (Value v: temp_keys)
					{
						for (int i: lhs2)
						{
							if (i == lhs_rhs_key)
							{
								o2 += v.value + " ";
								
							}
							else
								o2 += vals[i] + " ";
						}
						
						String rhs_val = vals[p2.fd.getRHSColumnIndex()];
						
						o2 = o2.trim();
						
						for (Value v2: p2.value_map.get(o2))
						{
							//patterns.put(key, value)
							
							if (v2.value == rhs_val)
							{
								if (patterns.containsKey(o2))
								{
									Value nv = new Value(v.value, v.support + v2.support);
									patterns.get(o2).add(nv);
								}
								else
								{
									PriorityQueue<Value> pq = new PriorityQueue<Value>();
									Value nv = new Value(v.value, v.support + v2.support);
									patterns.put(o2, pq);
								}
							}
						}
					}
				
					
					
				}
			}
			
			
		}
		
		return patterns;
	}
	
*/
	
	private void chase (String row, String separator, PatternKey pk, HashMap<Integer, String> join_keys, double support, int level)
	{
		
		if (level == pk.involved_fds.size()) return; //Recursion base case
		
		double sp = 0;
		
		HashMap<String, PriorityQueue<Value>> table = map.get(pk);
		
		//System.out.println("**" + id);
		
		String vals[] = row.split(separator);
		
		String id = pk.id;
		System.out.println("********* "+id);
		
		String ids[] = id.split(" "); //Get individual ids
		
		String current_key = "";
		
		//HashMap<String, PriorityQueue<Value>> patterns = generatePatternsFromId(id, Integer.parseInt(ids[ids.length - 1]), row);
		
		for (int i = 0; i < ids.length - 1; i++)
		{
			int index = Integer.parseInt(ids[i]);
			
			if (join_keys.containsKey(index))
				current_key += join_keys.get(index) + " ";
			else current_key += vals[index] + " ";
		}
		
		current_key = current_key.trim();
		
		System.out.println(">> current key: "+current_key);
		System.out.println(">> current id: "+pk.id);

		
		//int support = 0;
		
		ArrayList<FD> fd_list = pk.involved_fds;
		
		FD f = fd_list.get(level);
		
		System.out.println("         >> involved FD: "+f);

		

		int fd_order = f.getOrder();

		//System.out.println(f);
		
		
		ArrayList<Pattern> plist = pattern_list.get(fd_order);

		for (Pattern p : plist) {


			if (p.fd.equals(f)) {
				String key_fd = "";
				
				//System.out.println("p " + p.fd + "  " + f);
				//p.printPattern();
				//System.out.println();				

				for (int i : f.getLHSColumnIndexes()) {
					if (join_keys.containsKey(i)) key_fd += join_keys.get(i) + " ";
					else key_fd += vals[i] + " ";
				}

				key_fd = key_fd.trim();

				int rhs_fd = f.getRHSColumnIndex();

				//System.out.println("Getting pattern with id " + key_fd);

				PriorityQueue<Value> pq = p.getPattern(key_fd);
				
				

				if (pq != null) {
					//System.out.println("Key found "+pq.size());
					
					for (Value v: pq)
					{
						
						System.out.println("join key: "+v.value);
						
						
						join_keys.put(rhs_fd, v.value);
						
						//System.out.println(" ---- support: "+v.support);
						
						
						chase(row, separator, pk, join_keys, support + v.support, level+1);	
						
						//System.out.println("AFTER CHASE "+v.value);
						
						join_keys.remove(rhs_fd);
						
						
						
						sp = support + v.support;
						
						//System.out.println(level + " " + pk.involved_fds.size());
						
						if (level == pk.involved_fds.size() - 1) //Insert only when at final stage
						{
						
							int val_index = Integer.parseInt(ids[ids.length - 1]);
							String val =vals[val_index];
							
							if (join_keys.containsKey(val_index))
							{
								
								val = join_keys.get(val_index);
								//System.out.println("&&&&&&&& "+val);
							}
										
							//System.out.println("KKKK");
							
							
							
							sp = sp/(level+1);
							
							
							
							if (table.containsKey(current_key))
							{
								PriorityQueue<Value> vq = table.get(current_key);
								boolean found = false;
								//System.out.println("^^^?? "+val);
								//System.out.println("---"+vq.size());
								
								
								
								for (Value v2: vq)
								{
									//System.out.println("^^^ "+val +"   "+v2.value);
									if (v2.value.equals(val))
									{
										found = true;
										
										if (sp > v2.support)
										{
											v2.updateSupport(sp);
											//System.out.println("**** Inserting "+level+" "+current_key + " " + v2.value + " " + sp);
										}
									}
								}
								
								if (!found)
								{
									Value v3 = new Value(val, sp);
									vq.add(v3);
									//System.out.println("F**** Inserting "+level+" "+current_key + " " + v3.value + " " + sp);

								}
								

					
								
							}
							else //Add new pattern entry in hashtable
							{
								PriorityQueue<Value> pq2 = new PriorityQueue<Value>();
								
								
								Value v4 = new Value(val, sp);
								
								pq2.add(v4);
								
								table.put(current_key, pq2);
								
								//System.out.println("NEW **** Inserting "+level+" "+current_key + " " + v4.value + " " + v4.support );
								
							}	
						
						}						
						
						
						
						
						
						
					}

				}
				else return;
			}
		}
		
		
	}
	
	private void addEntrywChase(String row, String separator)
	{
		//if (level == pattern_list.size()) return; //Recursion base case
		
		
		
		for (PatternKey pk: map.keySet())
		{
			HashMap<Integer, String> map = new HashMap<Integer, String>();
			
			chase(row, separator, pk, map, 0, 0);
		}
	}	
	
	private void addEntry(String row, String separator)
	{
		String vals[] = row.split(separator);
		
		for (PatternKey pk: map.keySet())
		{
			HashMap<String, PriorityQueue<Value>> table = map.get(pk);
			
			//System.out.println("**" + id);
			
			String id = pk.id;
			
			String ids[] = id.split(" "); //Get individual ids
			
			String current_key = "";
			
			//HashMap<String, PriorityQueue<Value>> patterns = generatePatternsFromId(id, Integer.parseInt(ids[ids.length - 1]), row);
			
			for (int i = 0; i < ids.length - 1; i++)
			{
				int index = Integer.parseInt(ids[i]);
				current_key += vals[index] + " ";
			}
			
			current_key = current_key.trim();
			
			
			
			
			int val_index = Integer.parseInt(ids[ids.length - 1]);
			String val =vals[val_index];
			
			int support = 0;
			
			ArrayList<FD> fd_list = pk.involved_fds;
			
			for (FD f: fd_list)
			{
				int fd_order = f.getOrder();
				
				//System.out.println(f);
				ArrayList<Pattern> plist = pattern_list.get(fd_order);
				
				for (Pattern p: plist)
				{
					//System.out.println("p "+p.fd +"  "+f);
					
					if (p.fd.equals(f))
					{
						String key_fd = "";
						
						for (int i: f.getLHSColumnIndexes())
						{
							key_fd += vals[i] + " ";
						}
						
						
						key_fd = key_fd.trim();
						
						int rhs_fd = f.getRHSColumnIndex();
						
						//System.out.println("Getting pattern with id "+key_fd);
						
						PriorityQueue<Value> pq = p.getPattern(key_fd);
						
						if (pq != null)
						{
							System.out.println("Key found ");
							for (Value v: pq)
							{
								if (v.getValue().equals(vals[rhs_fd]))
								{
									support += v.support;
									break;
								}
							}
						}
					}
				}
			}		
			
			

			if (table.containsKey(current_key))
			{
				PriorityQueue<Value> vq = table.get(current_key);
				boolean found = false;
				
				
				for (Value v: vq)
				{
					if (v.getValue().equals(val))
					{
						v.updateSupport(support);
						found = true;
						break;
					}
				}
				
				if (!found)
				{
					vq.add(new Value(val, support));
				}
				
			}
			else //Add new pattern entry in hashtable
			{
				PriorityQueue<Value> pq = new PriorityQueue<>();
				
				Value v = new Value(val, support);
				
				pq.add(v);
				
				table.put(current_key, pq);
				
			}

		}
	}
	
	public void computePropagationScores(String filename, String separator)
	{
		try (BufferedReader br = new BufferedReader(new FileReader(filename))) {
		    String line;
		    
		    //Skip first line (column headers)
		    br.readLine();
		    
		    while ((line = br.readLine()) != null) {
		    	
		    	if (line.isEmpty()) continue;
		    	
		    	
		    	
		    	addEntrywChase(line, Pattern.separator);
		    }
		    
		
		} catch (FileNotFoundException e) {
			e.printStackTrace();
		} catch (IOException e) {
			e.printStackTrace();
	}
		
	}
	
	public void PopulateHashTablesFromFile(String filename, String separator)
	{
		try (BufferedReader br = new BufferedReader(new FileReader(filename))) {
		    String line;
		    
		    //Skip first line (column headers)
		    br.readLine();
		    
		    while ((line = br.readLine()) != null) {
		    	
		    	if (line.isEmpty()) continue;
		    	
		    	System.out.println(line);
		    	
		    	
		    	
		    	addEntrywChase(line, Pattern.separator);
		    	
		    	System.out.println("------");
		    }
		    
		
		} catch (FileNotFoundException e) {
			e.printStackTrace();
		} catch (IOException e) {
			e.printStackTrace();
	}		
		
	}
	
/*	
	public void buildIdsPatternMap()
	{
    	//Generate indexes
		
		
		
    	for (ArrayList<Pattern> list: pattern_list)
    	{
    		if (list.size() == 0) continue;
    		
    			
    		
    		for (Pattern p: list)
    		{
    				
    				
    				FD fd = p.fd;
    				
    				ArrayList<Integer> indexes = new ArrayList<Integer>();
    				
    				for (int i: fd.getLHSColumnIndexes())
    					indexes.add(i);
    				
    				indexes.add(fd.getRHSColumnIndex());
    				
    				Collections.sort(indexes);
    				
    				//Pattern.GenerateHashKeyIds(indexes, hashIds);
    				
    				
    				ArrayList<Pattern> adj_patterns = p.getAdjacentPatterns(pattern_list);
    				
	
    				for (Pattern ap: adj_patterns)
    				{
    					ap.printPattern();
    					
    					ArrayList<String> hashIds = new ArrayList<String>();
    					
    					ArrayList<Integer> LRIndexes = new ArrayList<Integer>();
    					
    					FD f = ap.fd;
    					
        				for (int i: fd.getLHSColumnIndexes())
        					LRIndexes.add(i);    	
        				
        				LRIndexes.add(f.getRHSColumnIndex());
        				
        				Collections.sort(LRIndexes);
        				
        				ArrayList<Integer> lhs_sorted = new ArrayList<Integer>(f.getLHSColumnIndexes());
        				
        				Collections.sort(lhs_sorted);
        				
        				System.out.println(LRIndexes + " * "+lhs_sorted);

        				Pattern.GenerateHashKeyIds(LRIndexes, lhs_sorted, hashIds);
        				
        				ArrayList<Pattern> l = new ArrayList<Pattern>();
        				l.add(p);
        				l.add(ap);
        				
        				for (String s: hashIds)
        				{
        					System.out.println(s);
        					ids_pattern_map.put(s, l);
        				}
    				}
    		}

    	}		
    	
    	
    	
	}	
	*/
	
	public ArrayList<PatternKey> generateHashIds()
	{
    	//Generate indexes
		
		ArrayList<PatternKey> hashIds = new ArrayList<PatternKey>();
		
    	for (ArrayList<FD> list: ordered_fds)
    	{
    		
    		if (list.size() == 0) continue;
    		
    		for (FD fd: list)
    		{
    				ArrayList<Integer> indexes = new ArrayList<Integer>();
    				
    				for (int i: fd.getLHSColumnIndexes())
    					indexes.add(i);
    				
    				indexes.add(fd.getRHSColumnIndex());
    				
    				Collections.sort(indexes);
    				
    				ArrayList<PatternKey> pklist = Pattern.GenerateHashKeyIds(indexes);
    				
    				for (PatternKey pk: pklist)
    				{
    					//Add involved fd
    					pk.addFD(fd);
    					hashIds.add(pk);
    				}
    				
    				
    				
    				ArrayList<FD> adj_fds = fd.getAdjacentFDs(ordered_fds);
    				
    				
    				
    				
    				for (FD f: adj_fds)
    				{
    					ArrayList<Integer> LRIndexes = new ArrayList<Integer>();
    					
        				for (int i: fd.getLHSColumnIndexes())
        					LRIndexes.add(i);    	
        				
        				LRIndexes.add(f.getRHSColumnIndex());
        				
        				Collections.sort(LRIndexes);
        				
        				ArrayList<Integer> lhs_sorted = new ArrayList<Integer>(f.getLHSColumnIndexes());
        				
        				Collections.sort(lhs_sorted);

        				ArrayList<PatternKey> pklist2 = Pattern.GenerateHashKeyIds(LRIndexes, lhs_sorted);
        				
        				for (PatternKey pk: pklist2)
        				{
        					pk.addFD(fd);
        					pk.addFD(f);
        					
        					hashIds.add(pk);
        				}
    				}
    		}

    	}		
    	
    	return hashIds;
    	
	}
	
	public void printIndexes()
	{
		for (PatternKey id: map.keySet())
		{
			HashMap<String, PriorityQueue<Value>> table = map.get(id);
			System.out.println(">> key: ");
			id.printPatternKey();
			
			for (String key: table.keySet())
			{
				PriorityQueue<Value> pq = table.get(key);
				
				System.out.print("[" + key + "], ");
				
				for (Value v: pq)
				{
					System.out.print("["+ v.value + ", "+v.support + "]");
				}
				
				System.out.println();
			}
			
		}
	}
	
		
	

}
