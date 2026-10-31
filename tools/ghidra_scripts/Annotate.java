// 1) Create functions at every code address referenced by a TVector in the data section.
// 2) Apply names/comments from a symbols file: lines "ADDR NAME [# comment]" (hex addr, '#' lines ignored).
//    Function at ADDR is renamed if present, else a label is created.
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.*;
import ghidra.program.model.listing.*;
import ghidra.program.model.mem.*;
import ghidra.program.model.symbol.*;
import java.io.*;
import java.nio.file.*;
import java.util.*;
import ghidra.program.model.data.*;
import ghidra.app.decompiler.*;
import ghidra.program.model.pcode.*;

public class Annotate extends GhidraScript {
    @Override
    public void run() throws Exception {
        Memory mem = currentProgram.getMemory();
        MemoryBlock code = mem.getBlock(toAddr(0x10000000L));
        int created = 0;
        for (MemoryBlock b : mem.getBlocks()) {
            if (!b.isInitialized() || b == code) continue;
            for (long a = b.getStart().getOffset(); a + 8 <= b.getEnd().getOffset(); a += 4) {
                long v = mem.getInt(toAddr(a)) & 0xffffffffL;
                long toc = mem.getInt(toAddr(a + 4)) & 0xffffffffL;
                if (toc != 0x10024120L || !code.contains(toAddr(v))) continue;
                Address ca = toAddr(v);
                if (getFunctionAt(ca) == null) {
                    disassemble(ca);
                    if (createFunction(ca, null) != null) created++;
                }
            }
        }
        println("created functions: " + created);
        String[] args = getScriptArgs();
        if (args.length == 0) return;
        int n = 0;
        for (String line : Files.readAllLines(Paths.get(args[0]))) {
            line = line.strip();
            if (line.isEmpty() || line.startsWith("#")) continue;
            String comment = null;
            int h = line.indexOf('#');
            if (h >= 0) { comment = line.substring(h + 1).strip(); line = line.substring(0, h).strip(); }
            String[] p = line.split("\\s+");
            Address a = toAddr(Long.parseLong(p[0].replace("0x", ""), 16));
            Function f = getFunctionAt(a);
            if (f != null) {
                f.setName(p[1], SourceType.USER_DEFINED);
                if (comment != null) f.setComment(comment);
            } else {
                currentProgram.getSymbolTable().createLabel(a, p[1], SourceType.USER_DEFINED);
                if (comment != null) setPlateComment(a, comment);
            }
            n++;
        }
        println("applied symbols: " + n);
        if (args.length > 1) applyStructs(args[1]);
    }

    void applyStructs(String path) throws Exception {
        DataTypeManager dtm = currentProgram.getDataTypeManager();
        Map<String, Structure> structs = new HashMap<>();
        Structure cur = null;
        int nparams = 0;
        for (String line : Files.readAllLines(Paths.get(path))) {
            String comment = null;
            int h = line.indexOf('#');
            if (h >= 0) { comment = line.substring(h + 1).strip(); line = line.substring(0, h); }
            line = line.strip();
            if (line.isEmpty()) continue;
            String[] p = line.split("\\s+");
            if (p[0].equals("STRUCT")) {
                cur = new StructureDataType(p[1], Integer.decode(p[2]));
                structs.put(p[1], cur);
            } else if (p[0].equals("FIELD")) {
                int off = Integer.decode(p[1]);
                DataType t;
                if (p[2].equals("int")) t = IntegerDataType.dataType;
                else if (p[2].equals("short")) t = ShortDataType.dataType;
                else if (p[2].equals("byte")) t = ByteDataType.dataType;
                else if (p[2].equals("ptr")) t = PointerDataType.dataType;
                else if (p[2].startsWith("char[")) t = new ArrayDataType(CharDataType.dataType, Integer.parseInt(p[2].substring(5, p[2].length() - 1)), 1);
                else if (p[2].contains("[") && structs.containsKey(p[2].substring(0, p[2].indexOf('[')))) {
                    Structure el = structs.get(p[2].substring(0, p[2].indexOf('[')));
                    int cnt = Integer.parseInt(p[2].substring(p[2].indexOf('[') + 1, p[2].length() - 1));
                    t = new ArrayDataType(el, cnt, el.getLength());
                }
                else throw new Exception("bad type " + p[2]);
                cur.replaceAtOffset(off, t, t.getLength(), p[3], comment);
            } else if (p[0].equals("PARAM")) {
                Structure st = structs.get(p[3]);
                DataType resolved = dtm.addDataType(st, DataTypeConflictHandler.REPLACE_HANDLER);
                Function f = getFunctionAt(toAddr(Long.parseLong(p[1], 16)));
                int idx = Integer.parseInt(p[2]);
                if (f == null) { println("PARAM skip " + line); continue; }
                if (idx >= f.getParameterCount()) {
                    DecompInterface d = new DecompInterface();
                    d.openProgram(currentProgram);
                    DecompileResults r = d.decompileFunction(f, 120, monitor);
                    HighFunctionDBUtil.commitParamsToDatabase(r.getHighFunction(), true,
                        HighFunctionDBUtil.ReturnCommitOption.NO_COMMIT, SourceType.USER_DEFINED);
                    d.dispose();
                }
                if (idx >= f.getParameterCount()) { println("PARAM skip " + line); continue; }
                f.getParameter(idx).setDataType(new PointerDataType(resolved), SourceType.USER_DEFINED);
                nparams++;
            }
        }
        for (Structure st : structs.values()) dtm.addDataType(st, DataTypeConflictHandler.REPLACE_HANDLER);
        println("applied struct params: " + nparams);
    }
}
