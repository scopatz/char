#!/usr/bin/env python

############################
#### Standard Libraries ####
############################
from __future__ import print_function
import os
import sys
import time
import shutil
import subprocess

from optparse import OptionParser

###########################
### Extension Libraries ###
###########################
import tables as tb

##########################
#### Custom Libraries ####
##########################
import isoname
import metasci
import metasci.nuke as msn
import metasci.graph as msg

from metasci.colortext import failure

#################
### CHAR Libs ###
#################
#import glbchar
defchar = None

import graphchar
import runchar
from n_code_mcnp    import NCodeMCNP
from n_code_origen  import NCodeORIGEN
from n_code_serpent import NCodeSerpent

def main():
    global defchar

    ###########################
    ### Command Line Parser ###
    ###########################
    usage = "usage: %prog [options] confchar"
    parser = OptionParser(usage)

    parser.add_option("-q", "--quiet", action="store_true", dest="Quiet", 
        default=False, help="Supresses stdout.")

    parser.add_option("-v", "--verbose", action="store_true", dest="Verbose", 
        default=False, help="Gives extra info while running.")

    parser.add_option("-i", "--input", action="store_true", dest="MakeInput", 
        help="Makes the transport calculation input deck.")

    parser.add_option("-r", "--run", action="store_true", dest="RunTransport", 
        default=False, help="Run the transport calculation.")

    parser.add_option("-d", "--dry-run", action="store_false", dest="RunTransport", 
        help="Dry Run. Do NOT run the transport calculation.")

    parser.add_option("-w", "--with", dest="RunWith", default="NONE", metavar="PROG", 
        help="Dictates what PROG to run transport calculation with. PROG = [MCNP | Serpent].")

    parser.add_option("-m", "--multi-core", dest="RunParallel", default="Single", metavar="PARA", 
        help="Dictates what PROG to run parallel transport calculation with. PARA = [Single | MPI | PBS].")

    parser.add_option("-O", "--ORIGEN", action="store_true", dest="RunORIGEN", 
        default=False, help="Run ORIGEN Burnup calculations.")

    parser.add_option("-l", "--local", action="store_true", dest="Local", 
        default=True, help="Run or Fetch files locally.")

    parser.add_option("-s", "--server", action="store_false", dest="Local", 
        help="Run or Fetch files from a remote server.")

    parser.add_option("-f", "--fetch", action="store_true", dest="FetchFiles", default=False, 
        help="Fetches files from the remote server. Does not run transport, even if -r is set. Automatically sets -s.")

    parser.add_option("-p", "--parse", action="store_true", dest="ParseData", 
        default=False, help="Parses output and stores it an HDF5 library.")

    parser.add_option("-t", "--text", action="store_true", dest="MakeText", 
        default=False, help="Parses output and makes text-based libraries.")

    parser.add_option("-9", "--tape9", action="store_true", dest="MakeTape9", 
        default=False, help="Parses output and makes a ORIGEN tape9 libraries for each burn step.")

    parser.add_option("-g", "--graph", action="store_true", dest="MakeGraphs", 
        default=False, help="Graphs data from libraries. Sets -p.")

    parser.add_option("-G", "--graph-ORIGEN", action="store_true", dest="MakeOrigenGraphs", 
        default=False, help="Graphs ORIGEN data only.")

    parser.add_option("-P", "--pid", action="store_true", dest="PID", default=False, 
        help="Finds the process identification number of a current transport run. Sets -d.")

    parser.add_option("-k", "--kill", action="store_true", dest="KillTransport", 
        default=False, help="Kills the current transport run. Sets -P.")

    parser.add_option("--no-burn", action="store_true", dest="NoBurnBool", default=False, 
        help="Removes the burn card from the MCNP deck.")

    parser.add_option("--no-pert", action="store_true", dest="NoPertBool", default=False, 
        help="Removes the perturbation cards from the MCNP deck.")

    (options, args) = parser.parse_args()

    # Load the CHAR definition file early, into its own namespace
    absolute_path = os.path.abspath(args[0])
    dir, file = os.path.split(absolute_path)
    sys.path.append(dir)
    mod_name = file.rpartition('.')[0]
    defchar = __import__(mod_name)

    #intial command-line options protocol.
    Quiet = options.Quiet
    options.RunWith = options.RunWith.upper()   #Ensures that RunWith is uppercase (nice for flags).
    if options.KillTransport:
        options.PID = True                      #Ensures that the PID is found in order that it mak be killed.
    if options.PID:
        options.RunTransport = False            #Ensures that transport calculation is not initiated while fetching files.
    if options.FetchFiles:
        options.RunTransport = False            #Ensures that transport calculation is not initiated while fetching files.
        options.Local = False                   #Ensures that ssh package is loaded.
    if options.RunORIGEN:
        options.MakeTape9 = True

    ################
    #### Script ####
    ################

    # Prep work
    if reactor not in os.listdir('.'):
        os.mkdir(reactor)
    os.chdir(reactor)

    # Set the transport code type
    if options.RunWith == "NONE":
        try:
            transport_code = TransportCode.lower()
        except:
            print(failure("Transport code type not set!"))
            print(failure("  Use either the '-w' command line option, or"))
            print(failure("  use the 'TransportCode' flag in defchar.py."))
            print(failure("Currently, 'MCNP' and 'Serpent' are accpeted values."))
            print()
            print(failure("Note: you must have the appropriate code installed on"))
            print(failure("your machine for this to work."))
            raise SystemExit
    else:
        transport_code = options.RunWith.lower()

    if ('serpent' in transport_code) and ('mcnp' not in transport_code):
        n_transporter = NCodeSerpent()
    elif ('mcnp' in transport_code) and ('serpent' not in transport_code):
        n_transporter = NCodeMCNP()
    else:
        print(failure("The transport code given is not valid: {0:yellow}", transport_code))
        print(failure("Currently, 'MCNP' and 'Serpent' are accpeted values."))
        raise SystemExit

    # Make the input file unless otherwise specified.
    if (options.MakeInput) and (not options.FetchFiles) and (not options.PID):
        if isinstance(n_transporter, NCodeSerpent):
            n_transporter.make_input()
        elif isinstance(n_transporter, NCodeMCNP):
            n_transporter.make_input(options.NoBurnBool, options.NoPertBool)

    # Run Transport code
    if options.RunTransport:
        runchar.make_run_script(n_transporter, options.RunWith, options.Local)
        if options.Local:
            runchar.run_transport_local(options.RunWith)
        else:
            runchar.run_transport_remote(options.RunWith)

    #Fetches files from remote server
    if options.FetchFiles:
        runchar.Fetch_Remote_Files()

    #Finds (and kills?) the Transport Run Process
    if options.PID:
        if options.Local:
            runchar.Find_PID_Local(options.KillTransport)
        else:
            runchar.Find_PID_Remote(options.RunWith, options.KillTransport)

    #Parse MCNPX Output & Make HDF5 Data Library
    if options.ParseData:
        parsechar.Write_HDF5_Lib_MCNP()

        #Parse MCNPX Output & Make Text-based Data Libraries
        if options.MakeText:
            parsechar.Write_TXT_Lib_MCNP()

    #Parse MCNPX Output & Make ORIGEN TAPE9 Libraries
    if options.MakeTape9:
        parsechar.Write_ORIGEN_Libs()

    #Run ORIGEN IRF Burnup Calculation
    if options.RunORIGEN:
        BU, k, Pro, Des, Tij = runchar.Run_ORIGEN()
        parsechar.Write_HDF5_Lib_ORIGEN( BU, k, Pro, Des, Tij )

        if options.MakeText:
            parsechar.Write_TXT_Lib_ORIGEN( BU, k, Pro, Des, Tij )

    #Make Graphs, for fun and learning
    if options.MakeGraphs:
        graphchar.Make_Figs_MCNP(options.Quiet)

        if options.RunORIGEN:
            graphchar.Make_Figs_ORIGEN(options.Quiet)

    #Make only the ORIGEN figures
    if options.MakeOrigenGraphs and not (options.MakeGraphs and options.RunORIGEN):
        graphchar.Make_Figs_ORIGEN(options.Quiet)


    #Clean up
    metasci.SafeRemove(reactor + ".m")
    metasci.SafeRemove(reactor + ".r")
    metasci.SafeRemove(reactor + ".s")
    os.chdir('..')


#Run CHAR
if __name__ == '__main__':
    main()