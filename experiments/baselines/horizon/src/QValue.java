import java.util.ArrayList;
import java.util.HashSet;


//This class is used to represent data values and their confidence scores

public class QValue {
	
	private String value;
	private int attribute_id;
	private double confidence;

	
	
	public QValue(String value, int attribute_id, double confidence)
	{
		this.value = value;
		this.confidence = confidence;
		this.attribute_id = attribute_id;

	}
	
	public String getValue()
	{
		return value;
	}
	
	public void setValue(String new_v)
	{
		this.value = new_v;
	}
	
	public void setConfidence(double confidence)
	{
		this.confidence = confidence;
	}

	
	public int getAttributeId()
	{
		return attribute_id;
	}
	
	public double getConfidence()
	{
		return confidence;
	}
	
	@Override
	public int hashCode()
	{
		return attribute_id;
	}
	
	@Override
	public boolean equals(Object obj)
	{
		QValue qv = (QValue)obj;
		
		if (value.equals(qv.value) && attribute_id == qv.attribute_id)
		{
			return true;
		}
		
		return false;
		
	}
	
/*	public boolean isResolveable() //true if all nodes in repair cover belong to F
	{ 
		
	}*/
	
	public void GetRepairCover(InfluenceVSet inf, LocalDependecyGraph g)
	{
		//Get edges in inf(this)
		HashSet<Pattern> plist = inf.getInfFromAttributeIndex(attribute_id);
		
		
		
		
	}
	
	public void print()
	{
		System.out.println("["+attribute_id+"], "+value + ", "+confidence);
	}
	
	@Override
	public String toString()
	{
		return "["+attribute_id+", "+value+"]";
	}

}
