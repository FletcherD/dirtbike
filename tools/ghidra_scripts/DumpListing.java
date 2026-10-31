// Dump disassembly of the whole program (one instruction per line, with function headers) to the given path.
import ghidra.app.script.GhidraScript;
import ghidra.program.model.listing.*;
import java.io.*;

public class DumpListing extends GhidraScript {
    @Override
    public void run() throws Exception {
        Listing l = currentProgram.getListing();
        try (PrintWriter w = new PrintWriter(new FileWriter(getScriptArgs()[0]))) {
            for (Instruction i : l.getInstructions(true)) {
                Function f = getFunctionAt(i.getAddress());
                if (f != null) w.println("\n;==== " + f.getName());
                w.println(i.getAddress() + "  " + i.toString());
            }
        }
    }
}
