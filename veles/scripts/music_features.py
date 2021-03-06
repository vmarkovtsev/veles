#!/usr/bin/env python3
# encoding: utf-8
"""
.. invisible:
     _   _ _____ _     _____ _____
    | | | |  ___| |   |  ___/  ___|
    | | | | |__ | |   | |__ \ `--.
    | | | |  __|| |   |  __| `--. \
    \ \_/ / |___| |___| |___/\__/ /
     \___/\____/\_____|____/\____/

Created on May 23, 2013

This script extracts music features from audio files.

This script scans the given directories for files with the specified name
pattern and extracts the features from the configuration file, saving
the results to XML file.

It uses libSoundFeatureExtraction as the calculation backend.

███████████████████████████████████████████████████████████████████████████████

Licensed to the Apache Software Foundation (ASF) under one
or more contributor license agreements.  See the NOTICE file
distributed with this work for additional information
regarding copyright ownership.  The ASF licenses this file
to you under the Apache License, Version 2.0 (the
"License"); you may not use this file except in compliance
with the License.  You may obtain a copy of the License at

  http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing,
software distributed under the License is distributed on an
"AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
KIND, either express or implied.  See the License for the
specific language governing permissions and limitations
under the License.

███████████████████████████████████████████████████████████████████████████████
"""


from argparse import ArgumentParser
from argparse import RawDescriptionHelpFormatter
from itertools import chain
import logging
import multiprocessing as mp
import os
import re
import sys
import time

from veles.dot_pip import install_dot_pip
install_dot_pip()
from veles.loader.libsndfile_loader import SndFileMixin
from veles.snd_features import SoundFeatures
from sound_feature_extraction.library import Library
from sound_feature_extraction.features_xml import FeaturesXml

__all__ = []
__version__ = 1.0
__date__ = '2013-05-22'
__updated__ = '2015-03-30'


class CLIError(Exception):
    """Generic exception to raise and log different fatal errors."""
    def __init__(self, msg):
        super(CLIError).__init__(type(self))
        self.msg = "E: %s" % msg

    def __str__(self):
        return self.msg

    def __unicode__(self):
        return self.msg


def mp_run(files, extr):
    try:
        logging.debug("Reading %d files...", len(files))
        loader = SndFileMixin()
        extr.inputs = [loader.decode_file(f) for f in files]
        logging.debug("Extracting features from %d files...", len(files))
        extr.run()
        return extr.outputs
    except:
        logging.exception("Subprocess failed")


def filter_files(files, root, prefix, inpat, expat):
    for f in files:
        if (not inpat or re.match(inpat, prefix + f)) and \
           (not expat or not re.match(expat, prefix + f)):
            full_name = os.path.join(root, f)
            logging.debug("Added " + full_name)
            yield full_name


