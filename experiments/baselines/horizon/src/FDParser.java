import java.io.BufferedReader;
import java.io.FileNotFoundException;
import java.io.FileReader;
import java.io.IOException;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Iterator;
import java.util.LinkedHashMap;
import java.util.Collections;

import org.apache.commons.collections4.keyvalue.MultiKey;
import org.apache.commons.collections4.map.MultiKeyMap;

public class FDParser {
	
	private String fds_file_name;
	
	private int size_attributes;
	
	
	private Graph fd_graph;
	
	private String separator; //separator character between LHS attributes of fds
	
    private ArrayList<FD> ordered_fds[];

	
	public FDParser(String fds_file_name, String separator)
	{
		this.fds_file_name = fds_file_name;
		
		this.separator = separator;
		
		fd_graph = new Graph();
	}
	
	public Graph getFDGraph()
	{
		return fd_graph;
	}
	
	public ArrayList<FD>[] getOrderedFDs()
	{
		return ordered_fds;
	}
	
	public int getAttributeSize()
	{
		return size_attributes;
	}
	
	public void readFDFromFile_test()
	{

		size_attributes = 0;

		
		MultiKeyMap<String, ArrayList<String>> multiKey = new MultiKeyMap<String, ArrayList<String>>();
		

		
		int max = 0;
		int lines = 0;
	
		try
		{

			
			BufferedReader reader = new BufferedReader(new FileReader(fds_file_name));
	
			while (reader.readLine() != null) lines++;
			reader.close();		
		}
		catch (Exception e)
		{
			e.printStackTrace();
			
		}
		
		ordered_fds = new ArrayList[lines];
		
		try (BufferedReader br = new BufferedReader(new FileReader(fds_file_name))) {
		    String line;
		    int o = 0;
		    
		    while ((line = br.readLine()) != null) {
		    	
		    	
		       
		    	if (line.isEmpty()) continue;
		    	
		    	String lhs_rhs[] = line.split("->");
		    	
		    	//Get lhs attributes
		    	String lhs_attributes[] = lhs_rhs[0].split(separator);
		    	
		    	HashSet<Integer> lhs_ids = new HashSet<Integer>();
		    	
		    	for (String att: lhs_attributes)
		    	{
		    		
		    		Integer att_id = Integer.parseInt(att.trim());
		    		lhs_ids.add(att_id);
		    		
		    		// Also build the fd_graph vertex for this LHS attribute
		    		Vertex v = new Vertex(att_id);
		    		if (!fd_graph.containsVertex(v))
		    		{
		    			size_attributes++;
		    			fd_graph.addVertex(v);
		    		}

		    	}
		    	
		    	//Assuming |rhs| = 1
		    	
		    	assert(lhs_rhs.length == 2);
		    	
		    	
		    	assert(!lhs_rhs[1].contains(","));
		    	
		    	
		    	//Adding the rhs
		    	int rhs_id = Integer.parseInt(lhs_rhs[1].trim());
		    	
		    	// Also build the fd_graph vertex for this RHS attribute
		    	Vertex rhs_v = new Vertex(rhs_id);
		    	if (!fd_graph.containsVertex(rhs_v))
		    	{
		    		size_attributes++;
		    		fd_graph.addVertex(rhs_v);
		    	}
		    	
		    	// Add edge(s) from LHS to RHS in the fd_graph
		    	if (lhs_attributes.length == 1)
		    	{
		    		// Single attribute LHS: add direct edge
		    		Vertex lhs_v = fd_graph.getVertex(Integer.parseInt(lhs_attributes[0].trim()));
		    		lhs_v.addEdge(fd_graph.getVertex(rhs_id));
		    	}
		    	else
		    	{
		    		// Multi-attribute LHS: build vertex group
		    		// For now, add edges from each LHS attribute to RHS
		    		// (VertexGroups are handled separately if needed)
		    		for (String att : lhs_attributes)
		    		{
		    			Integer att_id = Integer.parseInt(att.trim());
		    			fd_graph.getVertex(att_id).addEdge(fd_graph.getVertex(rhs_id));
		    		}
		    	}
		    	
		    	FD f = new FD(lhs_ids, rhs_id, o);
		    	ordered_fds[o] = new ArrayList<FD>();
		    	ordered_fds[o].add(f);
		    	
		    	o++;
		    }
		    
		} catch (FileNotFoundException e) {
			// TODO Auto-generated catch block
			e.printStackTrace();
		} catch (IOException e) {
			// TODO Auto-generated catch block
			e.printStackTrace();
		}
		
		
		if (Graph.DEBUG) 
		{
			fd_graph.print();
			
			
			for (MultiKey<? extends String> key: multiKey.keySet())
			{

					System.out.println(multiKey.get(key));
				
			}			
		}

		
		//Create vertex groups from multikey table
		for (MultiKey<? extends String> key: multiKey.keySet())
		{
			HashSet<Vertex> hs = new HashSet<Vertex>();
			
			//System.out.println((String)key.getKey(1));
			
			//Add member vertices
			for (Object lhs_att: key.getKeys())
			{
				Integer lhs_id = Integer.parseInt(((String)lhs_att).trim());
				hs.add(fd_graph.getVertex(lhs_id));
			}
			
			VertexGroup vg = new VertexGroup(hs, fd_graph);
			
			//Add edges between lhs and rhs atts
			ArrayList<String> rhs_nodes = multiKey.get(key);
			
			for (String rhs_n: rhs_nodes)
			{
				Integer rhs_id = Integer.parseInt(rhs_n);
				Vertex v = fd_graph.getVertex(rhs_id);
				vg.addEdge(v);
				
			}
			
			if (Graph.DEBUG) System.out.println(vg);
			
			fd_graph.addVertex(vg);
			

		}
		
		
		
	}	
	
