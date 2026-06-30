import java.io.BufferedReader;
import java.io.FileNotFoundException;
import java.io.FileReader;
import java.io.IOException;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.PriorityQueue;

//We have one local dependency graph per input tuple. Assumes all indexes have been created (global dependency graph)
public class LocalDependecyGraph {
	
	HashMap<Integer, QValue> vconfidence_map; //1 for each input tuple
	InfluenceVSet local_inf;
	String line;
	HashMap<Integer, RepairCover> repair_covers;
	
	

	
	public LocalDependecyGraph(String line)
	{
		vconfidence_map = new HashMap<Integer, QValue>();
		
		this.line = line;
		
		local_inf = LocalDependencyGraphManager.inf.getLocalInfluenceSet(line);
		
		repair_covers = new HashMap<Integer, RepairCover>();

	}
	
	public HashMap<Integer, RepairCover> getRepairCovers()
	{
		return repair_covers;
	}
	
	public void updateRepairCover(int i)
	{
		RepairCover rc = repair_covers.get(i);
		
		rc.clear_cover();
		
		rc.ComputeMinimalRepairCover();		
		
		System.out.println("Update Repair Cover for "+i);
		//rc.printRepairCover();
	}
	
	public void computeRepairCovers(Marker mk)
	{
		for (Integer i: vconfidence_map.keySet())
		{
			RepairCover rc = new RepairCover(vconfidence_map.get(i), this, mk);
			
			rc.ComputeMinimalRepairCover();
			
			//rc.printRepairCover();
			
			repair_covers.put(i, rc);
			
		}
	}
	
	public void ComputeVConfidenceFromFile()
	{

		double confidence = 0;

		String vals[] = CsvUtils.parseCsvLine(line);

		for (int i = 0; i < vals.length; i++) {
			if (LocalDependencyGraphManager.inf.getInfFromAttributeIndex(i) == null)
				continue;

			confidence = 0;
			int n_edges = 0;

			HashSet<Pattern> plist = LocalDependencyGraphManager.inf.getInfFromAttributeIndex(i);

			for (Pattern p : plist) {
				FD f = p.fd;

				String lhs_key = "";
				String rhs_val;

				for (Integer lhs_index : f.getLHSColumnIndexes()) {
					lhs_key += vals[lhs_index] + " ";
				}

				lhs_key = lhs_key.trim();

				rhs_val = vals[f.getRHSColumnIndex()];

				PriorityQueue<Value> pq = p.getPattern(lhs_key);

				for (Value v : pq) {
					if (v.value.equals(rhs_val)) {
						confidence += v.getSupport();
						//System.out.println("debug "+lhs_key + ", "+v.value +" = "+v.getSupport());
						break;
					}
				}

				n_edges++;

			}

			// Add confidence for value val[i]
			confidence = confidence / n_edges;

			QValue qvalue = new QValue(vals[i], i, confidence);
			
	
			vconfidence_map.put(i, qvalue);


			


		}

	}
	
	public double computeQualityCotributionFlow(QValue qv)
	{
		
		double conf = qv.getConfidence();
		double sum_in_flow = 0;
		int n_nodes = 0;
		
		HashSet<Pattern> inf_set = local_inf.getInfFromAttributeIndex(qv.getAttributeId());
		double n_edges = inf_set.size();
		
		
		for (Pattern edge: inf_set)
		{
			
			//double original_support = edge.getFirstPattern().getSupport();
			
			FD f = edge.fd;
			
			for (Integer lhs_index: f.getLHSColumnIndexes())
			{
				sum_in_flow += vconfidence_map.get(lhs_index).getConfidence();
				n_nodes++;
			}			
		}	
		
		double avg_in_flow = sum_in_flow / n_nodes;
		
		//is current vcconfidence contributing to the flow positively or negatively?
		
		//System.out.println("Quality contribution for ["+qv.getAttributeId() + ", " + qv.getValue() + "] = in "+avg_in_flow + " current "+conf);
		
		if (conf >= avg_in_flow)
			return 1;


		else return 0;
		
			
	}
	
