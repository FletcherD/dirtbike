#!/bin/zsh
# Apply re/symbols.txt to the Ghidra project and re-export the full decompilation to work/ppc_decomp.c
cd "${0:a:h}/.."
G=~/opt/ghidra_12.2_PUBLIC/support/analyzeHeadless
$G work/ghidra dirtbike -process app.pef -scriptPath tools/ghidra_scripts \
   -postScript Annotate.java $PWD/re/symbols.txt $PWD/re/structs.txt -postScript DecompileAll.java $PWD/work/ppc_decomp.c -postScript DumpListing.java $PWD/work/ppc_listing.s \
   > work/ghidra_annotate.log 2>&1
grep -E "created functions|applied|skip|ERROR|Exception" work/ghidra_annotate.log
grep -c "^// ====" work/ppc_decomp.c
