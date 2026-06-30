import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.FileNotFoundException;
import java.io.FileReader;
import java.io.IOException;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.PriorityQueue;




public class RepairManager {
	
	static ArrayList<ArrayList<Pattern>> fixed_patterns;
	
	LocalDependecyGraph g;
	Marker mk;
	PatternsIndex pindex;
	
	/** Delegate to shared CsvUtils. */
	private static String csvEscape(String value) {
		return CsvUtils.csvEscape(value);
	}
	
	
	
	public RepairManager(Marker mk, LocalDependecyGraph g, PatternsIndex pindex)
	{
		this.g = g;
		this.mk = mk;
		this.pindex = pindex;
	}
	
	public static void init_clean_patterns(PatternsIndex pindex)
	{
		fixed_patterns = new ArrayList<ArrayList<Pattern>>();
		
		
		for (int i = 0; i < pindex.pattern_list.size(); i++)
		{
			ArrayList<Pattern> al = new ArrayList<Pattern>();
			fixed_patterns.add(al);
			
			for (Pattern p: pindex.pattern_list.get(i))
			{
				Pattern pn = new Pattern(p.fd);
				al.add(pn);
			}
		}
		
		printCleanPatterns();
	}
	
	public static void printCleanPatterns()
	{
		System.out.println("Printing clean patterns");
		
		for (ArrayList<Pattern> plist: fixed_patterns)
			for (Pattern p: plist)
				p.printPattern();
	}
	