	public double computeQualityCotribution(QValue qv)
	{
		HashSet<Pattern> inf_set = local_inf.getInfFromAttributeIndex(qv.getAttributeId());
		double contribution = 0;
		double n_edges = inf_set.size();
		
		
		
		for (Pattern edge: inf_set)
		{
			
			double original_support = edge.getFirstPattern().getSupport();
			
			FD f = edge.fd;
			
			int n_nodes_involved = f.getLHSColumnIndexes().size();
			n_nodes_involved++; //account for rhs			
			
			double current_vconfidence = vconfidence_map.get(qv.getAttributeId()).getConfidence();
			
			//current_vconfidence = (enumerator + original_support)/n_nodes_involved
			//enumerator = original_support * n_nodes involved - current_vconfidence;
			
			double enumerator = (original_support * n_nodes_involved) - current_vconfidence;
			
			double new_support = enumerator / (n_nodes_involved - 1);
			
			//System.out.println("New support for node ["+qv.getAttributeId() + ", " + qv.getValue() + "] = "+new_support);
			
			//System.out.println(original_support);
			
			if (new_support <= original_support)
			{
				contribution += 1;
			}
			else
			{
				double diff = new_support - original_support;
				
				
			}
			
		}
		
		return (contribution/n_edges);
		
	}
	
	//Has to be called AFTER Vconfidence computation (because we need the confidence values for all the vertices computed) 	
	public void ComputeEConfidence(String line)
	{
		
		double confidence = 0;
		int n_nodes = 0;

		String vals[] = CsvUtils.parseCsvLine(line);

		for (int i = 0; i < vals.length; i++) {
			if (local_inf.getInfFromAttributeIndex(i) == null)
				continue;


			HashSet<Pattern> plist = local_inf.getInfFromAttributeIndex(i);
			
			

			for (Pattern p : plist) { //for each edge, assign confidence
				FD f = p.fd;
				
				confidence = 0;
				n_nodes = 0;
				
				String lhs_key = "";
				String rhs_val = vals[f.getRHSColumnIndex()];
				
				
				for (Integer lhs_index : f.getLHSColumnIndexes()) {
					confidence += vconfidence_map.get(lhs_index).getConfidence();
					n_nodes++;
					
					lhs_key += vals[lhs_index] + " ";
				}	
				
				lhs_key = lhs_key.trim();
				
				
				
				confidence += vconfidence_map.get(f.getRHSColumnIndex()).getConfidence();
				n_nodes++;
				
				confidence = confidence / n_nodes;
				
				PriorityQueue<Value> pq = p.getPattern(lhs_key);
				
				if (pq == null) continue;
				
				for (Value v: pq)
				{
					if (v.value.equals(rhs_val))
					{
						v.updateSupport(confidence);
						//v.setConfidence(confidence);
						break;
					}
				}
				
				

			}

		}
	}
	
	public void ComputeReapirCover(String line)
	{
		
	}
	
	public void printEConfidence()
	{
		
		
		for (Integer att_index: local_inf.getAttributeIndexes())
		{
			
			HashSet<Pattern> hs = local_inf.getInfFromAttributeIndex(att_index);
			
			for (Pattern lp: hs)
			{
				//lp.printPattern();
				
				for (String key: lp.value_map.keySet())
				{
					Value v = lp.getPattern(key).element();
					System.out.println("EConfidence("+key+", "+v.getValue()+") = "+lp.getPattern(key).element().getSupport());
				}
			}
		}
	}
	
	public void printVConfidenceMap()
	{
		for (Integer att_index: vconfidence_map.keySet())
			System.out.println("VConfidence("+att_index+", "+ vconfidence_map.get(att_index).getValue()+ ") = "+vconfidence_map.get(att_index).getConfidence());

	}

}