	public void readFDFromFile()
	{

		size_attributes = 0;

		
		MultiKeyMap<String, ArrayList<String>> multiKey = new MultiKeyMap<String, ArrayList<String>>();
		
		int max = 0;
		
		
		try (BufferedReader br = new BufferedReader(new FileReader(fds_file_name))) {
		    String line;
		    while ((line = br.readLine()) != null) {
		       
		    	if (line.isEmpty()) continue;
		    	
		    	String lhs_rhs[] = line.split("->");
		    	
		    	//Get lhs attributes
		    	String lhs_attributes[] = lhs_rhs[0].split(separator);
		    	
		    	for (String att: lhs_attributes)
		    	{
		    		
		    		//Create vertex for the lhs attribute
		    		Vertex v = new Vertex(Integer.parseInt(att.trim()));
		    		
		    		if (!fd_graph.containsVertex(v))
		    		{
		    			size_attributes++;
		    			
		    			
		    			fd_graph.addVertex(v);
		    		}

		    	}
		    	
		    	
		    	
		    	//Assuming |rhs| = 1
		    	
		    	assert(lhs_rhs.length == 2);
		    	
		    	
		    	assert(!lhs_rhs[1].contains(","));
		    	
		    	
		    	//Adding the rhs
		    	int rhs_id = Integer.parseInt(lhs_rhs[1].trim());
		    	Vertex rhs_v = new Vertex(rhs_id);
		    	
		    	if (!fd_graph.containsVertex(rhs_v))
		    	{
	    			size_attributes++;
		    		
		    		fd_graph.addVertex(rhs_v);
		    	}
		    	
		    	if (lhs_attributes.length == 1)
		    	{
		    		//Add edge between lhs and rhs atts
		    		Vertex v = fd_graph.getVertex(Integer.parseInt(lhs_attributes[0].trim()));
		    		v.addEdge(rhs_v);
		    		
		    	}
		    	
		    	
		    	
		    	//Create vertex group, if any, max is 5 atts in lhs
		    	//Fill the multikey table, and after scanning all the individual atts, we'll assign ids to vertex groups
		    	
		    	if (lhs_attributes.length > 1)
		    	{
		    		if (lhs_attributes.length == 2)
		    		{
		    			if (multiKey.containsKey(lhs_attributes[0], lhs_attributes[1]))
		    			{
		    				multiKey.get(lhs_attributes[0], lhs_attributes[1]).add(lhs_rhs[1].trim());
		    			}
		    			else
		    			{
		    				ArrayList<String> rhs_nodes = new ArrayList<String>();
		    				rhs_nodes.add(lhs_rhs[1].trim());
		    				multiKey.put(lhs_attributes[0], lhs_attributes[1], rhs_nodes);
		    				
		    				if (Graph.DEBUG) System.out.println("Putting vertex "+lhs_attributes[0]+", "+lhs_attributes[1]);
		    			}
		    		}
		    		else if (lhs_attributes.length == 3)
		    			if (multiKey.containsKey(lhs_attributes[0], lhs_attributes[1], lhs_attributes[2]))
		    			{
		    				multiKey.get(lhs_attributes[0], lhs_attributes[1], lhs_attributes[2]).add(lhs_rhs[1].trim());
		    			}
		    			else
		    			{
		    				ArrayList<String> rhs_nodes = new ArrayList<String>();
		    				rhs_nodes.add(lhs_rhs[1].trim());
		    				multiKey.put(lhs_attributes[0], lhs_attributes[1], lhs_attributes[2], rhs_nodes);
		    			}		    			

		    		else if (lhs_attributes.length == 4)
		    			if (multiKey.containsKey(lhs_attributes[0], lhs_attributes[1], lhs_attributes[2], lhs_attributes[3]))
		    			{
		    				multiKey.get(lhs_attributes[0], lhs_attributes[1], lhs_attributes[2], lhs_attributes[3]).add(lhs_rhs[1].trim());
		    			}
		    			else
		    			{
		    				ArrayList<String> rhs_nodes = new ArrayList<String>();
		    				rhs_nodes.add(lhs_rhs[1].trim());
		    				multiKey.put(lhs_attributes[0], lhs_attributes[1], lhs_attributes[2], lhs_attributes[3], rhs_nodes);
		    			}			    			
		    		else if (lhs_attributes.length == 5)
		    			if (multiKey.containsKey(lhs_attributes[0], lhs_attributes[1], lhs_attributes[2], lhs_attributes[3], lhs_attributes[4]))
		    			{
		    				multiKey.get(lhs_attributes[0], lhs_attributes[1], lhs_attributes[2], lhs_attributes[3], lhs_attributes[4]).add(lhs_rhs[1].trim());
		    			}
		    			else
		    			{
		    				ArrayList<String> rhs_nodes = new ArrayList<String>();
		    				rhs_nodes.add(lhs_rhs[1].trim());
		    				multiKey.put(lhs_attributes[0], lhs_attributes[1], lhs_attributes[2], lhs_attributes[3], lhs_attributes[4], rhs_nodes);
		    			}		    					    		
		    		else
		    		{
		    			System.err.println("Too many LHS attributes");
		    			System.exit(1);
		    			
		    		}
		    			
		    	}
		    	
		    }
  
		    
		} catch (FileNotFoundException e) {
			// TODO Auto-generated catch block
			e.printStackTrace();
		} catch (IOException e) {
			// TODO Auto-generated catch block
			e.printStackTrace();
		}
		
		
		if (Graph.DEBUG) 
		{
			fd_graph.print();
			
			
			for (MultiKey<? extends String> key: multiKey.keySet())
			{

					System.out.println(multiKey.get(key));
				
			}			
		}

		
		//Create vertex groups from multikey table
		for (MultiKey<? extends String> key: multiKey.keySet())
		{
			HashSet<Vertex> hs = new HashSet<Vertex>();
			
			//System.out.println((String)key.getKey(1));
			
			//Add member vertices
			for (Object lhs_att: key.getKeys())
			{
				Integer lhs_id = Integer.parseInt(((String)lhs_att).trim());
				hs.add(fd_graph.getVertex(lhs_id));
			}
			
			VertexGroup vg = new VertexGroup(hs, fd_graph);
			
			//Add edges between lhs and rhs atts
			ArrayList<String> rhs_nodes = multiKey.get(key);
			
			for (String rhs_n: rhs_nodes)
			{
				Integer rhs_id = Integer.parseInt(rhs_n);
				Vertex v = fd_graph.getVertex(rhs_id);
				vg.addEdge(v);
				
			}
			
			if (Graph.DEBUG) System.out.println(vg);
			
			fd_graph.addVertex(vg);
			

		}
		
		
		
	}
	
