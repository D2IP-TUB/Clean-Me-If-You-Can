import java.util.HashSet;


public class VertexGroup extends Vertex {

	
	private HashSet<Vertex> vertex_group;
	
	private static int index = 200;
	
	public VertexGroup (HashSet<Vertex> group, Graph g)
	{	
		super(index++);
		
		
		
		vertex_group = group;
		
		
		//Add this node to the adjacency lists of its parents
		
		for (Integer i: g.list_vertices.keySet())
		{
			Vertex v = g.list_vertices.get(i);
			
			for (Vertex u: group)
			{
				if (v.hasEdge(u) && !vertex_group.contains(v))
				{
					v.addEdge(this);
				}
			}
		}

		


	}
	
	public HashSet<Vertex> getVertexGroup()
	{
		return vertex_group;
	}
	
	@Override
	public String toString()
	{
		String s = "("+id+ ": [";
		
		for (Vertex v: vertex_group)
			s += v.id + " ";
		
		s +="]: ";
		
		for (Vertex v: adj)
			s += v.id + " ";

		s += ": ";
			
		for (Vertex parent: parents)
			s += parent + " ";
		
		s += ")";
		
		//System.out.println("******* " + s + "********");
		
		return s;
	}

	
	
	
}
