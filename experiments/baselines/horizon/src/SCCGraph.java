import java.util.ArrayList;
import java.util.HashSet;
import java.util.Iterator;
import java.util.LinkedList;
import java.util.Stack;


public class SCCGraph extends Graph {
	
	
	public SCC list_vertices[];
	public LinkedList<SCC> ordered_vertices;
	
	public SCCGraph(int size)
	{
		super();	
		
		list_vertices = new SCC[size];
		ordered_vertices = new LinkedList<SCC>();
		
	}
	
	
    // A recursive function used by topologicalSort
    void topologicalSortUtil(SCC v, boolean visited[],
                             Stack stack, SCC parent)
    {
        // Mark the current node as visited.
        visited[v.id] = true;
        Vertex i;
 
        // Recur for all the vertices adjacent to this
        // vertex
        Iterator<Vertex> it = list_vertices[v.id].getAdj().iterator();
        if (Graph.DEBUG) System.out.println("** "+v +" parent "+parent);
        
        while (it.hasNext())
        {
        	
            i = it.next();
            if (!visited[i.id])
            {
            	if (Graph.DEBUG) System.out.println("DFS "+i);
                topologicalSortUtil(list_vertices[i.id], visited, stack, v);
            }
            else
            {
            	if (Graph.DEBUG) System.out.println("Adding parent " + v + "to " + i.id);
            	list_vertices[i.id].parents.add(v);
            }
        }
 
        // Push current vertex to stack which stores result
        //Vertex vt =  new Vertex(v.id, parent);
        
        	list_vertices[v.id].parents.add(parent);
        
        ordered_vertices.add(list_vertices[v.id]);
        stack.push(list_vertices[v.id]);
    }	
	
	
    void topologicalSort()
    {
        Stack<Vertex> stack = new Stack<Vertex>();
        
        
 
        // Mark all the vertices as not visited
        boolean visited[] = new boolean[list_vertices.length];
        for (int i = 0; i < list_vertices.length; i++)
            visited[i] = false;
 
        // Call the recursive helper function to store
        // Topological Sort starting from all vertices
        // one by one

        
        for (SCC v: list_vertices)
            if (visited[v.id] == false)
            {
            	if (Graph.DEBUG) System.out.println("||| " + v);
                topologicalSortUtil(v, visited, stack, new SCC(-1));
            }
 
        if (Graph.DEBUG) 
        {
            // Print contents of stack
            System.out.println("Printing stack");
            while (stack.empty()==false)
                System.out.println(stack.pop() + " ");
                    	
        }


    }	
	
	
	public void print()
	{
        for (SCC v: list_vertices)
        {
        	System.out.print(v.id + " |" );
        	
        	
        	for (Vertex u: v.getVertices())
        		System.out.print(u.id + " ");
        	
        	System.out.print("|");
        	
        	for (Vertex p: v.parents)
        		System.out.print(p.id + " ");
        	
        	System.out.println();
        }    		
	}
	
	public void SCCToVertices()
	{
		if (Graph.DEBUG) System.out.println("SCCTovertices");
        for (SCC v: ordered_vertices)
        {
        	for (Vertex u: v.getVertices())
        	{
        		if (Graph.DEBUG) System.out.println(u.id + " ");
        		
        		if (u.id >= 200)
        		{
        			if (Graph.DEBUG) System.out.println("Vertex group");
        			
        			VertexGroup vg = (VertexGroup)u;
        			
        			for (Vertex vs: vg.getVertexGroup())
        			{
        				System.out.println(vs.id);
        			}
        		}
        	}
        	
        	if (Graph.DEBUG) System.out.println("----");
        		        	
        }
	}
	
	public void print_ordered()
	{
        for (SCC v: ordered_vertices)
        {
        	System.out.print(v.id + " |" );
        	
        	
        	for (Vertex u: v.getVertices())
        		System.out.print(u.id + " ");
        	
        	System.out.print("|");
        	
        	for (Vertex p: v.parents)
        		System.out.print(p.id + " ");
        	
        	System.out.println();
        }    		
	}	
	
	public ArrayList<HashSet<Vertex>> generatePartialOrder()
	{
		ArrayList<HashSet<Vertex>> poset = new ArrayList<HashSet<Vertex>>();
		
		Vertex prev = null;
		
		int pos_index = 0;
		
		if (ordered_vertices.size() > 0)
		{
			prev = ordered_vertices.get(ordered_vertices.size()-1);
			poset.add(new HashSet<Vertex>());
			
			for (Vertex u: ordered_vertices.get(ordered_vertices.size()-1).getVertices())
			{
				if (u.id >= 200)
				{
					VertexGroup vg = (VertexGroup)u;
					for (Vertex cv: vg.getVertexGroup())
					{
						poset.get(pos_index).add(cv);
					}
				}
				else
					poset.get(pos_index).add(u);
			}
			
			
			//System.out.println(prev);
			
		}
		
		for (int i = ordered_vertices.size()-2; i >= 0; i--)
		{
			if (ordered_vertices.get(i).hasSameParent(prev))
			{
				
				for (Vertex u: ordered_vertices.get(i).getVertices())
				{
					if (u.id >= 200)
					{
						VertexGroup vg = (VertexGroup)u;
						
						for (Vertex cv: vg.getVertexGroup())
						{
							poset.get(pos_index).add(cv);
						}
						
					}
					else
						poset.get(pos_index).add(u);
					
				}
			}
			else
			{
				
				pos_index++;
				
				HashSet<Vertex> hs = new HashSet<Vertex>();
				
				//poset.add(hs);
				
				for (Vertex u: ordered_vertices.get(i).getVertices())
				{
					if (u.id >= 200)
					{
						VertexGroup vg = (VertexGroup)u;
						
						for (Vertex cv: vg.getVertexGroup())
						{
							hs.add(cv);
						}
						
					}
					else
						hs.add(u);
				}
					
				
				prev = ordered_vertices.get(i);
				
				poset.add(hs);
			}
			
			
		}
		
		return poset;
	}
	
	public void printPartialOrder(ArrayList<HashSet<Vertex>> poset)
	{
		for (HashSet<Vertex> hs: poset)
		{
			for (Vertex v: hs)
			{
				System.out.print(v.id + " ");
			}
			
			System.out.println();
		}
	}

}
