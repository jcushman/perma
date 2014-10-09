from __future__ import print_function

import StringIO
import imghdr
import new
import os
import unittest
import requests
from sauceclient import SauceClient
import sys
from selenium import webdriver
from selenium.common.exceptions import ElementNotVisibleException, NoSuchElementException
import time


# get settings
from selenium.webdriver import ActionChains
from selenium.webdriver.common.alert import Alert
from selenium.webdriver.common.keys import Keys

SCRIPT_DIR = os.path.abspath(os.path.dirname(__file__))
HOST = os.environ.get('HOST', 'http://127.0.0.1:8000')
USERNAME = os.environ.get('SAUCE_USERNAME')
ACCESS_KEY = os.environ.get('SAUCE_ACCESS_KEY')
TARGET_BROWSERS = os.environ.get('TARGET_BROWSERS')
if TARGET_BROWSERS:
    TARGET_BROWSERS = TARGET_BROWSERS.split(',')
assert USERNAME and ACCESS_KEY, "Please make sure that SAUCE_USERNAME and SAUCE_ACCESS_KEY are set."

# base setup
sauce = SauceClient(USERNAME, ACCESS_KEY)
os.chdir(SCRIPT_DIR)


# set up browsers
# options: https://saucelabs.com/platforms
browsers = {
    "mac_chrome": {
        "platform": "Mac OS X 10.9",
        "browserName": "chrome",
        "version": "31"},

    "win8_ie11": {
        "platform": "Windows 8.1",
        "browserName": "internet explorer",
        "version": "11"},

    "win7_firefox": {
        "platform": "Windows 7",
        "browserName": "firefox",
        "version": "30"},

    "winxp_ie8": {
        "platform": "Windows XP",
        "browserName": "internet explorer",
        "version": "8"},

    "iphone": {
        "platform": "OS X 10.9",
        "browserName": "iPhone",
        "version": "7.1",
        "device-orientation": "portrait",
        "nonSyntheticWebClick": False},
}

## helpers
def on_platforms(platforms):
    """
        Run given unit test in each platform (browser) provided.
        Via http://saucelabs.com/examples/example.py
    """
    def decorator(base_class):
        module = sys.modules[base_class.__module__].__dict__
        for nickname, platform in platforms.items():
            if TARGET_BROWSERS and nickname not in TARGET_BROWSERS:
                continue
            d = dict(base_class.__dict__)
            d['desired_capabilities'] = platform
            name = "%s_%s_%s" % (platform['platform'], platform['browserName'], platform['version'])
            module[name] = new.classobj(name, (base_class,), d)
    return decorator


