import java.nio.file.*;
import java.util.*;
import org.sinytra.connector.forge.transform.Forge52Symbols;

public final class TransformContractTest {
    public static void main(String[] args)throws Exception {
        int positive=0,negative=0;var audit=new TreeSet<String>();
        try(var paths=Files.walk(Path.of(args[0]))){
            for(var file:paths.filter(p->p.toString().endsWith(".class")).toList()){
                byte[] transformed=Forge52Symbols.transform(Files.readAllBytes(file),audit);
                if(transformed.length==0)throw new AssertionError("Empty transformed class");positive++;
            }
        }
        try(var paths=Files.walk(Path.of(args[1]))){
            for(var file:paths.filter(p->p.toString().endsWith(".class")).toList()){
                boolean rejected=false;
                try{Forge52Symbols.transform(Files.readAllBytes(file),new TreeSet<>());}
                catch(IllegalArgumentException expected){
                    if(!expected.getMessage().contains("Forge"))throw new AssertionError("Missing symbol diagnosis",expected);
                    rejected=true;
                }
                if(!rejected)throw new AssertionError("Accepted negative "+file);negative++;
            }
        }
        if(positive!=2||negative!=22)throw new AssertionError("Wrong fixture counts "+positive+"/"+negative);
        System.out.println("C1_ACTUAL_TRANSFORM_PASS positive="+positive+" negative="+negative+" auditedSymbols="+audit.size()+" abi="+Forge52Symbols.ABI);
    }
}
