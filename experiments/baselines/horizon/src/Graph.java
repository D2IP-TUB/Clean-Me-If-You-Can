// Java implementation of Kosaraju's algorithm to print all SCCs
import java.io.*;
import java.util.*;
 
// This class represents a directed graph using adjacency list
// representation
class Graph
{
    
    //private LinkedList<Vertex> adj[]; //Adjacency List
	
	public static boolean DEBUG = true; //Print algorithm's output 
    
    HashMap<Integer, Vertex> list_vertices;
    LinkedList<Vertex> ordered_vertices;
    
    public LinkedList<SCC> list_sccs;
    
    public int current_scc_index;
 
    //Constructor
    Graph()
    {
        list_vertices = new HashMap<Integer, Vertex>();
        ordered_vertices = new LinkedList<Vertex>();
/*        
        for (int i=0; i<v; ++i)
        {
        	list_vertices[i] = new Vertex(i);
        }*/
        

/*        HashSet<Vertex> hs = new HashSet<Vertex>();
        
        hs.add(list_vertices[0]);
        hs.add(list_vertices[1]);
        

        
        list_vertices[v-1] = new VertexGroup(hs, v-1);  */        

        
        
        list_sccs = new LinkedList<SCC>();
        
        current_scc_index = 0;
    }
    
    public void addVertex(Vertex v)
    {
    	list_vertices.put(v.id, v);
    }
    
    public int getSize()
    {
    	return list_vertices.size();
    }
 
    //Function to add an edge into the graph
    void addEdge(int v, int w)  { list_vertices.get(v).addEdge(list_vertices.get(w)); }
 
    // A recursive function to print DFS starting from v
    void DFSUtil(Vertex v,HashMap<Integer, Boolean> visited, LinkedList<SCC> list_sccs, HashMap<Integer, Vertex> lvertices)
    {
        // Mark the current node as visited and print it
        visited.put(v.id, true);
        if (DEBUG) System.out.println(v + " parents : "+v.parents);
        
        list_sccs.get(current_scc_index).addSCCVertex(lvertices.get(v.id));
 
        Vertex n;
 
        // Recur for all the vertices adjacent to this vertex
        Iterator<Vertex> i = list_vertices.get(v.id).getAdj().iterator();
        while (i.hasNext())
        {
            n = i.next();
            if (!visited.get(n.id))
                DFSUtil(n,visited, list_sccs, lvertices);
        }
    }
    
    public boolean containsVertex(Vertex v)
    {
    	return list_vertices.containsKey(v.id);
    }
 
    // Function that returns reverse (or transpose) of this graph
    Graph getTranspose()
    {
        Graph g = new Graph();
        
        for (Integer v: list_vertices.keySet())
        {
        	g.addVertex(new Vertex(v));
        }
        
        for (Integer v: list_vertices.keySet())
        {
        	
        	//g.list_vertices[v] = new Vertex(v);
        	
            // Recur for all the vertices adjacent to this vertex
            Iterator<Vertex> i = list_vertices.get(v).getAdj().iterator();
            while(i.hasNext())
            {
            	Vertex u = i.next();
            	//g.list_vertices[u.id] = new Vertex(u.id);

            	g.list_vertices.get(u.id).addEdge(g.list_vertices.get(v));

            	//g.addEdge(u, new Vertex(v));
                
            	//g.adj[i.next().id].add(new Vertex(v));
            }
        }
        return g;
    }
 
    void fillOrder(int v, HashMap<Integer, Boolean> visited, Stack stack)
    {
    	
    	//System.out.println(v);
        // Mark the current node as visited and print it
        visited.put(v, true);
 
        // Recur for all the vertices adjacent to this vertex
        //System.out.println("---"+list_vertices.get(v).id);
        
        Iterator<Vertex> i = list_vertices.get(v).getAdj().iterator();
        while (i.hasNext())
        {
            Vertex n = i.next();
            if(!visited.get(n.id))
                fillOrder(n.id, visited, stack);
        }
 
        // All vertices reachable from v are processed by now,
        // push v to Stack
        stack.push(new Vertex(v));
    }
    
