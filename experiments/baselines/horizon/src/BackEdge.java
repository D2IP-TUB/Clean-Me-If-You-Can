
public class BackEdge {
	
	int node_id;
	String LHS;
	Value value;
	Pattern pattern;
	
	public BackEdge(int node_id, String LHS, Value value, Pattern pattern)
	{
		this.node_id = node_id;
		this.value = value;
		this.pattern = pattern;
		this.LHS = LHS;
	}
	
	public void updateBackEdgeScore(double score)
	{
		if (Graph.DEBUG) System.out.println("Updating score of back edge "+score);
		
		this.value.updateScore(score);
		
		Value n_v = value;
		
		pattern.value_map.get(LHS).remove(value);
		
		pattern.value_map.get(LHS).add(n_v);
		
		
		
	}
	
	
	
	@Override
	public String toString()
	{

		return "Back edge: "+node_id+" "+"["+LHS+" => "+value.value+"]" + pattern.fd;
	}
	

}
