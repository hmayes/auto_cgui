#!/usr/bin/env python3
"""
Unit and regression test for the cgui-wrangler package.
"""

import unittest
from auto_cgui.run_tests import main


class TestRunTests(unittest.TestCase):
    def testNoArgs(self):
        test_input = ["-w /Users/hmayes/bee/cgui/"]
        main(test_input)