@on_platforms(browsers)
class PermaTest(unittest.TestCase):
    def setUp(self):
        self.desired_capabilities['name'] = self.id()

        sauce_url = "http://%s:%s@ondemand.saucelabs.com:80/wd/hub"
        self.driver = webdriver.Remote(
            desired_capabilities=self.desired_capabilities,
            command_executor=sauce_url % (USERNAME, ACCESS_KEY)
        )
        self.driver.implicitly_wait(30)

    def test_all(self):
        # get host
        host = HOST
        if not host.startswith('http'):
            host = "http://"+host

        self.driver.implicitly_wait(10)
        action_chains = ActionChains(self.driver)

        # helpers
        def click_link(link_text):
            self.driver.find_element_by_link_text(link_text).click()

        def get_by_xpath(xpath):
            return self.driver.find_element_by_xpath(xpath)

        def get_by_id(id):
            return self.driver.find_element_by_id(id)

        def get_by_text(text, element_type='*'):
            return get_by_xpath("//%s[contains(text(),'%s')]" % (element_type, text))

        def get_by_css(css_selector):
            return self.driver.find_element_by_css_selector(css_selector)

        def is_displayed(element, repeat=True):
            """ Check if element is displayed, by default retrying for 10 seconds if false. """
            if repeat:
                def repeater():
                    assert element.is_displayed()
                    return True
                try:
                    repeat_while_exception(repeater, AssertionError)
                except AssertionError:
                    return False
            return element.is_displayed()

        def click_and_type(element, text):
            element.click()
            element.send_keys(text)

        def info(*args):
            print("%s %s %s:" % (
                self.desired_capabilities['platform'],
                self.desired_capabilities['browserName'],
                self.desired_capabilities['version'],
            ), *args)

        def repeat_while_exception(func, exception=Exception, timeout=10, sleep_time=.1):
            end_time = time.time()+timeout
            while True:
                try:
                    return func()
                except exception:
                    if time.time()>end_time:
                        raise
                    time.sleep(sleep_time)


        info("Loading homepage from %s." % host)
        self.driver.get(host)
        assert is_displayed(get_by_text("Websites Change"))

        info("Checking Perma In Action section.")
        get_by_xpath("//a[@data-img='MSC_1']").click()
        assert is_displayed(get_by_id('example-title'))
        get_by_css("#example-image-wrapper > img").click() # click on random element to trigger Sauce screenshot

        info("Loading docs.")
        get_by_xpath("//a[@href='/docs']").click()
        assert is_displayed(get_by_text('Overview', 'h2')) # wait for load

        info("Logging in.")
        click_link("Log in")
        assert "Email address" in get_by_xpath('//body').text
        get_by_id('id_username').send_keys('test_registrar_member@example.com')
        get_by_id('id_password').send_keys('pass')
        get_by_css(".btn-success.login").click()
        assert is_displayed(get_by_text('Create a Perma archive', 'h3')) # wait for load

        info("Creating archive.")
        click_and_type(get_by_id('rawUrl'), "example.com")  # type url
        get_by_id('addlink').click() # submit
        thumbnail = repeat_while_exception(lambda: get_by_css(".library-thumbnail img"), NoSuchElementException)
        thumbnail_data = requests.get(thumbnail.get_attribute('src'))
        thumbnail_fh = StringIO.StringIO(thumbnail_data.content)
        assert imghdr.what(thumbnail_fh) == 'png'
        # TODO: We could check the size of the generated png or the contents,
        # but note that the contents change between PhantomJS versions and OSes, so we'd need a fuzzy match

        info("Viewing playback.")
        link_browser_url = get_by_text('Links', 'a').get_attribute('href')  # get link browser url for later
        archive_url = get_by_css("a.perma-url").get_attribute('href')  # get link url from green button
        self.driver.get(archive_url)
        assert is_displayed(get_by_text('Live page view', 'a'))
        archive_view_link = get_by_id('warc_cap_container_complete')
        repeat_while_exception(lambda: archive_view_link.click(), ElementNotVisibleException) # wait for archiving to finish
        warc_url = self.driver.find_elements_by_tag_name("iframe")[0].get_attribute('src')
        self.driver.get(warc_url)
        assert is_displayed(get_by_text('This domain is established to be used for illustrative examples', 'p'))

        info("Browsing links.")
        self.driver.get(link_browser_url)
        root_folder = get_by_css('#j1_1 > a')
        # edit link
        get_by_css('.link-expand').click()
        click_and_type(get_by_css('.link-title'), 'Test Title')
        repeat_while_exception(lambda: get_by_xpath("//span[contains(@class,'title-save-status') and contains(text(),'saved.')]"), NoSuchElementException)
        click_and_type(get_by_css('.link-notes'), 'Test notes.')
        get_by_css('.link-title').click()  # click back to title to cause notes to save in ie8
        repeat_while_exception(lambda: get_by_xpath("//span[contains(@class,'notes-save-status') and contains(text(),'saved.')]"), NoSuchElementException)
        # folder create
        get_by_css('.new-folder').click()
        get_by_css('#folder-tree input').send_keys("Test Folder" + Keys.RETURN)
        # edit folder name
        click_link("Test Folder")
        get_by_css('.edit-folder').click()
        # delete folder
        get_by_css('#folder-tree input').send_keys("Test Folder New Name" + Keys.RETURN)
        get_by_css('.delete-folder').click()
        Alert(self.driver).accept()


    def tearDown(self):
        print("Link to your job: https://saucelabs.com/jobs/%s" % self.driver.session_id)
        try:
            if sys.exc_info() == (None, None, None):
                sauce.jobs.update_job(self.driver.session_id, passed=True)
            else:
                sauce.jobs.update_job(self.driver.session_id, passed=False)
        finally:
            self.driver.quit()



if __name__ == '__main__':
    unittest.main()