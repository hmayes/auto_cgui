import shutil
import os.path
import time
from multiprocessing import Process
from os.path import join as pjoin
from splinter import Browser
from selenium.common.exceptions import TimeoutException

# Keys
BROWSER_TYPE = 'browser_type'
BASE_URL = 'base_url'


class CGUIBrowserProcess(Process):
    """Usage: subclass this class and write an init_system() method.

    For an example, see MCABrowserProcess.
    """
    CHARMM_ERROR = 'CHARMM was terminated abnormally.'
    PHP_NOTICE = "Notice:"
    PHP_WARNING = "Warning:"
    PHP_ERROR = "Error:"
    PHP_FATAL_ERROR = "Fatal error:"
    PHP_MESSAGES = PHP_NOTICE, PHP_WARNING, PHP_ERROR

    def __init__(self, todo_q, done_q, **kwargs):
        """Setup Queues, browser settings, and delegate rest to multiprocessing.Process"""
        if BROWSER_TYPE not in kwargs:
            kwargs[BROWSER_TYPE] = 'chrome'
        self.browser_type = kwargs[BROWSER_TYPE]
        del kwargs[BROWSER_TYPE]

        if BASE_URL not in kwargs:
            kwargs[BASE_URL] = 'http://charmm-gui.org/'
        self.base_url = kwargs[BASE_URL]
        if not self.base_url.endswith('/'):
            self.base_url += '/'
        del kwargs[BASE_URL]

        if 'www_dir' not in kwargs:
            kwargs['www_dir'] = None
        self.www_dir = kwargs['www_dir']
        del kwargs['www_dir']

        if not 'pause' in kwargs:
            kwargs['pause'] = False
        self.pause = kwargs['pause']
        del kwargs['pause']

        super().__init__(**kwargs)
        self.todo_q = todo_q
        self.done_q = done_q

    def click(self, click_elem_id, wait=None):
        self.browser.find_by_id(click_elem_id).click()
        if wait:
            self.wait_text(wait)

    def click_by_text(self, text, wait=None):
        self.browser.find_by_text(text).click()
        if wait:
            self.wait_text(wait)

    def click_by_attrs(self, wait=None, **attrs):
        css_templ = "[{}='{}']"
        css_str = ''
        for attr, value in attrs.items():
            css_str += css_templ.format(attr, value)
        self.browser.find_by_css(css_str).click()
        if wait:
            self.wait_text(wait)

    def click_lipid_category(self, category):
        """Activate a lipid category in the Membrane Builder lipid selection page"""
        self.browser.find_by_text(category).find_by_xpath('../img').first.click()


    def copy_dir(self, ncopy, signal=True):
        """Make `ncopy` copies of the current project directory.

        Requirements:
            - self.test_case['jobid'] must be set
            - self.www_dir must be set (passed to __init__)
        All copies will be named as {jobid}_{copy_id}


        If the destination already exists, it is *not* overwritten.
        """
        if self.www_dir == None:
            raise ValueError("www_dir is not set")
        jobid = str(self.test_case['jobid'])
        src = pjoin(self.www_dir, jobid)
        for i in range(ncopy):
            i = str(i+1)
            dst = pjoin(self.www_dir, jobid+'_'+i)
            if os.path.exists(dst):
                print(self.name, "warning:", dst, "exists; skipping ...")
                continue
            shutil.copytree(src, dst)

        if signal:
            self.done_q.put(('CONTINUE', self.test_case))

    def eval(self, expr):
        """Evaluate a Python command that could refer to a method of self
        *OR* to a global function.
        """
        try:
            # isolate the function name
            fname = expr[:expr.index('(')]
        except ValueError:
            raise SyntaxError("invalid syntax: " + expr)
        if fname in dir(self):
            # make it a method call
            expr = 'self.'+expr
        return eval(expr)

    def go_next(self, test_text=None):
        self.browser.find_by_id('nextBtn').click()
        if test_text:
            print("waiting for", test_text)
            self.wait_text_multi([test_text, self.CHARMM_ERROR])

    def handle_step(self, step_info):
        for elem in step_info['elems']:
            name = list(elem.keys())[0]
            value = elem[name]
            self.browser.fill(name, value)

    def resume_step(self, jobid, project=None, step=None, link_no=None):
        """Uses Job Retriever to return to the given step.

        You must provide either:
            1) Project name AND step number
            2) Link number

        project: doc to return to
        step: step of doc to return to
        link_no: 0-indexed order of recovery link to return to
        """
        browser = self.browser
        url = self.base_url + "?doc=input/retriever"
        browser.visit(url)

        browser.fill('jobid', str(jobid))
        browser.find_by_css('input[type=submit]').click()

        success = 'Job found'
        failure = 'No job with that ID'
        found_text = self.wait_text_multi([success, failure])
        if found_text == failure:
            raise ValueError(failure)

        if link_no != None:
            assert isinstance(link_no, int), "link_no must be an integer"
            table = browser.find_by_css("#recovery_table tr:not(:first-child) td:nth-child(3)")
            table[link_no].click()
        else:
            raise NotImplementedError
            assert project != None and step != None, "Missing args"

    def run(self):
        with Browser(self.browser_type) as browser:
            self.browser = browser
            self.step = step_num = -1
            for test_case in iter(self.todo_q.get, 'STOP'):
                try:
                    self.test_case = test_case
                    print(self.name, "starting", test_case['label'])
                    start_time = time.time()
                    resume_link = 0
                    base = os.path.abspath(pjoin('files', test_case['base']))
                    self.base = base
                    if 'jobid' in test_case:
                        jobid = test_case['jobid']
                        resume_link = test_case['resume_link']
                        self.resume_step(jobid, link_no=resume_link)
                    else:
                        self.init_system(test_case)

                    jobid = test_case['jobid']
                    print(self.name, "Job ID:", jobid)

                    steps = test_case['steps'][resume_link:]
                    failure = False
                    for step_num, step in enumerate(steps):
                        self.step = step_num
                        if 'wait_text' in step:
                            print(self.name, "waiting for", step['wait_text'])
                            found_text = self.wait_text_multi([step['wait_text'], self.CHARMM_ERROR, self.PHP_FATAL_ERROR])
                        if found_text != step['wait_text']:
                            failure = True
                            break

                        # Check for PHP errors, warnings, and notices
                        if self.warn_if_text(self.PHP_MESSAGES) and self.pause:
                            print(self.name, "pausing; interrupt to exit")
                            while True:
                                time.sleep(1)

                        if 'presteps' in step:
                            for prestep in step['presteps']:
                                self.eval(prestep)
                        if 'elems' in step:
                            self.handle_step(step)
                        if 'poststeps' in step:
                            for poststep in step['poststeps']:
                                self.eval(poststep)
                        self.go_next()

                    elapsed_time = time.time() - start_time

                    # early failure?
                    if failure:
                        self.done_q.put(('FAILURE', test_case, step_num, elapsed_time))
                        continue

                    # late failure?
                    found_text = self.wait_text_multi([test_case['final_wait_text'], self.CHARMM_ERROR])
                    if found_text == self.CHARMM_ERROR:
                        self.done_q.put(('FAILURE', test_case, step_num, elapsed_time))
                    else:
                        self.done_q.put(('SUCCESS', test_case, elapsed_time))
                except Exception as e:
                    import sys, traceback
                    # give the full exception string
                    exc_str = ''.join(traceback.format_exception(*sys.exc_info()))
                    self.done_q.put(('EXCEPTION', test_case, step_num, exc_str))
                    if self.pause:
                        print(self.name, "pausing; interrupt to exit")
                        while True:
                            time.sleep(1)

    def wait_text(self, text):
        print(self.name, "waiting for text:", text)
        try:
            while not self.browser.is_text_present(text, wait_time=1):
                pass
        except TimeoutException:
            print(self.name, "timed out receiving message from renderer")

    def wait_text_multi(self, texts):
        wait_time = None
        while True:
            for text in texts:
                try:
                    if self.browser.is_text_present(text, wait_time):
                        return text
                except TimeoutException:
                    print(self.name, "timed out receiving message from renderer")
                wait_time = None
            wait_time = 1

    def warn_if_text(self, text):
        msg = "Warning: {} ({}) found '{{}}' on step {}"
        if not 'jobid' in self.test_case:
            jobid = '-1'
        else:
            jobid = str(self.test_case['jobid'])
        msg = msg.format(self.name, jobid, self.step)
        if isinstance(text, list) or isinstance(text, tuple):
            texts = text
            for text in texts:
                if self.browser.is_text_present(text):
                    print(msg.format(text))
                    return text
        elif self.browser.is_text_present(text):
            print(msg.format(text))
            return text