    void print()
    {
        for (Integer i: list_vertices.keySet())
        {
        	System.out.println(list_vertices.get(i));
        }    	
    }
        
 
    // The main function that finds and prints all strongly
    // connected components
    void printSCCs()
    {
        Stack stack = new Stack();
 
        // Mark all the vertices as not visited (For first DFS)
        HashMap<Integer, Boolean> visited = new HashMap<Integer, Boolean>();
        for (Integer i: list_vertices.keySet())
        {
        	visited.put(i, false);
        }
 
        // Fill vertices in stack according to their finishing
        // times
        for (Integer i: list_vertices.keySet())
            if (visited.get(i) == false)
                fillOrder(i, visited, stack);
        

 
        // Create a reversed graph
        Graph gr = getTranspose();
       
        //gr.print();
        
        // Mark all the vertices as not visited (For second DFS)
        for (Integer i: list_vertices.keySet())
            visited.put(i, false);
 
        // Now process all vertices in order defined by Stack
        while (stack.empty() == false)
        {
            // Pop a vertex from stack
            Vertex v = (Vertex)stack.pop();
 
            // Print Strongly connected component of the popped vertex
            if (visited.get(v.id) == false)
            {
            	list_sccs.add(new SCC(gr.current_scc_index));
            	
            	//System.out.println(gr.current_scc_index);
            	
                gr.DFSUtil(v, visited, list_sccs, list_vertices);
                
                
                gr.current_scc_index++;
                
                if (Graph.DEBUG) System.out.println();
            }
        }
    }
    
    // A recursive function used by topologicalSort
    void topologicalSortUtil(Vertex v, boolean visited[],
                             Stack stack, Vertex parent)
    {
        // Mark the current node as visited.
        visited[v.id] = true;
        Vertex i;
 
        // Recur for all the vertices adjacent to this
        // vertex
        Iterator<Vertex> it = list_vertices.get(v.id).getAdj().iterator();
        
        if (Graph.DEBUG) System.out.println("** "+v +" parent "+parent);
        
        while (it.hasNext())
        {
        	
            i = it.next();
            if (!visited[i.id])
            {
            	if (Graph.DEBUG) System.out.println("DFS "+i);
                topologicalSortUtil(i, visited, stack, v);
            }
            else
            {
            	if (Graph.DEBUG) System.out.println("Adding parent " + v + "to " + i.id);
            	list_vertices.get(i.id).parents.add(v);
            }
        }
 
        // Push current vertex to stack which stores result
        //Vertex vt =  new Vertex(v.id, parent);
        
        	list_vertices.get(v.id).parents.add(parent);
        
        ordered_vertices.add(list_vertices.get(v.id));
        stack.push(list_vertices.get(v.id));
    }
 
    // The function to do Topological Sort. It uses
    // recursive topologicalSortUtil()
    void topologicalSort()
    {
        Stack<Vertex> stack = new Stack<Vertex>();
        
        
 
        // Mark all the vertices as not visited
        boolean visited[] = new boolean[getSize()];
        
        for (int i = 0; i < getSize(); i++)
            visited[i] = false;
 
        // Call the recursive helper function to store
        // Topological Sort starting from all vertices
        // one by one

        
        for (Integer i: list_vertices.keySet())
        {
        	Vertex v = list_vertices.get(i);
        	
            if (visited[v.id] == false)
            {
            	if (Graph.DEBUG) System.out.println("||| " + v);
                topologicalSortUtil(v, visited, stack, new Vertex());
            }
        }
        
        if (Graph.DEBUG)
        {
            // Print contents of stack
            System.out.println("Printing stack");
            while (stack.empty()==false)
                System.out.print(stack.pop() + " ");        	
        }

    }
    
    
    static HashMap<Vertex, SCC> buildVertexSCCMap(LinkedList<SCC> list_sccs)
    {
        
        HashMap<Vertex, SCC> vertex_scc_map = new HashMap<Vertex, SCC>();
        
        for (SCC s: list_sccs)
        {
        	for (Vertex v: s.getVertices())
        		vertex_scc_map.put(v, s);
        } 
        
        return vertex_scc_map;
    }
    
    public Vertex getVertex(Integer v)
    {
    	return list_vertices.get(v);
    }
    
