import java.util.ArrayList;
import java.util.Comparator;


public class Value implements Comparable<Value>{
	
	String value;
	double support;
	
	double count;
	
	
	
	double score;
	
	public Value(String value, double support) 
	{
		this.value = value;
		this.support = support;
		
		this.count = support;
		
		this.score = support;
	}
	
	public double getScore()
	{
		return score;
	}
	
	public double getSupport()
	{
		return support;
	}
	
	public String getValue()
	{
		return value;
	}
	
	public void updateSupport(double support)
	{
		//this.count = this.support;
		
		this.support = support;
		this.score = support;
	}
	
	public void updateScore(double score)
	{
		this.score = score;
		
		//Balance
		
		//double diff = Math.abs(score - support);
		
/*		if (diff > 0.2)
		{
			this.score /= 2; 
		}*/
		
		
		
	}
	

	
	@Override
	public boolean equals(Object obj) {

		return (value.equals(((Value)obj).value))? true : false;

	}	

	
	
	   
	@Override
	public int compareTo(Value v2) {
		
		if (this.score > v2.score)
			return -1;
		
		if (this.score < v2.score)
			return 1;
		
		return 0;
	}

}
