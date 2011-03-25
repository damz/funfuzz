#!/usr/bin/env python

import os, shutil, subprocess, sys

from fnStartjsfunfuzz import archOfBinary, captureStdout, testDbgOrOpt, testJsShellOrXpcshell

p0=os.path.dirname(__file__)
lithiumpy = os.path.abspath(os.path.join(p0, "..", "lithium", "lithium.py"))
autobisectpy = os.path.abspath(os.path.join(p0, "..", "js-autobisect", "autoBisect.py"))
beautifyUsingJsShellpy = os.path.abspath(os.path.join(p0, "..", "jsfunfuzz", "beautifyUsingJsShell.py"))

def pinpoint(itest, logPrefix, jsEngine, engineFlags, infilename, bisectRepo, alsoRunChar=True):
    """
       Run Lithium and autobisect.

       itest must be an array of the form [module, ...] where module is an interestingness module.
       The module's "interesting" function must accept [...] + [jsEngine] + engineFlags + infilename
       (If it's not prepared to accept engineFlags, engineFlags must be empty.)
    """

    valgrindSupport = "--valgrind" in itest
    valgrindX = ["--valgrind"] if valgrindSupport else []

    lith1tmp = logPrefix + "-lith1-tmp"
    os.mkdir(lith1tmp)
    lithArgs = itest + [jsEngine] + engineFlags + [infilename]
    print ' '.join([lithiumpy] + lithArgs)
    subprocess.call([sys.executable, lithiumpy, "--tempdir=" + lith1tmp] + lithArgs, stdout=open(logPrefix + "-lith1-out", "w"))

    if alsoRunChar:
        lith2tmp = logPrefix + "-lith2-tmp"
        os.mkdir(lith2tmp)
        lith2Args = ["--char"] + lithArgs
        print ' '.join([lithiumpy] + lith2Args)
        subprocess.call([sys.executable, lithiumpy, "--tempdir=" + lith2tmp] + lith2Args, stdout=open(logPrefix + "-lith2-out", "w"))

    print
    print "Done running Lithium on the part in between DDBEGIN and DDEND. To reproduce, run:"
    print ' '.join([lithiumpy, "--strategy=check-only"] + lithArgs)
    print

    unbeautifiedOutput = captureStdout([sys.executable, lithiumpy, "--strategy=check-only"] + lithArgs)
    # Check that the testcase is interesting.
    if 'not interesting' not in unbeautifiedOutput:
        assert 'interesting' in unbeautifiedOutput
        # Beautify the output. This will remove DDBEGIN and DDEND as they are comments.
        # This will output a file with the '-beautified' suffix.
        # Reduce once using toString decompile method.
        subprocess.call([sys.executable, beautifyUsingJsShellpy, '--shell=' + jsEngine, "--decompilationType=uneval", infilename])

        print 'Operating on the beautified testcase for the n-th time where n =',
        # iterNum starts from 3 because lith1 and lith2 are already used above.
        iterNum = 3
        # Run Lithium on the testcase 10 more times, but run it using char only for 3 tries of toString and uneval reduction each.
        # Generally, lines don't get significantly reduced after the 3rd try of line reduction.
        MAX_BEAUTIFIED_LITHIUM_RUNS = iterNum + 10
        while(iterNum < MAX_BEAUTIFIED_LITHIUM_RUNS):
            print iterNum - 2,
            # Operate on the beautified version first.
            lithArgs = lithArgs[0:-1]
            beautifiedFilename = infilename + '-beautified'
            lithArgs = lithArgs + [beautifiedFilename]
            # We must still be operating on the beautified version.
            assert beautifiedFilename in lithArgs
            # Check that the testcase is still interesting.
            beautifiedOutput = captureStdout([sys.executable, lithiumpy, "--strategy=check-only"] + lithArgs)
            if 'not interesting' not in beautifiedOutput:
                assert 'interesting' in beautifiedOutput
                # Overwrite the original -reduced file with the beautified version since it is interesting.
                shutil.move(beautifiedFilename, infilename)
                lithBeautifiedTmpDir = logPrefix + '-lith' + str(iterNum) + '-tmp'
                os.mkdir(lithBeautifiedTmpDir)
                # Operate on the original -reduced file.
                lithArgs = lithArgs[0:-1]
                lithArgs = lithArgs + [infilename]
                assert beautifiedFilename not in lithArgs
                #print ' '.join([lithiumpy] + lithArgs)
                subprocess.call([sys.executable, lithiumpy, "--tempdir=" + lithBeautifiedTmpDir] + lithArgs, stdout=open(logPrefix + "-lith" + str(iterNum) + "-out", "w"))

                # Run it using char only after 3 tries of toString and uneval reduction each.
                if alsoRunChar and (iterNum - 2) > ((MAX_BEAUTIFIED_LITHIUM_RUNS - iterNum) // 2):
                    print iterNum - 2,
                    print '(operating on chars..)',
                    iterNum += 1
                    assert iterNum in (9, 11, 13)  # Refer to reduction method below
                    lithBeautifiedTmpCharDir = logPrefix + '-lith' + str(iterNum) + '-tmp'
                    os.mkdir(lithBeautifiedTmpCharDir)
                    lith2Args = ["--char"] + lithArgs
                    assert beautifiedFilename not in lith2Args
                    #print ' '.join([lithiumpy] + lith2Args)
                    subprocess.call([sys.executable, lithiumpy, "--tempdir=" + lithBeautifiedTmpCharDir] + lith2Args, stdout=open(logPrefix + "-lith" + str(iterNum) + "-out", "w"))
            else:
                # Beautified testcase is no longer interesting.
                print 'Beautified testcase is no longer interesting!'
                break
            iterNum += 1
            # We want the following reduction method:
            # iterNum 3: uneval
            # iterNum 4: toString
            # iterNum 5: uneval
            # iterNum 6: toString
            # iterNum 7: uneval
            # iterNum 8: toString
            # iterNum 9: char
            # iterNum 10: uneval
            # iterNum 11: char
            # iterNum 12: toString
            # iterNum 13: char
            if iterNum < MAX_BEAUTIFIED_LITHIUM_RUNS:
                # This will output a file with the '-beautified' suffix.
                # Rotate between reducing using the toString and uneval decompile method
                if iterNum % 2 == 0 and iterNum != 10:
                    # toString
                    assert iterNum in (4, 6, 8, 12)
                    subprocess.call([sys.executable, beautifyUsingJsShellpy, '--shell=' + jsEngine, "--decompilationType=toString", infilename])
                else:
                    # uneval
                    # iterNum 3 has already occurred prior to the increment of iterNum above.
                    assert iterNum in (5, 7, 10)
                    subprocess.call([sys.executable, beautifyUsingJsShellpy, '--shell=' + jsEngine, "--decompilationType=uneval", infilename])
            else:
                print

        # Operate on the original -reduced file.
        lithArgs = lithArgs[0:-1]
        lithArgs = lithArgs + [infilename]
        assert beautifiedFilename not in lithArgs
        # Check that the testcase is still interesting after the extra beautified lithium reductions.
        finalBeautifiedOutput = captureStdout([sys.executable, lithiumpy, "--strategy=check-only"] + lithArgs)
        if 'not interesting' not in finalBeautifiedOutput:
            assert 'interesting' in finalBeautifiedOutput

    jsEngineName = os.path.basename(jsEngine)
    if bisectRepo is not "none" and testJsShellOrXpcshell(jsEngine) != "xpcshell":
        autobisectCmd = [sys.executable, autobisectpy] + valgrindX + ["-d", bisectRepo, "-i", "-p", "-a", archOfBinary(jsEngine), "-c", testDbgOrOpt(jsEngine)] + engineFlags + [infilename] + itest
        print ' '.join(autobisectCmd)
        subprocess.call(autobisectCmd, stdout=open(logPrefix + "-autobisect", "w"), stderr=subprocess.STDOUT)
        print "Done running autobisect"