	public void DFS(Vertex root, HashSet<String> fds, HashSet<Vertex> scc_group, ArrayList<FD> ordered_fds, int order, HashSet<String> fds_visited)
	{
				

		for (Vertex v: root.adj)
		{
			if (scc_group.contains(v))
			{
				if (!fds_visited.contains(root.id+" -> "+v.id))
				{
					fds_visited.add(root.id+" -> "+v.id);
					fds.add(root.id+" -> "+v.id);
					
					FD f = new FD(root, v, order);
					
					ordered_fds.add(f);					
					
				}

			}
					//System.out.println(root.id+" -> "+v.id);


		}
	}

	
	
	public void generate_partial_order()
	{
		// Step 1: Collect all original FDs before reordering
		ArrayList<FD> all_fds = new ArrayList<FD>();
		for (ArrayList<FD> list : ordered_fds)
		{
			for (FD f : list)
				all_fds.add(f);
		}
		
		// Step 2: Compute SCCs
		fd_graph.printSCCs();
		
        if (Graph.DEBUG)
        {
            System.out.println();
            for (SCC s: fd_graph.list_sccs)
            	System.out.println(s);	        	
        }
	
        HashMap<Vertex, SCC> vertex_scc_map = fd_graph.buildVertexSCCMap(fd_graph.list_sccs);
        SCCGraph scc_g = fd_graph.buildSCCGraph(vertex_scc_map);
        
        if (Graph.DEBUG) 
        {
        		System.out.println("SCC graph: ");
        		scc_g.print();
        }

        // Step 3: Topological sort on SCC graph
        scc_g.topologicalSort();
        
        if (Graph.DEBUG) 
        {
            System.out.println();
            System.out.println("Ordered SCC graph");
            scc_g.print();
            System.out.println();        	
        }

        // Step 4: Build attribute -> SCC order mapping
        // Reverse the topological order (first in topo order = lowest order number)
        ArrayList<SCC> topo_sccs = new ArrayList<SCC>();
        for (int i = scc_g.ordered_vertices.size() - 1; i >= 0; i--)
        	topo_sccs.add(scc_g.ordered_vertices.get(i));
        
        // Map: attribute_id -> order (based on SCC of that attribute)
        HashMap<Integer, Integer> attr_order = new HashMap<Integer, Integer>();
        for (int i = 0; i < topo_sccs.size(); i++)
        {
        	SCC scc = topo_sccs.get(i);
        	for (Vertex v : scc.getVertices())
        	{
        		attr_order.put(v.id, i);
        	}
        }
        
        // Step 5: Reorder the original FDs based on RHS attribute's SCC order
        ordered_fds = new ArrayList[topo_sccs.size()];
        for (int i = 0; i < ordered_fds.length; i++)
        	ordered_fds[i] = new ArrayList<FD>();
        
        for (FD f : all_fds)
        {
        	int rhs_id = f.getRHSColumnIndex();
        	Integer order = attr_order.get(rhs_id);
        	if (order == null)
        	{
        		// RHS attribute not in any SCC (shouldn't happen), default to 0
        		order = 0;
        	}
        	f.setOrder(order);  // Update the FD's order to match its new bucket
        	ordered_fds[order].add(f);
        }
        
        if (Graph.DEBUG)
        {
            int i = 0;
            for (ArrayList<FD> list: ordered_fds)
            {
            	System.out.println("Level: "+i++);
            	for (FD f: list)
            		System.out.println(f);
            }        	
        }
	}
	

	
	
	

}