	public void repair(String line, BufferedWriter out) throws IOException
	{
		HashMap<Integer, QValue> vmap = g.vconfidence_map;
		
		String vals[] = CsvUtils.parseCsvLine(line);
		
		
		
		for (int i = 0; i < vals.length; i++)
		{
			
			if (!vmap.containsKey(i))
			{
				try {
					if (i == (vals.length - 1)) out.write(csvEscape(vals[i]));
					else
						out.write(csvEscape(vals[i])+",");			
					
				} catch (IOException e) {
					// TODO Auto-generated catch block
					e.printStackTrace();
				}
				continue;
			}
				
				
			g.updateRepairCover(i);
			
			//System.out.println("Repairing attribute id "+i);
		
			
			QValue qv = vmap.get(i);
			
			//if (mk.getAssignment(qv) == Marker.NodeAssignment.CHANGE)
			//{
				System.out.println("FULL COVER");
				
				if (g.getRepairCovers().get(i).cover.size() == 2) //Full repair cover
				{
					//System.out.println("&&& is it so "+g.getRepairCovers().get(i).cover.size());
					g.getRepairCovers().get(i).printRepairCover();
					
					Pattern p_left = g.getRepairCovers().get(i).cover.get(0);
					Pattern p_right = g.getRepairCovers().get(i).cover.get(1);
					
					FD f_l = p_left.fd;
					
					String l_key = p_left.getFirstKey();
					ArrayList<Pattern> p_clean = fixed_patterns.get(f_l.getOrder());
					
					Pattern target_pattern = null;
					
					for (Pattern p: p_clean)
					{
						FD f_2 = p.fd;
						
						if (f_2.equals(f_l))
						{
							target_pattern = p;
							break;
						}
					}
					
					assert (target_pattern != null);

					if (target_pattern.value_map.containsKey(l_key))
					{
						Value best_v =  target_pattern.value_map.get(l_key).element();
						
						if (!best_v.value.equals(qv.getValue()))
						{
							qv.setValue(best_v.value);
							vals[i] = best_v.value;
						}
						
						mk.updateAssignment(qv, Marker.NodeAssignment.FIXED);
						
						if (i == (vals.length - 1)) out.write(csvEscape(vals[i]));
						else
							out.write(csvEscape(vals[i])+",");						
						
						continue;
					}

					
					
					
					FD f_r = p_right.fd;
					
					ArrayList<Integer> l = new ArrayList<Integer>();
					l.addAll(f_l.getLHSColumnIndexes());
					l.addAll(f_r.getLHSColumnIndexes());
					l.add(f_r.getRHSColumnIndex());
					
					Collections.sort(l);
					
					String key_i = "";
					String key_v = "";
					
					
					for (Integer lhs_i: l)
					{
						if (lhs_i == i) continue;
						
						key_i += lhs_i +" ";
						key_v += vals[lhs_i] + " ";
					}
					
					key_i += i;
					
					key_v = key_v.trim();
					
					PatternKey pk = new PatternKey(key_i);
					pk.addFD(f_l);
					pk.addFD(f_r);
					
					//System.out.println("trying key: "+key_v);
					//System.out.println("printing pattern key: ");
					pk.printPatternKey();
					
					HashMap<PatternKey, HashMap<String, PriorityQueue<Value>>> map = pindex.map;
					
					HashMap<String, PriorityQueue<Value>> table = map.get(pk);
					
					PriorityQueue<Value> pq = table.get(key_v);
					
					Value best_value = pq.element();
					
					System.out.println("Best value is: "+best_value.value);
					
					String n_lhs = p_left.getFirstKey();
					Value n_rhs = p_right.getFirstPattern();
					
					ArrayList<Pattern> clean_patterns = fixed_patterns.get(f_l.getOrder());
					target_pattern = null;
					
					for (Pattern p: clean_patterns)
					{
						FD f_2 = p.fd;
						
						if (f_2.equals(f_l))
						{
							target_pattern = p;
							break;
						}
					}
					
					assert(target_pattern != null);
					
					//System.out.println("ADDING PATTERN: "+n_lhs + " "+best_value.value);
					target_pattern.addPattern(n_lhs, best_value);

					
					
					
					
					String new_lhs_2 = "";
					
					for (Integer id: f_r.getLHSColumnIndexes())
					{
						if (id == i) new_lhs_2 += best_value.value  + " ";
						else  new_lhs_2 += vals[id]  + " ";
							
					}
					
					new_lhs_2 = new_lhs_2.trim();
					
					clean_patterns = fixed_patterns.get(f_r.getOrder());
					target_pattern = null;
					
					for (Pattern p: clean_patterns)
					{
						FD f_2 = p.fd;
						
						if (f_2.equals(f_r))
						{
							target_pattern = p;
							break;
						}
					}
					
					assert(target_pattern != null);
					
					//System.out.println("ADDING PATTERN: "+new_lhs_2 + " "+best_value.value);
					target_pattern.addPattern(new_lhs_2, n_rhs);					
									
					
					
					

				}
				else if (g.getRepairCovers().get(i).cover.size() == 1) //Partial cover
				{
					Pattern p_left = g.getRepairCovers().get(i).cover.get(0);

					FD f_l = p_left.fd;
					
					
					if (p_left.value_map.isEmpty()) continue;
					String l_key = p_left.getFirstKey();
					
					
					ArrayList<Pattern> p_clean = fixed_patterns.get(f_l.getOrder());
					
					Pattern target_pattern = null;
					
					for (Pattern p: p_clean)
					{
						FD f_2 = p.fd;
						
						if (f_2.equals(f_l))
						{
							target_pattern = p;
							break;
						}
					}
					
					assert (target_pattern != null);

					if (target_pattern.value_map.containsKey(l_key))
					{
						Value best_v =  target_pattern.value_map.get(l_key).element();
						
						if (!best_v.value.equals(qv.getValue()))
						{
							qv.setValue(best_v.value);
							vals[i] = best_v.value;
						}
						
						mk.updateAssignment(qv, Marker.NodeAssignment.FIXED);
						if (i == (vals.length - 1)) out.write(csvEscape(vals[i]));
						else
							out.write(csvEscape(vals[i])+",");						
						
						continue;
					}					
					
					
					ArrayList<Integer> l = new ArrayList<Integer>();
					l.addAll(f_l.getLHSColumnIndexes());
					
					Collections.sort(l);
					
					String key_i = "";
					String key_v = "";
					
					
					for (Integer lhs_i: l)
					{
						
						key_i += lhs_i +" ";
						key_v += vals[lhs_i] + " ";
					}
					
					key_i += i;
					
					key_v = key_v.trim();	
					
					PatternKey pk = new PatternKey(key_i);
					pk.addFD(f_l);

					
					//System.out.println("2 trying key: "+key_v);
					//System.out.println("2 printing pattern key: ");
					pk.printPatternKey();
					
					HashMap<PatternKey, HashMap<String, PriorityQueue<Value>>> map = pindex.map;
					
					HashMap<String, PriorityQueue<Value>> table = map.get(pk);
					
					PriorityQueue<Value> pq = table.get(key_v);
					
					if (pq == null) continue; 
						
					Value best_value = pq.element();
					
					//System.out.println("2 Best value: "+best_value.value);
					
					String n_lhs = p_left.getFirstKey();
					
					ArrayList<Pattern> clean_patterns = fixed_patterns.get(f_l.getOrder());
					target_pattern = null;
					
					for (Pattern p: clean_patterns)
					{
						FD f_2 = p.fd;
						
						if (f_2.equals(f_l))
						{
							target_pattern = p;
							break;
						}
					}
					
					assert(target_pattern != null);
					
					//System.out.println("2 ADDING PATTERN: "+n_lhs + " "+best_value.value);
					target_pattern.addPattern(n_lhs, best_value);
				
				}
			//}

			
			mk.updateAssignment(qv, Marker.NodeAssignment.FIXED);
			if (i == (vals.length - 1)) out.write(csvEscape(vals[i]));
			else
				out.write(csvEscape(vals[i])+",");
			
			
		}
		
		out.write("\n");
	}
	
	
	
}
