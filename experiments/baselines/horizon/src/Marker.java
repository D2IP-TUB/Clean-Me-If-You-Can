import java.util.HashMap;
import java.util.HashSet;

//Given a local dependency graph g, this class is responsible for assigning vertices of g to the Chalgeable, Fixed and PossiblyChangeable sets 
public class Marker {
	
	public enum NodeAssignment {
	    FIXED,
	    CHANGE,
	    FUZZY,
	    UNASSIGNED;
	}	
	
	
	private LocalDependecyGraph dependency_graph;
	
	private HashMap<QValue, NodeAssignment> assignments;
	
	
	public Marker(LocalDependecyGraph dependency_graph)
	{
		this.dependency_graph = dependency_graph;
		assignments = new HashMap<QValue, Marker.NodeAssignment>();
	}
	
	public NodeAssignment getAssignment(QValue qv)
	{
		return assignments.get(qv);
	}
	
	public void updateAssignment(QValue qv, NodeAssignment new_assignment)
	{
		assignments.put(qv, new_assignment);
	}
	
	public void assignNodes_partial_cover()
	{
		
		InfluenceVSet inf = dependency_graph.local_inf;


		//Iterate over the nodes in the dependency graph, for each node compute quality contribution
		for (Integer att_id: dependency_graph.vconfidence_map.keySet())
		{
			
			HashSet<Pattern> in_edges = inf.getInfInFromAttributeIndex(att_id);

			QValue qv = dependency_graph.vconfidence_map.get(att_id);
			
			if (in_edges.size() == 0) //It means it's either an anchor or floating node, in both cases, it's put into the F set
			{
				//This is an anchor/floating node, assign it to F in this variation of the algorithm
				assignments.put(qv, NodeAssignment.FIXED);
				continue;
				
			}
			

			
			
			double contribution = dependency_graph.computeQualityCotributionFlow(qv);
			
			System.out.println("Quality contribution for ["+qv.getAttributeId() + ", " + qv.getValue() + "] = "+contribution);
			
			if (contribution == 1)
			{
				assignments.put(qv, NodeAssignment.FIXED);
			}
			else
			{
				assignments.put(qv, NodeAssignment.FUZZY);
				
				//Parent nodes should be CHANGE
				for (Pattern p: in_edges)
				{
					FD f = p.fd;
					System.out.println(f);
					
					boolean parent_fixed = true;
					
					
					for (Integer lhs_index: f.getLHSColumnIndexes())
					{
						System.out.println("lhs_index: "+lhs_index);
						QValue qv_parent = dependency_graph.vconfidence_map.get(lhs_index);
						qv_parent.print();
						if (!assignments.containsKey(qv_parent)) continue;
						
						System.out.println( " "+assignments.get(qv_parent).toString());
						if (assignments.get(qv_parent) == NodeAssignment.FUZZY)
						{
							
							System.out.println("CHANGING "+qv_parent.getAttributeId() + " "+qv_parent.getValue());
							assignments.put(qv_parent, NodeAssignment.CHANGE);
						}
						
						if (assignments.get(qv_parent) != NodeAssignment.FIXED)
						{
							parent_fixed  = false;
							
						}
					}
					
					if (parent_fixed)
						assignments.put(qv, NodeAssignment.CHANGE);
					
				}
				
			}
			
			
		}		
		
		for (QValue qv: assignments.keySet())
		{
			if (assignments.get(qv) == NodeAssignment.FUZZY)
				assignments.put(qv, NodeAssignment.FIXED);
		}
	}
	
	public void assignNodes()
	{
		//Iterate over the nodes in the dependency graph, for each node compute quality contribution
		for (Integer att_id: dependency_graph.vconfidence_map.keySet())
		{
			QValue qv = dependency_graph.vconfidence_map.get(att_id);
			
			double contribution = dependency_graph.computeQualityCotribution(qv);
			
			System.out.println("Quality contribution for ["+qv.getAttributeId() + ", " + qv.getValue() + "] = "+contribution);
			
			if (contribution >= 0.7)
			{
				assignments.put(qv, NodeAssignment.FIXED);
			}
			else if (contribution >= 0.5)
			{
				assignments.put(qv, NodeAssignment.FUZZY);
			}
			else
			{
				assignments.put(qv, NodeAssignment.CHANGE);
			}
			
			
		}
	}
	
	public void printAssignments()
	{
		for (QValue qv: assignments.keySet())
		{
			System.out.println(qv + " " + assignments.get(qv).toString());
		}
	}

}
