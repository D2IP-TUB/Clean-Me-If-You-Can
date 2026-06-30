import java.util.ArrayList;
import java.util.Collections;
import java.util.HashSet;


public class FD {
	
	private HashSet<Integer> LHS; //Attribute ids for FD LHS 
	private int RHS; //Attribute ids for FD RHS
	
	private int order; //order of fd in the chase
	
	public FD(FD f)
	{
		f.LHS = LHS;
		f.RHS = RHS;
		
		f.order = order;
	}
	
	public FD(HashSet<Integer> LHS, int RHS, int order)
	{
		this.LHS = LHS;
		this.RHS = RHS;
		
		this.order = order;
	
	}	
	
	public FD(Vertex LHS, Vertex RHS, int order)
	{

		
		this.order = order;
		
		this.LHS = new HashSet<Integer>();
		
		//Build LHS
		if (LHS instanceof VertexGroup) //multi atts lhs
		{
			VertexGroup vg = (VertexGroup) LHS;
			

			
			for (Vertex v: vg.getVertexGroup())
			{
				this.LHS.add(v.id);

			}
		}
		else
		{
			
			this.LHS.add(LHS.id);
		}
		
		
		
		//Build RHS
		this.RHS = RHS.id;
		
	}
	
	public int getOrder()
	{
		return order;
	}
	
	public void setOrder(int order)
	{
		this.order = order;
	}
	
	public HashSet<Integer> getLHSColumnIndexes()
	{
		return LHS;
	}
	
	public int getRHSColumnIndex()
	{
		return RHS;
	}
	
	public boolean hasSameRHS(FD f)
	{
		return (f.RHS == RHS)? true : false;
	}
	
	
	public boolean hasSameLHS(FD f)
	{
		HashSet<Integer> f_lhs = f.LHS;
		
		for (Integer i: LHS)
		{
			if (!f_lhs.contains(i)) return false;
		}
		
		return true;
	}
	

	public ArrayList<FD> getParentFDs(ArrayList<FD>[] fd_list)
	{
		ArrayList<FD> parents_fds = new ArrayList<FD>();

		for (ArrayList<FD> list: fd_list)
			for (FD f: list)
			{
				
				if (f.equals(this)) continue;
				
				if (this.LHS.contains(f.RHS))
				{
					parents_fds.add(f);
				}
			}
		
		return parents_fds;		
	}

	
	//True if RHS appears in LHS of another FD
	public ArrayList<FD> getAdjacentFDs(ArrayList<FD>[] fd_list)
	{
		ArrayList<FD> adj_fds = new ArrayList<FD>();

		for (ArrayList<FD> list: fd_list)
			for (FD f: list)
			{
				
				if (f.equals(this)) continue;
				
				if (f.LHS.contains(this.RHS))
				{
					adj_fds.add(f);
				}
			}
		
		return adj_fds;
				
	}
	
	@Override
	public int hashCode() {
		// System.out.println("MyInt HashCode: " + i.hashCode());
		return order;
	}

	@Override
	public boolean equals(Object obj) {

		FD f = (FD) obj;
		return hasSameLHS(f) && hasSameRHS(f);

	}	
	
	@Override
	public String toString()
	{
		String s = "";
		
		for (int i: LHS)
			s += i + " ";
		
		s += "-> ";
		
		s += RHS;
		
		return s;
	}

}
