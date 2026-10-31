// Print addresses of symbols whose name contains the script arg.
import ghidra.app.script.GhidraScript;
import ghidra.program.model.symbol.*;

public class FindSym extends GhidraScript {
    @Override
    public void run() throws Exception {
        String q = getScriptArgs()[0];
        for (Symbol s : currentProgram.getSymbolTable().getAllSymbols(true))
            if (s.getName(true).contains(q)) println("SYM " + s.getName(true) + " " + s.getAddress());
    }
}
