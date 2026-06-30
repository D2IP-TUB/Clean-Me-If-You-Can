import java.util.*;


public class PatternList implements Comparator<PatternList>{
	
	ArrayList<PatternEntry> pattern_list;
	double total_score;
	
	
	
	public PatternList()
	{
		pattern_list = new ArrayList<PatternEntry>();
		total_score = 0;
	}
	
	public void add_pattern_entry(PatternEntry pe)
	{
		if (Graph.DEBUG)
			System.out.println("add_pattern_entry(): adding pattern entry: "+pe.LHS  + " -> "+pe.RHS + " with score: "+pe.score);
		
		pattern_list.add(pe);
		
/*		for (PatternEntry pent: pattern_list)
		{
			double diff = Math.abs(pent.score - pe.score);
			if (diff > 0.)
		}*/
		
		total_score += pe.score;
	}
	
/*	public void normalize()
	{
		double sum = 0;
		for (PatternEntry pe: pattern_list)
		{
			sum += pe.score;
		}
		
		for (int i = 0; i < pattern_list.size(); i++)
		{
			PatternEntry pe = pattern_list.get(i);
			
			if (i == 0) pe.score = 3*pe.score / sum;
			else pe.score = pe.score / sum;
		}		
	}*/
	
	public void print()
	{
		System.out.println("Printing pattern list");
		for (PatternEntry pe: pattern_list)
		{
			System.out.println(pe.LHS + " | " + pe.RHS + " | "+ pe.score + " | "+ pe.fd);
		}
	}
	
	public int compare(PatternList pl1, PatternList pl2)
    {		
		return Double.compare(pl2.total_score, pl1.total_score);
	}	

}
