import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;



public class RepairCover {
	
	QValue v;
	LocalDependecyGraph g;
	Marker mk;
	
	ArrayList<Pattern> cover;
	
	public RepairCover(QValue v, LocalDependecyGraph g, Marker mk)
	{
		cover = new ArrayList<Pattern>();
		this.v = v;
		this.g = g;
		this.mk = mk;
	}
	
	
	public void clear_cover()
	{
		cover = new ArrayList<Pattern>();
	}
	
	
	
	public void ComputeMinimalRepairCover()
	{
		InfluenceVSet inf = g.local_inf;
		//ArrayList<QValue> cover = new ArrayList<QValue>();
		
		int attribute_id = v.getAttributeId();
		
		//Get all edges in inf(v_i)
		HashSet<Pattern> in_edges = inf.getInfInFromAttributeIndex(attribute_id);
		HashSet<Pattern> out_edges = inf.getInfOutFromAttributeIndex(attribute_id);
			
		boolean found = true;
		//Find an edge in F in in_edges
		for (Pattern edge: in_edges)
		{

			FD f = edge.fd;

			
			for (Integer i: f.getLHSColumnIndexes())
			{
				QValue qv = g.vconfidence_map.get(i);
				
				if (mk.getAssignment(qv) != Marker.NodeAssignment.FIXED)
				{
					found = false;
					break;
				}

			}
			
			if (found)
			{
				cover.add(edge);
				break;
				
			}
			else
				found = true; //reset and search for new edge
		}
		
		if (cover.size() == 1) {

			for (Pattern edge : out_edges) {
				// Build key
				String lhs_key = "";

				FD f = edge.fd;

				QValue qv = g.vconfidence_map.get(f.getRHSColumnIndex());

				if (mk.getAssignment(qv) == Marker.NodeAssignment.FIXED) {
					cover.add(edge);
					break;
				}
			}

		}
		
	}
	
	public void printRepairCover()
	{
		System.out.print("ReapirCover("+v.getAttributeId() + ", "+v.getValue()+") = {");
		
		for (int i = 0; i < cover.size(); i++)
		{
			if (cover.get(i).getFirstKey().isEmpty()) continue;
			
			if (i == 0) System.out.print(cover.get(i).getFirstKey());
			
			else if (i == 1) System.out.print("}, {"+cover.get(i).getFirstPattern().value);
		}
		
		System.out.println("}");
	}

}
