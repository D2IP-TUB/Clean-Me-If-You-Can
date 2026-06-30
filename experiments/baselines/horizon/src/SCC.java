import java.util.ArrayList;
import java.util.LinkedList;


public class SCC extends Vertex {
	
	//private int id; //SCC id, dummy id that has real-world meaning
	private ArrayList<Vertex> vertices; //Member vertices of the SCC
	
	
	
	
	public SCC(int id)
	{
		super(id);
		
		vertices = new ArrayList<Vertex>();
		
		
		
	}

	
	public ArrayList<Vertex> getVertices()
	{
		return vertices;
	}
	
	public void addSCCVertex(Vertex v)
	{
		vertices.add(v);
	}

	
	@Override
	public String toString()
	{
		String s = "";
		
		s += id + " : ";
		
		for (Vertex v: vertices)
		{
			s += v;
		}
		
		s += " : ";
		
/*		for (Vertex v: adj)
		{
			s += v;
		}	*/	
		
		
		return s;
	}

}
