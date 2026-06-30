import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.PriorityQueue;
import java.util.Set;


public class InfluenceVSet {
	
	HashMap<Integer, HashSet<Pattern>> inf;
	
	HashMap<Integer, HashSet<Pattern>> inf_in; //gives parents of v(att_id), needed to compute repair cover
	HashMap<Integer, HashSet<Pattern>> inf_out; //gives children of v(att_id), needed to compute repair cover
	

	ArrayList<FD> ordered_fds[];
	ArrayList<ArrayList<Pattern>> ordered_patterns;
	
	
	public InfluenceVSet(ArrayList<FD> ordered_fds[], ArrayList<ArrayList<Pattern>> ordered_patterns)
	{
		inf = new HashMap<Integer, HashSet<Pattern>>();
		inf_in = new HashMap<Integer, HashSet<Pattern>>();
		inf_out = new HashMap<Integer, HashSet<Pattern>>();
		
		this.ordered_fds = ordered_fds; 
		this.ordered_patterns = ordered_patterns;
		
		
	}
	
	public double getRepairCover(Pattern pattern)
	{
		FD f = pattern.fd;
		
		for (int index: f.getLHSColumnIndexes())
		{
			
		}
		
		return 0;
	}
	
	public Set<Integer> getAttributeIndexes()
	{
		return inf.keySet();
	}
	
	public HashSet<Pattern> getInfFromAttributeIndex(int attribute_index)
	{
		
		return inf.get(attribute_index);
	}
	
	public HashSet<Pattern> getInfOutFromAttributeIndex(int attribute_index)
	{
		return inf_out.get(attribute_index);
	}
	
	public HashSet<Pattern> getInfInFromAttributeIndex(int attribute_index)
	{
		return inf_in.get(attribute_index);
	}
	
	public InfluenceVSet getLocalInfluenceSet(String line)
	{
		
		String vals[] = CsvUtils.parseCsvLine(line);
		
		ArrayList<ArrayList<Pattern>> local_patterns = new ArrayList<ArrayList<Pattern>>();
		
		for (int i = 0; i < ordered_patterns.size(); i++)
		{
			ArrayList<Pattern> plist = ordered_patterns.get(i);
			
			ArrayList<Pattern> local_pl = new ArrayList<Pattern>();
			
			for (int j = 0; j < plist.size(); j++)
			{
				
				FD f = plist.get(j).fd;
				
				Pattern local_pattern = new Pattern(f);
				
				String lhs_key = "";
				String rhs_val;

				for (Integer lhs_index : f.getLHSColumnIndexes()) {
					lhs_key += vals[lhs_index] + " ";
				}

				lhs_key = lhs_key.trim();

				rhs_val = vals[f.getRHSColumnIndex()];		
				
				PriorityQueue<Value> pq = plist.get(j).getPattern(lhs_key);

				for (Value v : pq) {
					if (v.value.equals(rhs_val)) {
						
						Value v_new = new Value(v.value, 0);
						
						local_pattern.addPattern(lhs_key, v_new);
						break;
					}
				}
				
				local_pl.add(local_pattern);				
					
			}
			
			local_patterns.add(local_pl);
		}
		
		InfluenceVSet local_inf = new InfluenceVSet(ordered_fds, local_patterns);
		
		local_inf.buildInfluenceVSet();
	
		return local_inf;
		
	}
	
	public void buildInfluenceVSet() {
		// traverse the fd graph and generate influence relationships
		for (ArrayList<Pattern> plist : ordered_patterns) {
			for (Pattern p : plist) {
				FD f = p.fd;

				// ArrayList<Pattern> adj_patterns =
				// p.getAdjacentPatterns(ordered_patterns);
				
				ArrayList<Pattern> parent_patterns = p
						.getParentPatterns(ordered_patterns);

				for (int lhs_index : f.getLHSColumnIndexes()) {
					if (inf.containsKey(lhs_index)) {
						HashSet<Pattern> pl = inf.get(lhs_index);
						pl.add(p);

						HashSet<Pattern> children = inf_out.get(lhs_index);
						
						children.add(p);
					} else {
						HashSet<Pattern> pl = new HashSet<Pattern>();
						pl.add(p);
						inf.put(lhs_index, pl);

						HashSet<Pattern> children = new HashSet<Pattern>();
						children.add(p);
						inf_out.put(lhs_index, children);
					}
				}
				

				for (int lhs_index : f.getLHSColumnIndexes()) {
					// The key always exists because of the previous step (a LHS
					// always had a RHS !)

					ArrayList<Pattern> parent_patterns_pruned = new ArrayList<Pattern>();

					for (Pattern pp : parent_patterns) {
						FD pf = pp.fd;

						if (pf.getRHSColumnIndex() == lhs_index) {
							parent_patterns_pruned.add(pp);
						}

					}



					HashSet<Pattern> pl = inf.get(lhs_index);

					pl.addAll(parent_patterns_pruned);

					if (inf_in.containsKey(lhs_index)) {
						HashSet<Pattern> parents = inf_in.get(lhs_index);
						parents.addAll(parent_patterns_pruned);
					} else {
						HashSet<Pattern> parents = new HashSet<Pattern>();
						parents.addAll(parent_patterns_pruned);

						inf_in.put(lhs_index, parents);
					}
					
				}
				
				if (inf.containsKey(f.getRHSColumnIndex()))
				{
					HashSet<Pattern> plist2 = inf.get(f.getRHSColumnIndex());
					plist2.add(p);
				}
				else
				{
					HashSet<Pattern> plist2 = new HashSet<Pattern>();
					plist2.add(p);
					inf.put(f.getRHSColumnIndex(), plist2);
					
					HashSet<Pattern> children = new HashSet<Pattern>();
					inf_out.put(f.getRHSColumnIndex(), children);
				}
				
				if (inf_in.containsKey(f.getRHSColumnIndex()))
				{
					HashSet<Pattern> plist2 = inf_in.get(f.getRHSColumnIndex());
					plist2.add(p);					
				}
				else
				{
					HashSet<Pattern> plist2 = new HashSet<Pattern>();
					plist2.add(p);
					inf_in.put(f.getRHSColumnIndex(), plist2);					
				}
				
			}
		}
	}
	
	public void printInfluenceVSetINOUT()
	{
		for (int att_id: inf.keySet())
		{
			System.out.println("Influence+ set for attribute id: "+att_id);
			
			for (Pattern p: inf_in.get(att_id))
			{
				FD f = p.fd;
				System.out.println("      "+f);
			}
			
			System.out.println("Influence- set for attribute id: "+att_id);
			
			for (Pattern p: inf_out.get(att_id))
			{
				FD f = p.fd;
				System.out.println("      "+f);
			}			
		}
		
		System.out.println();
	}	
	
	public void printInfluenceVSet()
	{
		for (int att_id: inf.keySet())
		{
			System.out.println("Influence set for attribute id: "+att_id);
			
			for (Pattern p: inf.get(att_id))
			{
				FD f = p.fd;
				System.out.println("      "+f);
			}
		}
		
		System.out.println();
	}

}