    SCCGraph buildSCCGraph(HashMap<Vertex, SCC> vertex_to_scc_map)
    {
    	SCCGraph scc_graph = new SCCGraph(list_sccs.size());
    	
    	for (SCC s: list_sccs)
    		scc_graph.list_vertices[s.id] = new SCC(s.id);
    	
    	for (SCC s: list_sccs)
    		for (Vertex v: s.getVertices())
    		{
    			scc_graph.list_vertices[s.id].addSCCVertex(v);
    			
    			for (Vertex u: v.getAdj())
    			{
    				scc_graph.list_vertices[s.id].addEdge(vertex_to_scc_map.get(u));
    				//System.out.println("Added edge "+ s.id + " " + vertex_to_scc_map.get(u));
    				//System.out.println("***" + scc_graph.list_vertices[2].getAdj().size());
    			}
    		}
    	
    	//System.out.println("***" + scc_graph.list_vertices[0].getAdj().size());
    	
    	return scc_graph;
    }
    
 
    // Driver method
    public static void main(String args[])
    {
    	
    	if (args.length < 4)
    	{
    		System.err.println("Need to specify data and ground truth file path!");
    		System.err.println("graph {dirty_data_file_path} {ground truth file path} {fd file} {algo}");
    		System.err.println("algo: 0 for greedy. 1 for RC. 2 for hybrid");
    		return;
    	}
    	
    	Pattern.data_file = args[0];
    	
    	Pattern.ground = args[1];
    	
    	Pattern.fd_file = args[2];
    	
    	Repairer.algo = Integer.parseInt(args[3]);
    	
    	System.out.println(args[0]);
    	
    	if (Repairer.algo != 0 && Repairer.algo != 1 && Repairer.algo != 2)
    	{
    		System.err.println("Error: Unknown algorithm index "+Repairer.algo);
    		System.err.println("algo: 0 for greedy. 1 for RC. 2 for hybrid");
    		return;    		
    	}
    	
    	
    	
    	Pattern.separator = ",";    	
    	
    	
    	//long startTime = System.nanoTime();    
    	long startTime = System.currentTimeMillis();
    	
    	FDParser fd_parser = new FDParser(Pattern.fd_file, ",");
    	
    	fd_parser.readFDFromFile_test();
    	
    	//if (Graph.DEBUG)
    	//{
    		//System.out.println("FD GRAPH: ");
    		//fd_parser.getFDGraph().print();
    	//}    	
    	
    	fd_parser.generate_partial_order();
    	


    	
    	ArrayList<FD> ordered_fds[] = fd_parser.getOrderedFDs();
    	
    	if (DEBUG)
    	{
        	System.out.println("FDs");
        	for (int i = 0; i < ordered_fds.length; i++)
        	{
        		ArrayList<FD> ar = ordered_fds[i];
        		for (FD f: ar)
        			System.out.println(f);
        	}    		
    	}


	
    	

    	
    	Pattern.initialize_node_quality_index();
    	
    	if (DEBUG) System.out.println("*************************** LOADING PATTERNS FROM INPUT FILE TO INSTANCE GRAPH *******************************");
    	ArrayList<ArrayList<Pattern>> pattern_list = Pattern.generatePatternList(ordered_fds);
    	//System.out.println("Done generating patterns");
    	
    	
    	if (DEBUG)
    	{
    		System.out.println("*************************** PATTERN LOADED FROM INPUT FILE *******************************");
	    	for (ArrayList<Pattern> plist: pattern_list)
	    	{
	    		for (Pattern p: plist)
	    			p.printPattern();
	    		
	    		System.out.println();	
	    	}
	    	
	    	System.out.println("Adjacency");
	    	for (ArrayList<Pattern> plist: pattern_list)
	    	{
	    		
	    		for (Pattern p: plist)
	    		{
	    			System.out.println(p.fd);
	    	      for (Pattern ap: p.getAdjacentPatterns(pattern_list))
	    	      {
	    	    	  System.out.println("\t\t"+ap.fd);
	    	      }
	    	     	
	    		}
	    		
	    		System.out.println();	
	    	}  	
    	
    	}
    	
    	Pattern.PropagateScores(pattern_list);
    	
    	if (DEBUG) 
    	{	
    		System.out.println("*************************** SCORE PROPAGATION DONE *******************************");
	    	Pattern.printNodeQualityIndex();
	    	
	    	for (ArrayList<Pattern> plist: pattern_list)
	    	{
	    		for (Pattern p: plist)
	    			p.printPattern();
	    		
	    		System.out.println();	
	    	}
    	}
    	
    	Repairer repairer = new Repairer(pattern_list);
    	
    	
    	
    	repairer.repair();
    	
    	//repairer.printCleanPatterns();
    	System.out.println("DONE");
    	
    	long estimatedTime = System.currentTimeMillis() - startTime;
    	//System.out.println("Elapsed time: "+estimatedTime/1000000.0);
    	
    	System.out.println("Elapsed time: "+estimatedTime);
    	
    	
    	
    	
    	//FileComparator fc = new FileComparator("5k_tax.csv.small", "clean_xu.csv.small", "5k_tax_gt.csv.small");
    	//FileComparator fc2 = new FileComparator(Pattern.data_file, Pattern.ground+".a"+Repairer.algo+".clean" , Pattern.ground);
    	
    	
    	FileComparator fc2 = new FileComparator(Pattern.data_file, Pattern.ground+".a"+Repairer.algo+".clean" , Pattern.ground, false);
    	fc2.CompareAndGenerateCells();
    	
       
    }
}