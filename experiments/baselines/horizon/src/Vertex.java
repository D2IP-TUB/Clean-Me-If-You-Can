import java.util.ArrayList;
import java.util.HashSet;
import java.util.LinkedList;


public class Vertex {
	
	public int id;
	public HashSet<Vertex> parents;
	protected HashSet<Vertex> adj;
	
	public Vertex(int id, Vertex parent)
	{
		parents = new HashSet<Vertex>();
		
		this.id = id;
		this.parents.add(parent);
		adj = new HashSet<Vertex>();
	}
	
	public Vertex()
	{
		this.id = -1;
		parents = new HashSet<Vertex>();
		adj = new HashSet<Vertex>();
	}
	
	public Vertex(int id)
	{
		parents = new HashSet<Vertex>();
		
		this.id = id;
		//this.parents.add(new Vertex());
		adj = new HashSet<Vertex>();
		
	}
	
	public boolean hasSameParent(Vertex v)
	{
		for (Vertex u: v.parents)
		{
			if (!parents.contains(u))
				return false;
		}
		
		return true;
	}
	
	public boolean hasEdge(Vertex v)
	{
		//We can't have an edge going to a vertex group, 
		//because we're assuming we have canonical FDs,
		//i.e., |RHS| = 1
		
		return (v instanceof VertexGroup)? false : adj.contains(v);
	}
	
	public Vertex(Vertex v)
	{
		parents = new HashSet<Vertex>();
		adj = new HashSet<Vertex>();


		this.id = v.id;
		
		for (Vertex i: v.parents)
			parents.add(i);
		
		for (Vertex w: v.getAdj())
			adj.add(w);

		
	}
	
	public HashSet<Vertex> getAdj()
	{
		return adj;
	}
	
	public void addEdge(Vertex v)
	{
		if (!adj.contains(v) && v.id != id) adj.add(v);
	}
	
	@Override
	public String toString()
	{
		String s = "("+id+ ": ";
		
		for (Vertex v: adj)
			s += v.id + " ";
		
		s += ": ";
			
		for (Vertex parent: parents)
			s += parent + " ";
		
		s += ")";
		
		//System.out.println("******* " + s + "********");
		
		return s;
	}
	
	
	   @Override
	   public int hashCode() {
	      //System.out.println("MyInt HashCode: " + i.hashCode());
	     return id;
	   }	

	   
	   @Override
	   public boolean equals(Object obj) {
		
		   return (id == ((Vertex)obj).id)? true : false;
	   
	   }	

}
