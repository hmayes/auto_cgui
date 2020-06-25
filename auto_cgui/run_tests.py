#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
run_tests.py
Based on git@github.com:nk53/auto_cgui.git

Handles the primary functions
"""

import argparse
import os
import sys
import yaml
from pathlib import Path
from configparser import ConfigParser
from importlib import import_module
from time import sleep
from multiprocessing import Queue
from common_wrangler.common import (process_cfg, INPUT_ERROR, GOOD_RET, MAIN_SEC, warning, InvalidDataError,
                                    INVALID_DATA, make_dir)
from auto_cgui.cgui_common import (BASE_URL, BROWSER, PAUSE, WWW_DIR, INTERACTIVE, TEST_NAME, INTER_QUEUE, MSG_QUEUE,
                                   LOG_FILE, COPY, MODULE, NUM_THREADS, PASSWORD, TEST_DIR, USER, MODULE_SCRIPT, JOB_ID)

SOURCES_DIR = os.path.dirname(__file__)

# defaults and config keys
DEF_BASE_URL = 'http://beta.charmm-gui.org/'
DEF_BROWSER = 'chrome'
DEF_LOG_FNAME = 'results.log'
DEF_TEST_NAME = 'basic.yml'
DEF_TEST_DIR = os.path.join(SOURCES_DIR, 'test_cases')

FEP = 'FEP'
MCA = 'MCA'
POLYMER = 'POLYMER'
CGUI_MODULES = {FEP: 'FEPBrowserProcess',
                MCA: 'MCABrowserProcess',
                POLYMER: 'PBBrowserProcess'}

# JOBID = 'jobid'

DEF_CFG_VALS = {BASE_URL: DEF_BASE_URL,
                BROWSER: DEF_BROWSER,
                COPY: False,
                # JOBID: None,
                LOG_FILE: DEF_LOG_FNAME,
                MODULE: MCA,
                NUM_THREADS: 1,
                INTERACTIVE: False,
                PASSWORD: 'lammps',
                PAUSE: False,
                TEST_DIR: DEF_TEST_DIR,
                TEST_NAME: DEF_TEST_NAME,
                USER: 'testing',
                WWW_DIR: None,
                }

REQ_KEYS = {}


def log_exception(logfile, case_info, step_num, exc_info):
    templ = 'Job "{}" ({}) encountered an exception on step {}:\n{}\n'
    if JOB_ID not in case_info:
        case_info[JOB_ID] = '-1'
    jobid = case_info[JOB_ID]
    with open(logfile, 'a') as fh:
        label = case_info['label']
        fh.write(templ.format(label, jobid, step_num, exc_info))


def log_failure(logfile, case_info, step, elapsed_time):
    templ = 'Job "{}" ({}) failed on step {} after {:.2f} seconds\n'
    if JOB_ID not in case_info:
        case_info[JOB_ID] = '-1'
    jobid = case_info[JOB_ID]
    with open(logfile, 'a') as fh:
        label = case_info['label']
        fh.write(templ.format(label, jobid, step, elapsed_time))


def log_success(logfile, case_info, elapsed_time):
    templ = 'Job "{}" ({}) finished successfully after {:.2f} seconds\n'
    jobid = case_info[JOB_ID]
    with open(logfile, 'a') as fh:
        label = case_info['label']
        fh.write(templ.format(label, jobid, elapsed_time))


def read_cfg(f_loc, cfg_proc=process_cfg):
    """
    Reads the given configuration file, returning a dict with the converted values supplemented by default values.

    :param f_loc: The location of the file to read.
    :param cfg_proc: The processor to use for the raw configuration values.  Uses default values when the raw
        value is missing.
    :return: A dict of the processed configuration file's data.
    """
    config = ConfigParser()
    good_files = config.read(f_loc)

    if not good_files:
        raise IOError(f"Could not find specified configuration file: {f_loc}")

    main_proc = cfg_proc(dict(config.items(MAIN_SEC)), DEF_CFG_VALS, REQ_KEYS)

    return main_proc


def check_input(args):
    """
    Validate input
    :param args: user-input and/or default args
    :return: n/a; updated args if needed
    """
    if args.config[WWW_DIR] is None:
        # make nested path if it does not exist
        args.config[WWW_DIR] = Path.home().joinpath('.local', 'bin', 'cgui_www')
    make_dir(args.config[WWW_DIR])
    if args.config[MODULE] in CGUI_MODULES.keys():
        args.config[MODULE_SCRIPT] = CGUI_MODULES[args.config[MODULE]]
    else:
        raise ValueError(f'Unknown C-GUI module: {args.config[MODULE]}. Available modules are: {CGUI_MODULES.keys()}')

    if args.config[INTERACTIVE]:
        if args.config[NUM_THREADS] > 1:
            raise InvalidDataError("Error: '--interactive' flag is incompatible with 2+ threads")
        args.config[INTER_QUEUE] = Queue()
        args.config[MSG_QUEUE] = Queue()
    else:
        args.config[INTER_QUEUE] = None
        args.config[MSG_QUEUE] = None


def parse_cmdline(argv):
    """
    Returns the parsed argument list and return code.
    `argv` is a list of arguments, or `None` for ``sys.argv[1:]``.
    """
    if argv is None:
        argv = sys.argv[1:]

    # initialize the parser object:
    parser = argparse.ArgumentParser(description="Test a C-GUI (CHARMM-GUI) project.")
    parser.add_argument('-b', '--base_url', metavar="URL", default=DEF_BASE_URL,
                        help=f"Web address to CHARMM-GUI (default: '{DEF_BASE_URL}')")
    parser.add_argument("-c", "--config", help="The location of the configuration file in the 'ini' format. This file "
                                               "can be used to \noverwrite default values such as for energies.",
                        default=None, type=read_cfg)
    parser.add_argument('-i', '--interactive', action='store_true',
                        help=f"Option to specify and interactive job.")
    parser.add_argument('-l', '--logfile', default='results.log',
                        help=f"Filename for log file. The default name is {DEF_LOG_FNAME}.")
    parser.add_argument('-m', '--module', type=str, default=MCA,
                        help=f"Default module is '{MCA}' (multicomponent assembler). Other options (all case "
                             f"insensitive): POLYMER and FEB")
    parser.add_argument('-n', '--num_threads', type=int, default=1, metavar="N",
                        help="Number of parallel threads to spawn for testing (default: 1)")
    parser.add_argument('-p', '--pause', action='store_true', help="Pause execution on error.")
    parser.add_argument('-t', '--test_name', default=DEF_TEST_NAME,
                        help=f"Name of test to run (default: {DEF_TEST_NAME})")
    parser.add_argument('--test_dir', default=DEF_TEST_NAME,
                        help=f"Name of test to run (default: {os.path.relpath(DEF_TEST_DIR)})")
    parser.add_argument('-w', '--www_dir', metavar="PATH",
                        help=f"Directory where C-GUI projects are stored, e.g. `$HOME/.local/bin/cgui_www`. "
                             f"This is the default location; such a folder will be created if it does not exist.")
    parser.add_argument('--copy', action='store_true',
                        help="For tests on localhost, run solvent tests by cloning the project at the solvent test's "
                             "branch point; saves time, but can cause errors if the request cache is corrupted")

    args = None
    try:
        args = parser.parse_args(argv)
        # dict below to map config input and defaults to command-line input
        conf_arg_dict = {BASE_URL: args.base_url,
                         COPY: args.copy,
                         INTERACTIVE: args.interactive,
                         LOG_FILE: args.logfile,
                         MODULE: args.module.upper(),
                         NUM_THREADS: args.num_threads,
                         PAUSE: args.pause,
                         TEST_NAME: args.test_name,
                         WWW_DIR: args.www_dir,
                         }
        if args.config is None:
            args.config = DEF_CFG_VALS.copy()
        # Now overwrite any config values with command-line arguments, only if those values are not the default
        for config_key, arg_val in conf_arg_dict.items():
            if not (arg_val == DEF_CFG_VALS[config_key]):
                args.config[config_key] = arg_val
        check_input(args)
    except (KeyError, IOError, SystemExit) as e:
        if hasattr(e, 'code') and e.code == 0:
            return args, GOOD_RET
        else:
            return args, INPUT_ERROR

    return args, GOOD_RET


def main(argv=None):
    """
    Runs the main program.
    :param argv: The command line arguments.
    :return: The return code for the program's termination.
    """
    if argv is None:
        argv = sys.argv[1:]
    args, ret = parse_cmdline(argv)
    if ret != GOOD_RET or args is None:
        return ret

    cfg = args.config

    try:
        logfile = cfg[LOG_FILE]
        # indicate whether logfile already exists
        if os.path.exists(logfile):
            print("Appending to existing logfile:", logfile)
        else:
            print("Creating new logfile:", logfile)

        # import relevant names from the module file
        module = import_module('..' + cfg[MODULE_SCRIPT], package='auto_cgui.' + cfg[MODULE_SCRIPT])
        init_module = getattr(module, 'init_module')
        browser_process = getattr(module, cfg[MODULE_SCRIPT])

        test_case_path = os.path.join(cfg[TEST_DIR], cfg[MODULE].lower(), cfg[TEST_NAME])
        with open(test_case_path) as fh:
            test_cases = yaml.load(fh, Loader=yaml.FullLoader)

        base_cases, wait_cases = init_module(test_cases, args)

        todo_queue = Queue()
        done_queue = Queue()

        processes = [browser_process(todo_queue, done_queue, **cfg) for _ in range(cfg[NUM_THREADS])]

        # initialize browser processes
        for p in processes:
            p.start()

        # put regular cases in the task queue
        pending = 0
        for case in base_cases:
            sleep(0.1 * pending)
            todo_queue.put(case)
            pending += 1

        # main communication loop
        while pending:
            result = done_queue.get()
            pending -= 1
            if result[0] == 'SUCCESS':
                done_case, elapsed_time = result[1:]
                # done_label = done_case['label']
                # done_jobid = str(done_case[JOB_ID])
                log_success(logfile, done_case, elapsed_time)
            elif result[0] == 'FAILURE':
                done_case, step_num, elapsed_time = result[1:]
                log_failure(logfile, done_case, step_num, elapsed_time)
            elif result[0] == 'EXCEPTION':
                done_case, step_num, exc_info = result[1:]
                # elapsed_time = -1 # don't report time for exceptions
                log_exception(logfile, done_case, step_num, exc_info)
                warning("Exception encountered for job ({})".format(done_case[JOB_ID]))
                warning(exc_info)
            elif result[0] == 'CONTINUE':
                pending += 1
                done_case = result[1]
                done_label = done_case['label']
                # are any tasks waiting on this one?
                if done_label in wait_cases:
                    done_jobid = str(done_case[JOB_ID])
                    for num, wait_case in enumerate(wait_cases[done_label]):
                        if args.copy:
                            wait_case[JOB_ID] = done_jobid + '_' + str(num + 1)
                            wait_case['resume_link'] = done_case['solvent_link']
                        todo_queue.put(wait_case)
                        pending += 1
                    del wait_cases[done_label]

        # signal to stop
        for _ in processes:
            todo_queue.put('STOP')

        # clean up
        for p in processes:
            p.join()
    except (InvalidDataError, KeyError) as e:
        warning(e)
        return INVALID_DATA

    return GOOD_RET  # success


if __name__ == "__main__":
    status = main()
    sys.exit(status)
