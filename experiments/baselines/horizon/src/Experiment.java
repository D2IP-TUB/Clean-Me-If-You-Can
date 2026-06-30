import java.util.ArrayList;


public class Experiment {
	
	public String ground_truth_filename;
	public String ground_truth_separator;
	
	public Experiment(String ground_truth_file_name, String ground_truth_separator)
	{
		this.ground_truth_filename = ground_truth_file_name;
		this.ground_truth_separator = ground_truth_separator;		
	}
	
	public void compareToXu(ArrayList<FD> ordered_fds[])
	{
		double total_missed_keys = 0;
		double correct = 0;
		double ratio = 0;
		
		double total_found_vals = 0; 
		//generate GT patterns
		Pattern.data_file = "5k_tax_gt.csv";
		ArrayList<ArrayList<Pattern>> pattern_list_gt = Pattern.generatePatternList(ordered_fds);
		
		Pattern.data_file = "output_xu.csv";
		Pattern.separator = ",";
		
		ArrayList<ArrayList<Pattern>> repaired_patterns = Pattern.generatePatternList(ordered_fds);
		
		for (ArrayList<Pattern> pl: repaired_patterns)
			for (Pattern p: pl)
				p.printPattern();
		
		System.out.println("*********");
		
		for (int i = 0; i < pattern_list_gt.size(); i++)
		{
			ArrayList<Pattern> plist_gt = pattern_list_gt.get(i);
			ArrayList<Pattern> plist = repaired_patterns.get(i);
			
			for (int j = 0; j < plist_gt.size(); j++)
			{
				Pattern p_gt = plist_gt.get(j);
				Pattern p = plist.get(j);
				
				for (String key: p_gt.value_map.keySet())
				{
					Value v_gt = p_gt.getPattern(key).element();
					System.out.println(key);
					if (!p.value_map.containsKey(key))
					{
						total_missed_keys++;
						continue;
					}
					Value v = p.getPattern(key).element();
					
					System.out.println("Comparing "+key+" "+v.value +" to: "+v_gt.value);
					
					if (v.value.equals(v_gt.value))
					{
						System.out.println("Correct");
						correct++;
					}
					
					total_found_vals++;
				}
			}
		}
		
		ratio = correct / total_found_vals;
		
		double recall = correct / (total_found_vals + total_missed_keys);
		
		System.out.println("XU TOTAL VALS: "+total_found_vals);
		System.out.println("XU TOTAL MISSED KEYS: "+total_missed_keys);
		System.out.println("XU RECALL IS: "+recall);
		System.out.println("XU PRECISION IS: "+ratio);		
	}
	
	
	public void Precision(ArrayList<FD> ordered_fds[], ArrayList<ArrayList<Pattern>> repaired_patterns)
	{
		
		

		double total_missed_keys = 0;
		double correct = 0;
		double ratio = 0;
		
		double total_found_vals = 0; 
		//generate GT patterns
		Pattern.data_file = "5k_tax_gt.csv";
		ArrayList<ArrayList<Pattern>> pattern_list_gt = Pattern.generatePatternList(ordered_fds);
		
		for (int i = 0; i < pattern_list_gt.size(); i++)
		{
			ArrayList<Pattern> plist_gt = pattern_list_gt.get(i);
			ArrayList<Pattern> plist = repaired_patterns.get(i);
			
			for (int j = 0; j < plist_gt.size(); j++)
			{
				Pattern p_gt = plist_gt.get(j);
				Pattern p = plist.get(j);
				
				for (String key: p_gt.value_map.keySet())
				{
					Value v_gt = p_gt.getPattern(key).element();
					System.out.println(key);
					if (!p.value_map.containsKey(key))
					{
						total_missed_keys++;
						continue;
					}
					Value v = p.getPattern(key).element();
					
					//System.out.println("Comparing "+key+" "+v.value +" to: "+v_gt.value);
					
					if (v.value.equals(v_gt.value))
					{
						correct++;
					}
					
					total_found_vals++;
				}
			}
		}
		
		ratio = correct / total_found_vals;
		
		double recall = correct / (total_found_vals + total_missed_keys);
		
		System.out.println("TOTAL VALS: "+total_found_vals);
		System.out.println("TOTAL MISSED KEYS: "+total_missed_keys);
		System.out.println("RECALL IS: "+recall);
		System.out.println("PRECISION IS: "+ratio);
		
		
	}

}