def main(argv=None):  # IGNORE:C0111
    """Command line options."""

    if argv is None:
        argv = sys.argv
    else:
        sys.argv.extend(argv)

    # program_name = os.path.basename(sys.argv[0])
    program_version = "v%s" % __version__
    program_build_date = str(__updated__)
    program_version_message = \
        '%%(prog)s %s (%s)' % (program_version, program_build_date)
    program_shortdesc = __import__('__main__').__doc__.split("\n")[1]
    program_license = """%s

  Copyright 2013 Samsung R&D Institute Russia. All rights reserved.

  Licensed under Apache 2.0

USAGE
""" % program_shortdesc

    try:
        # Setup argument parser
        parser = ArgumentParser(description=program_license,
                                formatter_class=RawDescriptionHelpFormatter)
        parser.add_argument("-l", "--lib", dest="library",
                            default="libSoundFeatureExtraction.so",
                            help="path to the native library "
                                 "[default: %(default)s]",
                            metavar="path")
        parser.add_argument("-f", "--features", dest="features",
                            help="name of the file with feature "
                                 "descriptions [default: %(default)s]",
                            metavar="path", required=True)
        parser.add_argument("-o", "--output", dest="output",
                            help="name of the XML file with extracted "
                                 "features [default: %(default)s]",
                            metavar="path", required=True)
        parser.add_argument("-g", "--graph", dest="report",
                            help="save the extraction report graphs at "
                                 "this path [default: %(default)s]",
                            metavar="path", required=False)
        parser.add_argument("-r", "--recursive", dest="recurse",
                            action="store_true", default=True,
                            help="recurse into subfolders [default: "
                                 "%(default)s]")
        parser.add_argument("-1", "--single-threaded", dest="single",
                            action="store_true", default=False,
                            help="single-threaded extraction [default: "
                                 "%(default)s]")
        parser.add_argument("-ns", "--no-simd", dest="nosimd",
                            action="store_true", default=False,
                            help="disable SIMD acceleration [default: "
                                 "%(default)s]")
        parser.add_argument("-v", "--verbose", dest="verbose",
                            action="count", default=0,
                            help="set verbosity level [default: %(default)s]")
        parser.add_argument("-i", "--include", dest="include",
                            help="only include paths matching this regex "
                                 "pattern. Note: exclude is given preference "
                                 "over include. [default: %(default)s]",
                                 metavar="RE")
        parser.add_argument("-e", "--exclude", dest="exclude",
                            help="exclude paths matching this regex pattern. "
                                 "[default: %(default)s]", metavar="RE")
        parser.add_argument('-V', '--version', action='version',
                            version=program_version_message)
        parser.add_argument(dest="paths",
                            help="paths to folder(s) with audio file(s) "
                                 "[default: %(default)s]",
                            metavar="path", nargs='+')

        # Process arguments
        args = parser.parse_args()

        library_path = args.library
        feature_file = args.features
        output = args.output
        report = args.report
        paths = args.paths
        verbose = args.verbose
        recurse = args.recurse
        inpat = args.include
        expat = args.exclude
        single = args.single
        nosimd = args.nosimd

        if verbose > 4:
            verbose = 4
        logging.basicConfig(level=50 - verbose * 10)

        if inpat and expat and inpat == expat:
            raise CLIError("include and exclude pattern are equal! "
                           "Nothing will be processed.")

        start_timer = time.time()

        # initialize Library
        Library(library_path)
        # We can do work in parallel more effectively with multiprocessing
        if not single:
            Library().set_omp_transforms_max_threads_num(1)
        if nosimd:
            Library().set_use_simd(0)
        features = FeaturesXml.parse(feature_file)
        logging.info("Read %d features", len(features))

        found_files = []
        for inpath in paths:
            if recurse:
                for root, _, files in os.walk(inpath, followlinks=True):
                    logging.debug("Scanning " + root + "...")
                    found_files.extend(filter_files(files, root,
                                                    root[len(inpath):],
                                                    inpat, expat))
            else:
                files = [f for f in os.listdir(inpath)
                         if os.path.isfile(os.path.join(inpath, f))]
                found_files.extend(filter_files(
                    files, root, "", inpat, expat))

        if len(found_files) == 0:
            logging.warn("No files were found")
            return 0
        logging.info("Found %d files", len(found_files))

        timer = time.time()
        extr = SoundFeatures(report, None)
        logging.debug("Parsing the supplied features...")
        extr.add_features(features)
        extr.initialize()
        logging.info("Done in %f", (time.time() - timer))
        timer = time.time()

        pcount = mp.cpu_count()
        splitted_found_files = [found_files[i::pcount] for i in range(pcount)]
        if not single:
            with mp.Pool(pcount) as pool:
                results_async = [
                    pool.apply_async(mp_run, (splitted_found_files[i], extr))
                    for i in range(0, pcount)]
                pool.close()
                pool.join()
                extr.outputs = list(chain(*[r.get() for r in results_async]))
                logging.info("Analyzed %d files", len(extr.outputs))
        else:
            all_outputs = []
            for i in range(0, len(splitted_found_files)):
                all_outputs += mp_run(splitted_found_files[i], extr)
            extr.outputs = all_outputs
        logging.info("Done in %f", (time.time() - timer))
        timer = time.time()
        logging.debug("Saving the results...")
        extr.save_to_file(output, list(chain(*splitted_found_files)))

        logging.info("Finished in %f", (time.time() - start_timer))
        return 0
    except KeyboardInterrupt:
        logging.critical("Interrupted")
        return 0
    except Exception:
        logging.critical("Failed")
        raise

if __name__ == "__main__":
    sys.exit(main())
