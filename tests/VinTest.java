import com.hakom.warehouse.VinCandidates;
import java.util.*;
public class VinTest {
 public static void main(String[] args){String vin="L1234567890123456";
 for(String raw:new String[]{"NO","NO 123","VIN","ABCDEFGHIJKLMNOPQ","XX"+vin+"YY"})if(!VinCandidates.extract(raw).isEmpty())throw new AssertionError(raw);
 for(String raw:new String[]{"VIN: "+vin,"CHASSIS NO: L123 4567 8901 23456","NO\n"+vin+"\n125CC","L123456789O123456"})if(!VinCandidates.extract(raw).equals(List.of(vin)))throw new AssertionError(raw);
 if(!VinCandidates.extract("SERIAL: M1234567890123456\nVIN: "+vin).equals(List.of(vin,"M1234567890123456")))throw new AssertionError("label priority");
 System.out.println("10 Java VIN cases passed");
 }
}
