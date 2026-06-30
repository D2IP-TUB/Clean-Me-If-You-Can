import java.util.ArrayList;


public class PatternKey {
	
	String id;
	ArrayList<FD> involved_fds;
	
	
	
	public PatternKey(String id)
	{
		this.id = id;
		involved_fds = new ArrayList<FD>();
	}
	
	public void addFD(FD f)
	{
		involved_fds.add(f);
	}
	
	@Override
	public int hashCode() {
		return id.hashCode();
	}
	
	@Override
	public boolean equals(Object obj) {
		
		PatternKey pk = (PatternKey)obj;
		
		if (pk.involved_fds.size() != involved_fds.size()) return false;
		
		if (id.equals(pk.id))
			for (int i = 0; i < involved_fds.size(); i++)
				if (! involved_fds.get(i).equals(pk.involved_fds.get(i))) return false;
		
		return true;
	}
	
	public void printPatternKey()
	{
		System.out.println("id: "+id);
		for (FD f: involved_fds)
			System.out.println(f);
		
		System.out.println();
	}

}
