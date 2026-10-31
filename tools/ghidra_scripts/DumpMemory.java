// Dump each initialized memory block to <outdir>/<name>_<start>.bin and print the block map.
import ghidra.app.script.GhidraScript;
import ghidra.program.model.mem.*;
import java.io.*;

public class DumpMemory extends GhidraScript {
    @Override
    public void run() throws Exception {
        String dir = getScriptArgs()[0];
        for (MemoryBlock b : currentProgram.getMemory().getBlocks()) {
            println("BLOCK " + b.getName() + " " + b.getStart() + " " + b.getSize() + " init=" + b.isInitialized());
            if (!b.isInitialized()) continue;
            byte[] buf = new byte[(int) b.getSize()];
            b.getBytes(b.getStart(), buf);
            String fn = b.getName().replaceAll("[^A-Za-z0-9_.]", "_") + "_" + b.getStart() + ".bin";
            try (FileOutputStream o = new FileOutputStream(new File(dir, fn))) { o.write(buf); }
        }
    }
}
