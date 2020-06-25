#!/usr/bin/env python3
"""
Unit and regression test for the cgui-wrangler package.
"""

import os
import unittest
from pathlib import Path

from common_wrangler.common import make_dir

from auto_cgui.run_tests import main

TEST_DIR = Path(__file__).parents[0]
TEST_WWW_DIR = TEST_DIR.joinpath('temp_www')


class TestRunTests(unittest.TestCase):
    def testFindPath(self):
        test_input = ["-w", str(TEST_WWW_DIR)]
        main(test_input)

    def testNoArgs(self):
        test_path = os.path.join(os.path.dirname(__file__), 'www')
        self.assertTrue(os.path.exists(test_path))
        self.assertTrue(os.path.isdir(test_path))
        # main("-w", "")
