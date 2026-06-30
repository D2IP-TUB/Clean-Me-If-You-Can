import java.util.HashMap;


public class PatternEntry {
	
	String LHS;
	String RHS;
	double score;
	FD fd;
	Pattern repair_table;
	Pattern org_pattern;
	
	public PatternEntry(String LHS, String RHS, double score, FD f, Pattern repair_table, Pattern org_pattern)
	{
		this.LHS = LHS;
		this.RHS = RHS;
		this.score = score;
		this.fd = f;
		this.repair_table = repair_table;
		this.org_pattern = org_pattern;
	}

}
