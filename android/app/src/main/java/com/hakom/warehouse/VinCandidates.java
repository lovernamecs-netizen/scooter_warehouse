package com.hakom.warehouse;
import java.util.*;
import java.util.regex.*;
/** Candidate extraction is conservative, not a certification that a VIN is genuine. */
public final class VinCandidates {
    private static void add(Set<String> out,String value){if(!value.matches("[A-Z0-9]{17}")||!value.matches(".*[0-9].*"))return;String v=value.replace('O','0').replace('Q','0').replace('I','1');if(v.matches("[A-HJ-NPR-Z0-9]{17}"))out.add(v);}
    public static List<String> extract(String raw){LinkedHashSet<String> labelled=new LinkedHashSet<>(),other=new LinkedHashSet<>();Pattern label=Pattern.compile("^(?:(?:VIN|CHASSIS|FRAME)(?:\\s*(?:NO|NUMBER)\\.?)?|NO\\.?|차대번호)\\s*[:：.#-]?\\s*");for(String line:raw.toUpperCase(Locale.ROOT).split("[\\r\\n]+")){line=line.trim();Matcher lm=label.matcher(line);boolean hasLabel=lm.find();if(hasLabel)line=line.substring(lm.end());Set<String> found=hasLabel?labelled:other;Matcher tokens=Pattern.compile("[A-Z0-9]+").matcher(line);while(tokens.find())add(found,tokens.group());if(line.matches("[A-Z0-9\\s*\\-]+"))add(found,line.replaceAll("[\\s*\\-]",""));}labelled.addAll(other);return new ArrayList<>(labelled).subList(0,Math.min(12,labelled.size()));}
}
